"""用途：从有限中文任务表达提取独立约束，检查遗漏、顺序和简单否定，拒绝不支持的条件任务。"""

import re
from dataclasses import dataclass

from .schemas import ValidationError


class ClarificationRequired(ValidationError):
    code = 'CLARIFICATION_REQUIRED'


class MemoryUnavailable(ClarificationRequired):
    code = 'MEMORY_UNAVAILABLE'


class IntentMismatch(ValidationError):
    code = 'INTENT_MISMATCH'


def plan_signature(plan):
    return [(s.action, s.place, s.target) for s in plan.steps]


@dataclass
class IntentContract:
    required: list
    forbidden_places: list
    forbid_return: bool = False

    def to_dict(self):
        return {'required': [list(s) for s in self.required],
                'forbidden_places': self.forbidden_places, 'forbid_return': self.forbid_return,
                'scope': '有限中文地点/检查/返航/简单否定；不是通用自然语言语义验证'}

    def validate(self, plan):
        actual = plan_signature(plan)
        if any(s.place in self.forbidden_places for s in plan.steps):
            raise IntentMismatch('计划包含明确禁止访问的地点')
        if self.forbid_return and any(s.action == 'return_to_start' for s in plan.steps):
            raise IntentMismatch('用户明确不要求返航，计划却包含返航')
        if actual != self.required:
            raise IntentMismatch(f'计划动作/地点/顺序不完整或多余；required={self.required}, actual={actual}')


def extract_contract(text, places, aliases=None, last_seen=None):
    """Grounded finite patterns. Gold benchmark labels are never read here."""
    if re.search(r'如果|假如|否则|一旦|除非|直到|若|视情况|\b(?:if|unless|when)\b', text, re.I):
        raise ClarificationRequired('当前执行器不支持条件分支；请明确本次要执行的线性步骤')
    names = {name: name for name in places}
    names.update(aliases or {})
    pattern = '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    clauses = [s.strip() for s in re.split(r'[，,；;。]|(?=然后|接着|随后|最后|再(?:去|到|检查|返回|回到))', text) if s.strip()]
    required, forbidden = [], []
    current = None
    forbid_return = False
    for clause in clauses:
        negative = bool(re.search(r'不要|不用|无需|不必|别|禁止|不去', clause))
        locations = [names[m.group()] for m in re.finditer(pattern, clause)] if pattern else []
        historical = bool(re.search(r'(?:上次|最近一次).*(?:发现|看到).*(?:地方|地点|位置)', clause))
        if historical:
            if not last_seen or last_seen.get('place') not in places:
                raise MemoryUnavailable('没有当前地图和后端下可用的历史发现地点，请先执行明确地点的检查')
            if locations:
                raise ClarificationRequired('同一片段混合历史地点与命名地点，请分开描述执行顺序')
            locations = [last_seen['place']]
        returns = bool(re.search(r'返回起点|回到起点|回起点|回到出发点|返回出发点', clause))
        inspection = bool(re.search(r'检查|查看|看看|看下|看一看|确认|巡检|复查|复检', clause))
        if negative:
            if len(locations)>1 and re.search(r'先去|只去|请去|前往', clause):
                raise ClarificationRequired('否定与访问要求混在同一片段，请用逗号分开并明确顺序')
            if locations and inspection:
                raise ClarificationRequired('暂不支持地点与检查动作混合的否定；请明确哪些地点允许访问和检查')
            if locations:
                forbidden.extend(locations)
            elif returns:
                forbid_return = True
            else:
                raise ClarificationRequired('否定目标不明确，请明确禁止的地点或返航动作')
            continue
        if not locations and not inspection and not returns:
            if clause not in ('谢谢','谢谢你'):
                raise ClarificationRequired('存在无法确定动作的片段：' + clause)
            continue
        for place in locations:
            required.append(('navigate', place, None))
            current = place
            if inspection:
                required.append(('inspect', place, 'red_marker'))
        if inspection and not locations:
            if current is None:
                raise ClarificationRequired('未明确检查地点，请给出地点名称或有效历史地点')
            required.append(('inspect', current, 'red_marker'))
        if returns:
            required.append(('return_to_start', None, None))
            current = None
    if not required:
        raise ClarificationRequired('没有可确定的执行步骤，请明确地点、动作和顺序')
    if any(place in forbidden for action, place, _ in required if action == 'navigate'):
        raise ClarificationRequired('同一地点同时被要求访问和禁止访问，请澄清')
    if forbid_return and any(action == 'return_to_start' for action, _, _ in required):
        raise ClarificationRequired('返航要求互相矛盾，请澄清')
    return IntentContract(required, list(dict.fromkeys(forbidden)), forbid_return)
