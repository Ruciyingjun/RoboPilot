"""用途：确定性评估观测的时效、配置与来源；历史记录不能替代本次现场证据。"""

from datetime import datetime, timezone

# 工程策略阈值，不表示阈值内世界状态不会改变。
TTL_SECONDS = {'door_closed': 30, 'backpack_hanging': 300, 'fruit_bowl': 300,
               'toolbox': 300, 'red_marker': 300}


def assess_memory(observations, *, target, backend, context_id, mission_id=None,
                  place=None, now=None):
    """输入完整历史；只在相同检查点判定覆盖，不推断其他房间不存在。"""
    now = now or datetime.now(timezone.utc)
    candidates = [o for o in observations if o.get('target') == target
                  and o.get('backend') == backend and (place is None or o.get('place') == place)]
    def timestamp(o):
        try:
            value = datetime.fromisoformat(o['observed_at'].replace('Z', '+00:00'))
            return value if value.tzinfo else None
        except (KeyError, ValueError, TypeError):
            return None
    candidates.sort(key=lambda o: timestamp(o).timestamp() if timestamp(o) else float('-inf'), reverse=True)
    positive = next((o for o in candidates if o.get('status') == 'detected'), None)
    latest = candidates[0] if candidates else None
    reasons = []
    state = 'missing'
    age = None
    if latest:
        stamp = timestamp(latest)
        age = (now - stamp).total_seconds() if stamp else None
        state = 'historical_clue'
        if not context_id or latest.get('context_id') != context_id:
            state = 'context_mismatch'; reasons.append('配置来源缺失或地点配置摘要不同')
        elif age is None or age < 0:
            state = 'needs_refresh'; reasons.append('时间缺失、无时区或位于未来')
        elif latest.get('status') == 'unknown':
            state = 'needs_refresh'; reasons.append('最新观测无法确认，不能恢复旧的肯定结论')
        elif latest.get('status') not in ('detected', 'not_detected') or not latest.get('evidence_path'):
            state = 'needs_refresh'; reasons.append('缺少明确结果或图像证据引用')
        elif age > TTL_SECONDS.get(target, 300):
            state = 'expired'; reasons.append('超过目标类型的策略时效阈值')
        elif mission_id is not None and latest.get('mission_id') == mission_id:
            state = 'current_evidence'; reasons.append('本次任务、相同配置和检查点的近期明确观测')
        else:
            reasons.append('历史观测只可用于定位线索，当前状态任务必须现场复查')
        if positive and latest.get('place') == positive.get('place') and latest.get('status') == 'not_detected':
            reasons.append('同一检查点的后续否定观测覆盖历史肯定；不推断全局不存在')
            if state == 'historical_clue': state = 'superseded'
    else:
        reasons.append('没有匹配目标、后端和检查点的观测')
    def brief(o):
        return {k: o[k] for k in ('id', 'place', 'status', 'observed_at') if k in o} if o else None
    return {'state': state, 'can_answer_current': state == 'current_evidence',
            'requires_observation': state != 'current_evidence', 'reasons': reasons,
            'age_s': age, 'ttl_s': TTL_SECONDS.get(target, 300),
            'latest': brief(latest), 'last_seen': brief(positive),
            'scope': '单个检查点的条件判断；配置摘要不是SLAM地图或世界版本标识'}
