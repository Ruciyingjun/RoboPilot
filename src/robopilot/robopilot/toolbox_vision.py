"""用途：复用聊天客户端识别工具箱及家居检查命题，严格校验视觉结果，不按颜色兜底。"""

import base64
import math
import time

import cv2

from .llm_client import LLMError, request_plan
from .llm_config import load_llm_config
from .perception import image_problem
from .targets import VISUAL_TARGETS
from .schemas import ValidationError, decode_json


def inspect_toolbox(image, timeout_s=60, *, config=None, request=request_plan, target='toolbox',
                    prompt_snapshot=None, max_output_tokens=None):
    if target not in VISUAL_TARGETS:
        raise ValidationError('Unsupported visual target')
    from .prompt_registry import pin_prompts, validate_snapshot
    selected = validate_snapshot(prompt_snapshot or pin_prompts([target])[target], target)
    prompt = selected['text']
    metadata = {'prompt_version':selected['id'],'prompt_sha256':selected['sha256']}
    definition = VISUAL_TARGETS[target]
    method = 'vlm_toolbox_v1' if target=='toolbox' else 'vlm_predicate_v1'
    started=time.monotonic()
    if not isinstance(timeout_s,(int,float)) or not math.isfinite(timeout_s) or timeout_s<=0:
        return {**metadata,'status':'unknown','reason':'视觉检查预算无效或已耗尽','method':method}
    deadline=started+timeout_s
    problem = image_problem(image)
    if problem:
        return {**metadata,'status':'unknown','reason':problem,'method':method}
    try:
        config = config or load_llm_config()
    except ValidationError as exc:
        return {**metadata,'status':'unknown','reason':f'视觉配置不可用：{exc}','method':method}
    # No text-only model fallback: explicit known vision model until other providers are verified.
    if config.provider != 'deepseek' or config.model != 'deepseek-flash':
        return {**metadata,'status':'unknown','reason':'工具箱识别仅支持已验证的 deepseek-flash',
                'method':method}
    from .rsi_store import model_fingerprint
    if selected.get('deployment_model') and selected['deployment_model'] != model_fingerprint(config):
        return {**metadata,'status':'unknown','reason':'Active prompt was evaluated for another model configuration',
                'method':method,'error_kind':'configuration'}
    height,width=image.shape[:2]
    scale=min(1,1024/max(height,width))
    image=cv2.resize(image,(round(width*scale),round(height*scale))) if scale<1 else image
    ok,encoded=cv2.imencode('.png',image)
    if not ok or encoded.nbytes > 2*1024*1024:
        raise ValueError('Cannot encode image within 2 MiB limit')
    allowed = definition['cues'] if definition else ('handle','lid','latch','rigid_container')
    messages=[{'role':'user','content':[{'type':'text','text':prompt},
        {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(encoded).decode('ascii')}}]}]
    turn={}
    error_kind = None
    try:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise LLMError('视觉编码后预算已耗尽')
        options = {} if max_output_tokens is None else {'max_output_tokens':max_output_tokens}
        raw=request(config.endpoint,config.model,config.api_key,messages,{},'json',
            min(remaining,config.timeout_s),provider=config.provider,thinking='disabled',
            reasoning_effort=config.reasoning_effort,turn=turn,**options)
        result=decode_json(raw)
        if (not isinstance(result,dict) or set(result)!= {'view_clear','status','reason','visual_cues'}
                or type(result['view_clear']) is not bool
                or result['status'] not in ('detected','not_detected','unknown')
                or not isinstance(result['reason'],str) or not 1<=len(result['reason'])<=1000
                or not isinstance(result['visual_cues'],list) or len(result['visual_cues'])>4
                or any(not isinstance(c,str) or c not in allowed
                       for c in result['visual_cues'])):
            raise ValidationError('Invalid vision response schema')
        if not result['view_clear']:
            result.update(status='unknown',reason='观察区域受阻，无法确认：'+result['reason'])
        cues=set(result['visual_cues'])
        if result['status']=='detected' and (not set(definition['required']).issubset(cues) if definition
                else (len(cues)<2 or not cues&{'handle','latch'})):
            result.update(status='unknown',reason='模型未提供足够检查证据：'+result['reason'])
    except (LLMError,ValidationError) as exc:
        error_kind = 'service' if isinstance(exc,LLMError) else 'protocol'
        result={'status':'unknown','reason':f'视觉服务结果不可用：{exc}','visual_cues':[]}
    return {**metadata, **result, 'error_kind':error_kind,'condition_satisfied': {'detected':True,'not_detected':False,'unknown':None}[result['status']],
            'predicate': definition['label'] if definition else '工具箱是否在本次视野内',
            'method':method,'model':config.model,
            'duration_s':round(time.monotonic()-started,3),'usage':turn.get('telemetry',{})}
