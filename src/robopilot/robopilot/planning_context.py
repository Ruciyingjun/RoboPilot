"""用途：校验中文地点别名、构造有来源的观测上下文，并计算计划和地图配置快照摘要。"""

import hashlib
import json
from dataclasses import asdict

from .schemas import ValidationError, load_yaml


def aliases_from_file(path, places):
    if path is None:
        return {}
    data = load_yaml(path)
    if (not isinstance(data, dict) or set(data) != {'version', 'aliases'}
            or type(data['version']) is not int or data['version'] != 1
            or not isinstance(data['aliases'], dict)):
        raise ValidationError('aliases: expected version=1 and aliases mapping')
    result = {}
    for alias, place in data['aliases'].items():
        if (not isinstance(alias, str) or not alias.strip() or alias != alias.strip()
                or len(alias) > 64 or any(c in alias for c in '\n\r，,；;。')):
            raise ValidationError('aliases: invalid alias name')
        if not isinstance(place, str) or place not in places:
            raise ValidationError(f'aliases: unknown place for {alias!r}')
        if alias in places and alias != place:
            raise ValidationError(f'aliases: {alias!r} conflicts with a canonical place')
        result[alias] = place
    return result


def planning_context(places, aliases=None, store=None, backend='ros'):
    aliases = aliases or {}
    context = {'backend': backend, 'places': list(places), 'aliases': aliases,
               'supported_targets': ['red_marker'], 'last_seen': None, 'recent_observations': []}
    if store:
        def summarize(obs):
            return {k: obs[k] for k in ('id', 'place', 'target', 'status', 'observed_at')}
        from .memory_validity import assess_memory
        context['memory_validity'] = (store.assess_memory('red_marker', backend, digest(places_snapshot(places)))
            if hasattr(store, 'assess_memory') else assess_memory(store.history('red_marker', backend, 1000),
                target='red_marker', backend=backend, context_id=digest(places_snapshot(places))))
        last = store.last_seen('red_marker', backend)
        if last:
            context['last_seen'] = summarize(last)
        context['recent_observations'] = [summarize(o) for o in store.history('red_marker', backend, 10)]
    return context


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                         separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def places_snapshot(places):
    return {name: asdict(pose) for name, pose in places.items()}
