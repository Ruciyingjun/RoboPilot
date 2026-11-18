"""用途：对既有六轮家居巡检证据评分与统计；不启动仿真。"""

import argparse
import json
import math
from pathlib import Path
import statistics

TARGETS = ('backpack_hanging','door_closed','fruit_bowl')
PROFILES = ('positive', 'negative')  # Historical score groups; no simulator launch configuration.


def write(path, data):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temp.replace(path)


def durations(values):
    values=[v for v in values if v is not None]
    return {'n':len(values), 'mean_s':statistics.mean(values) if values else None,
            'median_s':statistics.median(values) if values else None,
            'min_s':min(values) if values else None,'max_s':max(values) if values else None}


def score(trials, labels=None):
    """No missing/unknown inspection can make an end-to-end task successful."""
    labels=labels or {}
    rows=[]; visual=[]
    for trial in trials:
        mission=trial.get('mission') or {}
        obs=mission.get('observations',[])
        expected=trial['expected']
        moves=[s for s in mission.get('steps',[]) if s['action'] in ('navigate','return_to_start')]
        complete=(mission.get('status')=='SUCCEEDED' and len(moves)==4
                  and all(s['status']=='SUCCEEDED' for s in moves)
                  and sum(s['action']=='return_to_start' for s in moves)==1)
        matches=(len(obs)==3 and {o['target'] for o in obs}==set(TARGETS)
                 and all(o['status']==expected[o['target']] for o in obs))
        start,end=mission.get('start_pose'),trial.get('final_pose')
        xy=yaw=None
        if start and end:
            xy=math.hypot(end['x']-start['x'],end['y']-start['y'])
            yaw=abs(math.atan2(math.sin(end['yaw']-start['yaw']),math.cos(end['yaw']-start['yaw'])))
        returned=xy is not None and xy<=.35 and yaw<=.35
        success=bool(complete and matches and returned and trial.get('command_exit')==0)
        rows.append({'trial':trial['id'],'profile':trial['profile'],'execution_status':mission.get('status','NOT_STARTED'),
                     'success':success,'elapsed_s':trial.get('elapsed_s'),'return_xy_error_m':xy,'return_yaw_error_rad':yaw})
        for o in obs:
            key=trial['id']+'/'+o['id']
            label=labels.get(key,{})
            visual.append({'key':key,'trial':trial['id'],'target':o['target'],'expected':expected[o['target']],
                'actual':o['status'],'clear':label.get('clear'),'review_note':label.get('note',''),
                'correct':o['status']==expected[o['target']],
                'image':str(Path(trial['mission_path']).parent/o['evidence_path']) if o.get('evidence_path') else None})
    clear=[v for v in visual if v['clear'] is True]
    return {'trials':rows,'observations':visual,'metrics':{
        'planned_trials':6,'completed_trial_records':len(trials),'e2e_successes':sum(r['success'] for r in rows),
        'e2e_denominator':len(trials),'e2e_rate':sum(r['success'] for r in rows)/len(rows) if rows else None,
        'planned_inspections_in_recorded_trials':3*len(trials),'actual_observations':len(visual),
        'reviewed_observations':sum(v['clear'] is not None for v in visual),'clear_observations':len(clear),
        'visual_correct_clear':sum(v['correct'] for v in clear),
        'visual_effective_rate':sum(v['correct'] for v in clear)/len(clear) if clear else None,
        'unknown_clear':sum(v['actual']=='unknown' for v in clear),
        'all_task_time':durations([r['elapsed_s'] for r in rows]),
        'successful_task_time':durations([r['elapsed_s'] for r in rows if r['success']]),
        'time_by_profile':{p:durations([r['elapsed_s'] for r in rows if r['profile']==p]) for p in PROFILES}}}


def render(result):
    m=result['metrics']
    lines=['<!-- 用途：汇总本轮固定家居任务实验的真实记录与三项指标。 -->','# 家居任务实验结果','',
           '固定顺序 positive/negative/negative/positive/positive/negative；每轮重启世界。原始计划见protocol.json。',
           '这是固定目录任务执行链路，不测LLM搜索规划；图像清晰度须独立于VLM结果复核，见clarity-labels.json。','',
           f"端到端成功：{m['e2e_successes']}/{m['e2e_denominator']}。视觉有效判定：{m['visual_correct_clear']}/{m['clear_observations']}（未复核不计）。",
           f"已记录{m['completed_trial_records']}/6轮，实际观测{m['actual_observations']}，清晰度已复核{m['reviewed_observations']}张。",'',
           '任务墙上时间从提交巡检命令到进程退出，包含初始化、视觉API、I/O、返航；不含仿真启动和人工确认等待。',
           '所有已提交任务含失败样本；成功子集另列，不能只挑成功计时。返航误差为AMCL估计，不是真值定位精度。','',
           '|任务|场景|程序状态|严格成功|耗时秒|返航误差米|','|---|---|---|---|---|---|']
    for r in result['trials']:
        lines.append('| '+' | '.join(str(r[k]) for k in ('trial','profile','execution_status','success','elapsed_s','return_xy_error_m'))+' |')
    lines+=['','```json',json.dumps(m,ensure_ascii=False,indent=2),'```','','|任务|目标|预期|实际|画面可判断|','|---|---|---|---|---|']
    for v in result['observations']:
        lines.append(f"|{v['trial']}|{v['target']}|{v['expected']}|{v['actual']}|{v['clear']}|")
    lines+=['','样本量仅6次任务，同地图同模型下的重复测量，不代表独立泛化、真机或不同负载性能。模型别名并非固定权重版本。']
    return '\n'.join(lines)+'\n'



def main():
    parser = argparse.ArgumentParser(description='对已有家居巡检实验结果评分；不启动仿真或调用 API。')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--summarize', action='store_true', help='兼容旧汇总命令')
    args = parser.parse_args()
    output = args.output.resolve()
    trials = json.loads((output/'trials.json').read_text())
    labels_path = output/'clarity-labels.json'
    labels = json.loads(labels_path.read_text()) if labels_path.exists() else {}
    result = score(trials, labels)
    write(output/'summary.json', result)
    (output/'report.md').write_text(render(result))
    print(json.dumps(result['metrics'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
