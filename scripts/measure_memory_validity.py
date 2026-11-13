"""用途：运行可复现的离线配对记忆消融；不冒充Gazebo、VLM或实际导航耗时。"""

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from robopilot.memory_validity import assess_memory


def scenarios():
    now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
    def obs(status='detected', age=5, **fields):
        return dict(id='fixture', target='door_closed', backend='mock', place='door_check',
                    observed_at=(now-timedelta(seconds=age)).isoformat(), status=status,
                    context_id='home-v1', mission_id='past', evidence_path='fixture.png', **fields)
    cases = []
    def add(name, history, truth, expected_reuse=False):
        cases.append(dict(name=name, history=history, truth=truth, expected_reuse=expected_reuse))
    add('recent_but_door_opened', [obs()], False)
    add('recent_unchanged', [obs()], True)
    add('expired_changed', [obs(age=600)], False)
    add('expired_unchanged', [obs(age=600)], True)
    add('later_negative', [obs(age=20), obs('not_detected')], False)
    add('later_unknown_changed', [obs(age=20), obs('unknown')], False)
    add('later_unknown_unchanged', [obs(age=20), obs('unknown')], True)
    x=obs(); x['context_id']='another-layout'; add('configuration_changed', [x], False)
    x=obs(); del x['context_id']; add('legacy_without_context', [x], False)
    x=obs(); x['evidence_path']=None; add('missing_evidence', [x], False)
    add('future_timestamp', [obs(age=-20)], False)
    add('no_memory', [], False)
    x=obs(); x['mission_id']='current'; add('current_positive', [x], True, True)
    x=obs('not_detected'); x['mission_id']='current'; add('current_negative', [x], False, True)
    return now, cases


def run():
    now, cases = scenarios()
    rows=[]
    for case in cases:
        for mode in ('last_positive_baseline', 'validity_gate', 'existing_always_refresh'):
            began=time.perf_counter_ns()
            assessment=assess_memory(case['history'], target='door_closed', backend='mock',
                context_id='home-v1', mission_id='current', place='door_check', now=now)
            positive=next((o for o in reversed(case['history']) if o['status']=='detected'),None)
            if mode=='last_positive_baseline':
                reuse=positive is not None
                answer=True if reuse else case['truth']
            else:
                reuse=assessment['can_answer_current'] if mode=='validity_gate' else False
                answer=assessment['latest']['status']=='detected' if reuse else case['truth']
            rows.append(dict(case=case['name'], mode=mode, truth=case['truth'], answer=answer,
                correct=answer==case['truth'], reused=reuse, refreshes=int(not reuse),
                wrong_reuse=bool(reuse and answer!=case['truth']),
                policy_runtime_us=(time.perf_counter_ns()-began)/1000,
                validity=assessment if mode=='validity_gate' else None))
    summary={}
    for mode in ('last_positive_baseline','validity_gate','existing_always_refresh'):
        selected=[r for r in rows if r['mode']==mode]
        summary[mode]=dict(tasks=len(selected), correct=sum(r['correct'] for r in selected),
            wrong_reuse=sum(r['wrong_reuse'] for r in selected),
            refreshes=sum(r['refreshes'] for r in selected),
            mean_policy_runtime_us=sum(r['policy_runtime_us'] for r in selected)/len(selected))
    return dict(protocol={'kind':'deterministic_offline_paired_ablation', 'cases':len(cases),
        'clock':now.isoformat(), 'refresh_model':'oracle: fresh inspection always returns fixture truth',
        'baseline':'deliberately permissive last-positive reuse, NOT previous production behavior',
        'limitations':'hand-authored fixtures, perfect fresh observation, no ROS/API; runtime is offline Python policy time, not task time'},
        cases=cases, rows=rows, summary=summary)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='runs/memory-validity-20261031')
    args=parser.parse_args()
    root=Path(args.output); root.mkdir(parents=True, exist_ok=False)
    result=run()
    (root/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    lines=['# 记忆有效性离线配对消融', '', '14个人工场景；复查使用理想真值，不代表视觉或机器人端到端成功率。', '',
           '|策略|正确任务|错误复用|复查次数|平均策略耗时μs|','|---|---:|---:|---:|---:|']
    for mode,s in result['summary'].items():
        lines.append(f"|{mode}|{s['correct']}/{s['tasks']}|{s['wrong_reuse']}|{s['refreshes']}|{s['mean_policy_runtime_us']:.2f}|")
    lines += ['', '基线主动允许历史肯定直接回答当前状态；原生产流程已强制复查。新增判别器相对原流程的价值是显式解释、上下文隔离及可审计约束，不能声称修复了原系统已经存在的错误复用。',
              '实际任务耗时尚未进行ROS配对测量；不能把策略微秒耗时或理想复查真值包装为机器人性能。']
    (root/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
