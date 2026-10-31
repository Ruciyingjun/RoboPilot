"""用途：对固定人工标注指令进行只规划评测，分开统计模型候选、应用拒绝、完整性与技术错误。"""

import json
import re
import statistics
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .capabilities import CapabilityError
from .intent import ClarificationRequired, IntentMismatch
from .llm_client import LLMError
from .planner import PlanningRefusal, generate_plan
from .planning_context import digest, places_snapshot
from .planning_io import save_plan
from .schemas import ValidationError, decode_json
from .storage import _atomic_write


def signature(data):
    return [(s['action'], s.get('place'), s.get('target')) for s in data['steps']]


class FixtureMemory:
    """Explicit synthetic observation context; never writes into real robot memory."""
    def __init__(self, fixture):
        self.fixture = fixture

    def last_seen(self, target, backend='ros'):
        if self.fixture == 'none':
            return None
        place = 'checkpoint_b' if self.fixture == 'seen_b' else 'checkpoint_a'
        return {'id': 'benchmark_detected_' + place, 'place': place, 'target': 'red_marker',
                'status': 'detected', 'observed_at': '2026-10-01T00:00:00+00:00'}

    def history(self, target, backend='ros', limit=10):
        seen = self.last_seen(target, backend)
        observations = [seen] if seen else []
        if self.fixture == 'seen_a_then_missing':
            observations.insert(0, dict(seen, id='benchmark_not_detected_a', status='not_detected',
                                         observed_at='2026-10-02T00:00:00+00:00'))
        return observations[:limit]


def load_cases(path, places):
    data = decode_json(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or set(data) - {'version', '$comment', 'cases'}
            or type(data.get('version')) is not int or data['version'] != 1
            or not isinstance(data.get('cases'), list) or not 1 <= len(data['cases']) <= 100):
        raise ValidationError('benchmark requires version=1 and 1–100 cases')
    seen = set()
    for case in data['cases']:
        if (not isinstance(case, dict) or set(case) - {'id','category','instruction','memory','expected','reason'}
                or not {'id','category','instruction','memory','expected'} <= set(case)):
            raise ValidationError('Invalid benchmark case fields')
        name = case['id']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', name) or name in seen:
            raise ValidationError('Case IDs must be unique ASCII identifiers')
        seen.add(name)
        if not isinstance(case['instruction'], str) or not 1 <= len(case['instruction']) <= 4000:
            raise ValidationError('Invalid benchmark instruction')
        if not isinstance(case['category'], str) or not case['category']:
            raise ValidationError('Invalid benchmark category')
        if case['memory'] not in ('none','seen_a','seen_b','seen_a_then_missing'):
            raise ValidationError('Unknown synthetic memory fixture')
        expected = case['expected']
        if not isinstance(expected, dict) or expected.get('decision') not in ('accept', 'reject'):
            raise ValidationError('Expected decision must be accept/reject')
        if expected['decision'] == 'accept':
            if set(expected) != {'decision','steps'} or not isinstance(expected['steps'], list) or not expected['steps']:
                raise ValidationError('Accepted cases need a nonempty hand-authored steps list')
            for step in expected['steps']:
                if not isinstance(step, dict):
                    raise ValidationError('Invalid expected step')
                action = step.get('action')
                if action == 'return_to_start' and set(step) == {'action'}:
                    continue
                fields = {'action','place','target'} if action == 'inspect' else {'action','place'}
                if (action not in ('navigate','inspect') or set(step) != fields
                        or step.get('place') not in places
                        or (action == 'inspect' and step.get('target') != 'red_marker')):
                    raise ValidationError('Expected step contains unsupported action/place/target')
        elif set(expected) != {'decision'}:
            raise ValidationError('Rejected cases cannot include executable expected steps')
    return data


def _rate(passed, total):
    return {'passed': passed, 'total': total, 'rate': passed / total if total else None}


def summarize(results):
    accepts = [r for r in results if r['expected']['decision'] == 'accept']
    rejects = [r for r in results if r['expected']['decision'] == 'reject']
    responded = [r for r in results if r['audit'].get('attempts') and r['planner']=='llm']
    responded_accepts = [r for r in responded if r['expected']['decision']=='accept']
    called = [r for r in results if r['audit'].get('model_request_attempts', 0)]
    durations = [r['duration_s'] for r in called]
    tokens = Counter()
    for r in results:
        for attempt in r['audit'].get('attempts', []):
            tokens.update(attempt.get('usage', {}))
    def first(r):
        return r['audit']['attempts'][0]
    return {
        'case_pass': _rate(sum(r['passed'] for r in results), len(results)),
        'accepted_task_complete': _rate(sum(r['passed'] for r in accepts), len(accepts)),
        'correct_rejection': _rate(sum(r['passed'] for r in rejects), len(rejects)),
        'first_model_plan_schema': _rate(sum(first(r).get('protocol_valid') is True for r in responded), len(responded)),
        'first_model_task_complete_on_accept_cases': _rate(sum(
            first(r).get('candidate') is not None and
            signature(first(r)['candidate']) == signature(r['expected']) for r in responded_accepts), len(responded_accepts)),
        'decision_counts': dict(Counter(r['decision'] for r in results)),
        'error_kinds': dict(Counter(r.get('error_kind','unspecified') for r in results if r['decision']=='error')),
        'precheck_rejections': sum(r['decision']=='reject' and r['audit'].get('stage') in
                                   ('capability_check','intent_contract') for r in results),
        'model_refusals': sum(r['audit'].get('error_code')=='MODEL_REFUSAL' for r in results),
        'model_request_attempts': sum(r['audit'].get('model_request_attempts',0) for r in results),
        'reported_usage': dict(tokens),
        'model_case_duration_s_mean': round(statistics.mean(durations),3) if durations else None,
        'model_case_duration_s_median': round(statistics.median(durations),3) if durations else None,
        'model_case_duration_s_max': round(max(durations),3) if durations else None,
    }


def render_benchmark(report):
    lines = ['<!-- 用途：记录固定合成指令的规划评测结果；不执行机器人，不代表导航或视觉成功率。 -->',
             '# RoboPilot 规划评测', '', f"- 规划器：{report['planner']}",
             '- 记忆：人工构造的仿真观测夹具，不读取真实机器人记忆。',
             f"- 状态：{report['status']}；完成 {len(report['results'])}/{report['total_cases']} 个样本。",
             '- 人工预期与意图约束实现独立；模型会收到应用提取的约束，因此结果评估的是整条规划管线。', '',
             '| 指标 | 通过/总数 | 比例 |', '|---|---:|---:|']
    for name, value in report['metrics'].items():
        if isinstance(value, dict) and 'rate' in value:
            rate = f"{value['rate']:.1%}" if value['rate'] is not None else 'N/A'
            lines.append(f"| {name} | {value['passed']}/{value['total']} | {rate} |")
    lines += ['', '| 样本 | 类别 | 预期 | 最终决策 | 通过 | 原因 |', '|---|---|---|---|---|---|']
    for r in report['results']:
        reason = str(r.get('error','')).replace('|','/').replace('\n',' ')
        lines.append(f"| {r['id']} | {r['category']} | {r['expected']['decision']} | {r['decision']} | {r['passed']} | {reason} |")
    lines += ['', '完整指令、人工预期、首次候选、修复和 token 用量见同目录 summary.json 与 cases/。',
              '前置拒绝不计作模型拒绝；网络/格式技术错误不计作正确拒绝。模型明确 refusal 不是合法计划，故不计入计划 schema 通过率。',
              '少量固定样本不是泛化成功率，token 仅累计服务报告值，延迟是包含修复的单案例总规划时间。', '']
    return '\n'.join(lines)


def run_benchmark(cases_path, places, aliases, output, planner='rules', response_mode='json',
                  repair_attempts=1, selected=None, repeats=1, on_event=print):
    data = load_cases(cases_path, places)
    if type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValidationError('repeats must be 1–5')
    cases = data['cases']
    if selected:
        if not set(selected) <= {c['id'] for c in cases}:
            raise ValidationError('Unknown selected case ID')
        cases = [c for c in cases if c['id'] in selected]
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:8]
    directory = Path(output) / run_id
    (directory/'cases').mkdir(parents=True, exist_ok=False)
    report = {'version':1, 'id':run_id, 'planner':planner, 'response_mode':response_mode,
              'cases_sha256':digest(data), 'places_sha256':digest(places_snapshot(places)),
              'memory_source':'synthetic_fixture', 'robot_execution':False, 'status':'RUNNING',
              'total_cases':len(cases)*repeats, 'results':[], 'metrics':{}}
    def save():
        report['metrics'] = summarize(report['results'])
        report['metrics']['case_coverage'] = _rate(len(report['results']), report['total_cases'])
        _atomic_write(directory/'summary.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        _atomic_write(directory/'report.md',render_benchmark(report))
    save()
    try:
        for repeat in range(repeats):
            for case in cases:
                audit, plan, error, decision, error_kind = {}, None, '', 'error', None
                try:
                    plan = generate_plan(case['instruction'], places, aliases, FixtureMemory(case['memory']),
                                         'ros', planner, audit, response_mode, repair_attempts)
                    decision = 'accept'
                except (CapabilityError, ClarificationRequired, IntentMismatch, PlanningRefusal) as exc:
                    decision, error = 'reject', str(exc)
                except ValidationError as exc:
                    error, error_kind = f'{type(exc).__name__}: {exc}', 'plan_validation'
                except LLMError as exc:
                    error, error_kind = f'{type(exc).__name__}: {exc}', 'technical'
                except Exception as exc:
                    error, error_kind = f'{type(exc).__name__}: {exc}', 'internal'
                passed = decision == case['expected']['decision']
                if decision == 'accept':
                    passed = passed and signature(plan.to_dict()) == signature(case['expected'])
                result = {'id':case['id'], 'repeat':repeat+1, 'category':case['category'], 'planner':planner,
                          'instruction':case['instruction'], 'memory':case['memory'], 'expected':case['expected'],
                          'decision':decision, 'passed':bool(passed), 'error':error, 'error_kind':error_kind, 'audit':audit,
                          'duration_s':audit.get('duration_s',0), 'plan':plan.to_dict() if plan else None}
                report['results'].append(result)
                stem = directory/'cases'/f"{case['id']}_r{repeat+1}"
                _atomic_write(stem.with_suffix('.result.json'),json.dumps(result,ensure_ascii=False,indent=2)+'\n')
                if plan:
                    audit['benchmark_memory_source'] = 'synthetic_fixture'
                    save_plan(stem.with_suffix('.plan.json'), plan, audit)
                on_event(f"[{len(report['results'])}/{report['total_cases']}] {case['id']}: {decision}, pass={passed}")
                save()
                if error_kind in ('technical','internal'):
                    report['status'] = 'STOPPED_ON_TECHNICAL_ERROR'
                    return directory, report
        report['status'] = 'COMPLETE'
        return directory, report
    finally:
        if report['status']=='RUNNING':
            report['status']='INTERRUPTED'
        save()
