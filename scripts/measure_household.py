"""用途：预注册并执行六轮家居巡检实验，保存原始证据，严格评分与统计任务墙上耗时。"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ('backpack_hanging','door_closed','fruit_bowl')
ORDER = ('positive','negative','negative','positive','positive','negative')
PROFILES = {
    'positive': {'backpack_state':'hanging','door_state':'closed','fruit_state':'present'},
    'negative': {'backpack_state':'floor','door_state':'open','fruit_state':'empty'},
}


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


def active(domain):
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if f'ROS_DOMAIN_ID={domain}'.encode() in (p/'environ').read_bytes().split(b'\0'):
                found.append(int(p.name))
        except OSError:pass
    return found


def stop(process, domain):
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill();process.wait()
    # Domain was verified unused before launch; only this trial's descendants may be here.
    residual=active(domain)
    for sig in (signal.SIGTERM,signal.SIGKILL):
        for pid in active(domain):
            try:os.kill(pid,sig)
            except ProcessLookupError:pass
        time.sleep(.3)
    return {'launch_exit':process.returncode,'residual_before_cleanup':residual,'residual_after_cleanup':active(domain)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--base-domain',type=int,default=80)
    parser.add_argument('--summarize',action='store_true')
    args=parser.parse_args()
    output=args.output.resolve()
    if args.summarize:
        trials=json.loads((output/'trials.json').read_text())
        labels=json.loads((output/'clarity-labels.json').read_text()) if (output/'clarity-labels.json').exists() else {}
        result=score(trials,labels);write(output/'summary.json',result)
        (output/'report.md').write_text(render(result));print(json.dumps(result['metrics'],ensure_ascii=False,indent=2));return
    if not 1<=args.base_domain<=95:parser.error('Use base-domain 1–95')
    if any(active(d) for d in range(args.base_domain,args.base_domain+6)):
        parser.error('A selected ROS domain is already in use')
    from robopilot.llm_config import load_llm_config
    config=load_llm_config()  # Fail before any movement if paid visual service is not configured.
    output.mkdir(parents=True,exist_ok=False)
    files=[*Path(ROOT/'src/robopilot/robopilot').glob('*.py'),*Path(ROOT/'src/robopilot/launch').glob('*.py'),
           ROOT/'src/robopilot/config/places.home.yaml',ROOT/'robopilot']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    protocol={'created_utc':datetime.now(timezone.utc).isoformat(),'order':ORDER,'profiles':PROFILES,
        'repeats_per_profile':3,'instruction':'2,3,4','code_hashes':hashes,'model':config.model,'provider':config.provider,
        'time_boundary':'monotonic command submission through process exit, including failures, excluding simulation boot',
        'return_tolerance':{'xy_m':.35,'yaw_rad':.35},'expected_positive':dict.fromkeys(TARGETS,'detected'),
        'expected_negative':dict.fromkeys(TARGETS,'not_detected'),'unknown_is_success':False,
        'review':'assistant image readability review, non-blind; never change ground truth from model answer'}
    write(output/'protocol.json',protocol)
    trials=[]
    for i,profile in enumerate(ORDER):
        if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in hashes.items()):
            raise RuntimeError('Source changed during frozen experiment')
        trial_dir=output/f'trial-{i+1:02d}';trial_dir.mkdir()
        domain=args.base_domain+i
        env={**os.environ,'ROS_DOMAIN_ID':str(domain),'ROS_LOG_DIR':str(trial_dir/'ros-logs'),'PYTHONUNBUFFERED':'1'}
        trial={'id':f'trial-{i+1:02d}','profile':profile,'expected':dict.fromkeys(TARGETS,'detected' if profile=='positive' else 'not_detected'),
               'elapsed_s':None,'command_exit':None,'mission_path':None,'mission':None,'final_pose':None}
        print(trial['id'],profile,'starting simulation',flush=True)
        with (trial_dir/'simulation.log').open('w') as log:
            sim=subprocess.Popen(['ros2','launch',str(ROOT/'install/robopilot/share/robopilot/launch/simulation.launch.py'),
                'scene:=home','headless:=True','use_rviz:=False','initialize_home:=True',
                *[f'{k}:={v}' for k,v in PROFILES[profile].items()]],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                until=time.monotonic()+90
                while time.monotonic()<until:
                    if sim.poll() is not None:raise RuntimeError('simulation exited during boot')
                    if '"ready": true' in (trial_dir/'simulation.log').read_text():break
                    time.sleep(.25)
                else:raise TimeoutError('simulation readiness budget exhausted')
                print(trial['id'],'ready; task timer started',flush=True)
                mission_root=trial_dir/'missions'
                with (trial_dir/'task.log').open('w') as task_log:
                    began=time.perf_counter()
                    try:
                        task=subprocess.run([str(ROOT/'robopilot'),'check','--instruction','2,3,4',
                            '--output',str(mission_root)],input='y\n',text=True,env=env,cwd=ROOT,
                            stdout=task_log,stderr=subprocess.STDOUT,timeout=1050)
                        trial['command_exit']=task.returncode
                    finally:trial['elapsed_s']=round(time.perf_counter()-began,3)
                paths=list(mission_root.glob('*/mission.json'))
                if len(paths)!=1:raise RuntimeError('Expected exactly one mission record')
                trial['mission_path']=str(paths[0]);trial['mission']=json.loads(paths[0].read_text())
                code=("import json; from dataclasses import asdict; from robopilot.ros_adapter import RosNavigationBackend; "
                      "b=RosNavigationBackend();\ntry: print(json.dumps(asdict(b.prepare(10))))\nfinally: b.close()")
                pose=subprocess.run(['/usr/bin/python3','-c',code],env=env,cwd=ROOT,capture_output=True,text=True,timeout=20)
                (trial_dir/'final-pose.log').write_text(pose.stdout+pose.stderr)
                if pose.returncode==0:trial['final_pose']=json.loads(pose.stdout)
            except Exception as exc:
                trial['technical_error']=f'{type(exc).__name__}: {exc}'
            finally:
                trial['shutdown']=stop(sim,domain)
                # Preserve a completed/partial mission even after a technical error.
                if trial['mission'] is None:
                    paths=list((trial_dir/'missions').glob('*/mission.json'))
                    if len(paths)==1:
                        trial['mission_path']=str(paths[0]);trial['mission']=json.loads(paths[0].read_text())
        trials.append(trial);write(output/'trials.json',trials)
        result=score(trials);write(output/'summary.json',result);(output/'report.md').write_text(render(result))
        print(trial['id'],'done',trial.get('mission',{}).get('status') if trial['mission'] else trial.get('technical_error'),trial['elapsed_s'],flush=True)


if __name__=='__main__':
    main()
