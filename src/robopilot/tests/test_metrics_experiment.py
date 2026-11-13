"""用途：验证实验严格成功判定、未知/缺失不算成功及失败任务计时不被剔除。"""

import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('measure_household',Path(__file__).resolve().parents[3]/'scripts/measure_household.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def trial(actual='detected',elapsed=10):
    return {'id':'t1','profile':'positive','expected':dict.fromkeys(module.TARGETS,'detected'),
        'elapsed_s':elapsed,'command_exit':0,'final_pose':{'x':0,'y':0,'yaw':0},'mission_path':'/tmp/mission.json',
        'mission':{'status':'SUCCEEDED','start_pose':{'x':0,'y':0,'yaw':0},
            'steps':[{'action':'navigate','status':'SUCCEEDED'} for _ in range(3)]+[{'action':'return_to_start','status':'SUCCEEDED'}],
            'observations':[{'id':str(i),'target':t,'status':actual} for i,t in enumerate(module.TARGETS)]}}


@pytest.mark.parametrize('actual,success',[('detected',True),('unknown',False),('not_detected',False)])
def test_execution_success_is_not_sufficient(actual,success):
    data=trial(actual)
    labels={f't1/{i}':{'clear':True} for i in range(3)}
    result=module.score([data],labels)
    assert result['trials'][0]['success'] is success
    assert result['metrics']['visual_effective_rate']==(1 if success else 0)


def test_missing_observation_or_large_return_error_fails():
    data=trial();data['mission']['observations'].pop()
    assert module.score([data])['metrics']['e2e_successes']==0
    data=trial();data['final_pose']['x']=.36
    assert module.score([data])['metrics']['e2e_successes']==0


def test_failed_duration_included_and_unreviewed_images_not_scored():
    good=trial(elapsed=20);bad=trial('unknown',elapsed=10);bad['id']='t2'
    result=module.score([good,bad])['metrics']
    assert result['all_task_time']['mean_s']==15
    assert result['successful_task_time']['mean_s']==20
    assert result['visual_effective_rate'] is None
