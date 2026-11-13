"""用途：在模型调用前拒绝已知不支持能力和显式未知检查点，避免模型静默省略任务。"""

import re

from .schemas import ValidationError


class CapabilityError(ValidationError):
    code = 'UNSUPPORTED_CAPABILITY'


def check_capabilities(text, places, aliases=None):
    """Conservative patterns, not a general natural-language intent verifier."""
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
        raise ValidationError('instruction must contain 1–4000 characters')
    unsupported = (
        (r'背包|果盘|backpack|fruit\s*bowl', '静态自然语言入口尚未支持这类检查，请使用household任务或显式target'),
        (r'(?:打开|关闭|开|关)\s*(?:一下)?门|门(?:是否|有没|开闭|的状态)|door|工具箱|toolbox',
         '当前只支持红色标记检查，不支持门操作、门状态或工具箱语义识别'),
        (r'抓取|拿起|搬运|抓住|pick\s+up|grasp|manipulat', '当前没有机械臂抓取或搬运技能'),
        (r'自动建图|自主建图|探索未知|未知环境探索|\bslam\b', '当前只支持已知地图的命名地点导航'),
    )
    for pattern, reason in unsupported:
        if re.search(pattern, text, re.IGNORECASE):
            raise CapabilityError(reason + '；请明确改为支持的任务后再执行')
    known = set(places) | set(aliases or {})
    for match in re.finditer(r'checkpoint_[A-Za-z0-9_-]+|检查点\s*[A-Za-z]|[A-Za-z]\s*点', text):
        name = re.sub(r'\s+', '', match.group())
        if name not in known:
            raise CapabilityError(f'未知检查点：{name}；只支持已配置的地点和别名')
