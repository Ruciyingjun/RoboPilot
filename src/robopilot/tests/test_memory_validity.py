"""用途：验证记忆门控边界、同地点覆盖、时效、后端隔离及离线消融评分。"""

import importlib.util
from pathlib import Path

from robopilot.memory_validity import assess_memory

spec=importlib.util.spec_from_file_location('measure_memory', Path(__file__).resolve().parents[3]/'scripts/measure_memory_validity.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_fixture_contracts():
    now,cases=module.scenarios()
    for case in cases:
        result=assess_memory(case['history'],target='door_closed',backend='mock',context_id='home-v1',
                             mission_id='current',place='door_check',now=now)
        assert result['can_answer_current']==case['expected_reuse'], case['name']


def test_scope_and_backend():
    now,cases=module.scenarios()
    obs=cases[-2]['history'][0]
    for backend,place in [('ros','door_check'),('mock','other')]:
        result=assess_memory([obs],target='door_closed',backend=backend,context_id='home-v1',
                            mission_id='current',place=place,now=now)
        assert result['state']=='missing'


def test_unknown_does_not_restore_old_positive():
    now,cases=module.scenarios()
    history=cases[5]['history']
    result=assess_memory(history,target='door_closed',backend='mock',context_id='home-v1',now=now)
    assert result['state']=='needs_refresh'
    assert result['last_seen']['status']=='detected'
    assert result['latest']['status']=='unknown'


def test_ablation_scoring():
    s=module.run()['summary']
    assert s['validity_gate']['wrong_reuse']==0
    assert s['validity_gate']['correct']==14
    assert s['last_positive_baseline']['wrong_reuse']>0
    assert s['existing_always_refresh']['correct']==14
    assert s['validity_gate']['refreshes']==12


def test_sqlite_roundtrip_and_newer_negative(tmp_path):
    from robopilot.storage import MissionStore
    now,cases=module.scenarios()
    history=cases[4]['history']
    for n,o in enumerate(history):
        o['id']=str(n); o['mission_id']='past'
    store=MissionStore(tmp_path)
    try:
        store.save(dict(id='past',name='fixture',backend='mock',status='SUCCEEDED',
            updated_at=now.isoformat(),created_at=now.isoformat(),steps=[],observations=history))
        result=store.assess_memory('door_closed','mock','home-v1',place='door_check',now=now)
        assert result['state']=='superseded'
        assert result['latest']['status']=='not_detected'
        assert store.last_seen('door_closed','mock')['status']=='detected'
    finally:
        store.close()
