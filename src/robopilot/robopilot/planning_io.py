"""用途：保存规划审计文件，校验执行计划和地点配置是否与规划时一致，防止静默使用旧计划。"""

import json
from pathlib import Path

from .planning_context import digest, places_snapshot
from .schemas import ValidationError, decode_json
from .storage import _atomic_write


def audit_path(path):
    return Path(path).with_suffix('.planning.json')


def save_audit(path, audit):
    sidecar = audit_path(path)
    if sidecar == Path(path) or Path(path).suffix != '.json':
        raise ValidationError('Plan filename must end with .json, but not .planning.json')
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(sidecar, json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def save_plan(path, plan, audit):
    save_audit(path, audit)
    _atomic_write(Path(path), json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + '\n')


def load_audit(path, plan, places):
    sidecar = audit_path(path)
    if not sidecar.exists():
        return {'planner': 'json_file', 'source': str(Path(path).resolve())}
    try:
        audit = decode_json(sidecar.read_text(encoding='utf-8'))
        if not isinstance(audit, dict) or audit.get('status') != 'VALIDATED':
            raise ValidationError('Planning audit is not VALIDATED; generate a new plan')
        if audit.get('plan_sha256') != digest(plan.to_dict()):
            raise ValidationError('Plan differs from its planning audit; regenerate or review it as a manual plan')
        if audit.get('places_sha256') != digest(places_snapshot(places)):
            raise ValidationError('Place coordinates changed since planning; generate a new plan')
        return audit
    except (OSError, UnicodeError) as exc:
        raise ValidationError('Cannot read planning audit') from exc
