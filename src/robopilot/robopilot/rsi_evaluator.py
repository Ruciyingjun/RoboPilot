"""Bounded paired VLM evaluations with durable partial results and explicit fixture mode."""
import json
import time
import uuid

from .llm_client import request_plan
from .rsi_gate import POLICY, assess
from .rsi_store import evaluator_fingerprint, model_fingerprint, now
from .schemas import ValidationError
from .storage import _atomic_write
from .toolbox_vision import inspect_toolbox


def evaluate(store,candidate_id,dataset_id,config,*,split='gate',repeats=3,fixtures=None,
             max_requests=200,max_tokens=50000,total_timeout=600.,request=request_plan):
    if (split not in ('development','gate','test') or type(repeats) is not int or not 1<=repeats<=10
            or type(max_requests) is not int or not 1<=max_requests<=2000
            or type(max_tokens) is not int or max_tokens<1 or not 0<total_timeout<=3600):
        raise ValidationError('Invalid evaluation limits')
    if fixtures is not None and store.kind!='sandbox':
        raise ValidationError('Fixture evaluations require a sandbox registry')
    if config.provider!='deepseek' or config.model!='deepseek-flash':
        raise ValidationError('Evaluation requires the supported visual model configuration')
    candidate = store.prompt(candidate_id)
    baseline = store.active(candidate['target'])
    if candidate['parent']!=baseline['id']:
        raise ValidationError('Candidate parent is not the active baseline')
    if baseline.get('deployment_model') and baseline['deployment_model']!=model_fingerprint(config):
        raise ValidationError('Baseline deployment model changed')
    dataset = store.dataset(dataset_id)
    cases = [c for c in dataset['cases'] if c['target']==candidate['target'] and c['split']==split]
    if not cases or len(cases)*repeats*2>max_requests:
        raise ValidationError('Empty evaluation split or request budget too small')
    report = {'id':'eval_'+uuid.uuid4().hex,'status':'RUNNING','created_at':now(),
        'target':candidate['target'],'baseline':baseline['id'],'candidate':candidate_id,
        'dataset':dataset_id,'split':split,'repeats':repeats,'policy':dict(POLICY),
        'model':model_fingerprint(config),'evaluator_sha256':evaluator_fingerprint(),
        'mode':'fixture' if fixtures is not None else 'live','rows':[], 'tokens':0, 'requests':0,
        'limits':{'max_requests':max_requests,'max_tokens':max_tokens,'timeout_s':total_timeout},'error':''}
    directory = store.root/'evaluations'/report['id']
    directory.mkdir(parents=True)
    def save():
        store.save_evaluation(report)
        _atomic_write(directory/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    save()
    began = time.monotonic()
    try:
        for repeat in range(repeats):
            for case in cases:
                image = store.image(case)
                # Alternate order to reduce systematic first/second request effects.
                roles = ('baseline','candidate') if repeat%2==0 else ('candidate','baseline')
                for role in roles:
                    remaining = total_timeout-(time.monotonic()-began)
                    if remaining<=0 or report['tokens']>=max_tokens:
                        raise TimeoutError('Evaluation time/token budget exhausted')
                    calls = []
                    def call(*args,**kwargs):
                        if report['requests']>=max_requests:
                            raise ValidationError('Evaluation request budget exhausted')
                        report['requests'] += 1
                        calls.append(True)
                        # Persist admission BEFORE the request; a crash never hides an admitted call.
                        save()
                        if fixtures is not None:
                            raw = fixtures[role][case['id']]
                            kwargs['turn']['telemetry'] = {'total_tokens':10}
                            return json.dumps(raw)
                        return request(*args,**kwargs)
                    started = time.monotonic()
                    result = inspect_toolbox(image,min(config.timeout_s,remaining),config=config,
                        request=call,target=candidate['target'],
                        prompt_snapshot=baseline if role=='baseline' else candidate,
                        max_output_tokens=min(512,max_tokens-report['tokens']))
                    tokens = result.get('usage',{}).get('total_tokens') if calls else 0
                    error = result.get('error_kind')
                    if tokens is None:
                        error = error or 'unaccounted_usage'
                    if type(tokens) is not int or tokens<0:
                        tokens=None
                        error=error or 'invalid_usage'
                    row = {'case_id':case['id'],'repeat':repeat,'role':role,'status':result['status'],
                        'reason':result.get('reason',''),'error_kind':error,'tokens':tokens,
                        'duration_s':time.monotonic()-started,'prompt_sha256':result.get('prompt_sha256'),
                        'requested':bool(calls)}
                    report['rows'].append(row)
                    report['tokens'] += tokens or 0
                    save()
                    if error or report['tokens']>max_tokens or time.monotonic()-began>total_timeout:
                        raise RuntimeError('Technical error, unknown usage or exhausted evaluation budget')
        report['status']='COMPLETE'
    except (Exception,KeyboardInterrupt) as exc:
        report.update(status='INCOMPLETE',error=f'{type(exc).__name__}: {exc}')
    report['elapsed_s']=time.monotonic()-began
    report['gate'] = assess(report,dataset)
    save()
    metrics = report['gate']['metrics']
    _atomic_write(directory/'report.md', '\n'.join([
        '# RSI paired evaluation','',f"Mode: {report['mode']} (fixtures are NOT model evidence)",
        f"Status: {report['status']}",f"Gate passed: {report['gate']['passed']}",
        f"Failed checks: {', '.join(report['gate']['failed'])}",
        '', '```json',json.dumps(metrics,indent=2),'```','',
        'Repeated fixed images measure prompt behavior, not robot end-to-end success.'])+'\n')
    return report
