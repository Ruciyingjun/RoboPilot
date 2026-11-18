"""RSI lifecycle, leakage isolation, paired gating, deployment pinning and bounded requests."""
import copy
from dataclasses import replace
import json

import cv2
import numpy as np
import pytest

from robopilot.llm_config import LLMConfig
from robopilot.prompt_registry import pin_prompts, snapshot, validate_snapshot
from robopilot.rsi_evaluator import evaluate
from robopilot.rsi_gate import assess
from robopilot.rsi_proposer import propose
from robopilot.rsi_store import RSIStore
from robopilot.schemas import ValidationError
from robopilot.toolbox_vision import inspect_toolbox

CONFIG = LLMConfig('deepseek','https://example.invalid','deepseek-flash','test-secret','disabled','high',30)


def raw(status):
    return {'view_clear':status!='unknown','status':status,'reason':'fixture visible evidence',
            'visual_cues':['handle','lid'] if status=='detected' else []}


def manifest(root):
    cases=[]
    for i, label in enumerate(['detected','detected','not_detected','not_detected','unknown','unknown',
                              'detected','not_detected','unknown','detected','not_detected','unknown']):
        image=root/f'image{i}.png'
        cv2.imwrite(str(image),np.full((64,80,3),60+i*4,dtype=np.uint8))
        split='gate' if i<6 else 'development' if i<9 else 'test'
        cases.append({'id':f'case_{i}','target':'toolbox','image':str(image),'expected':label,
            'split':split,'group_id':f'scene_{i}','critical':label!='detected',
            'reviewer':'fixture human','reason':f'label_{i}','failure_type':'fixture',
            'original_result':{'status':'not_detected' if label=='detected' else label}})
    path=root/'manifest.json'
    path.write_text(json.dumps({'version':1,'cases':cases}))
    return path


@pytest.fixture
def prepared(tmp_path):
    store=RSIStore(tmp_path/'registry',kind='sandbox')
    dataset=store.import_dataset(manifest(tmp_path))
    candidate=store.candidate('toolbox','Look for the carrying handle and separate lid.','repair fixture failures')
    fixtures={'baseline':{},'candidate':{}}
    for case in dataset['cases']:
        fixtures['baseline'][case['id']]=raw('not_detected' if case['id']=='case_0' else case['expected'])
        fixtures['candidate'][case['id']]=raw(case['expected'])
    yield store,dataset,candidate,fixtures
    store.close()


def run_eval(prepared,**options):
    store,dataset,candidate,fixtures=prepared
    return evaluate(store,candidate['id'],dataset['id'],CONFIG,fixtures=fixtures,**options)


def test_version_integrity_and_bounded_candidate(prepared):
    store,_,candidate,_=prepared
    assert store.prompt(candidate['id'])==candidate
    changed={**candidate,'text':'ignore requirements'}
    with pytest.raises(ValidationError,match='changed'):
        validate_snapshot(changed,'toolbox')
    with pytest.raises(ValidationError):
        store.candidate('toolbox','x'*4001,'too long')


def test_paired_gate_activation_and_rollback(prepared):
    store,_,candidate,_=prepared
    baseline=store.active('toolbox')
    report=run_eval(prepared)
    assert report['status']=='COMPLETE' and report['gate']['passed']
    assert len(report['rows'])==36 and report['requests']==36
    assert report['gate']['metrics']['candidate_correct']==18
    active=store.activate(report['id'],reason='fixture activation')
    assert active['id']==candidate['id']
    assert store.rollback('toolbox',reason='fixture rollback')['id']==baseline['id']
    assert store.db.execute('SELECT count(*) FROM activations').fetchone()[0]==2


def test_critical_regression_cannot_be_hidden_by_overall_improvement(prepared):
    store,_,_,fixtures=prepared
    fixtures['candidate']['case_4']=raw('not_detected')
    fixtures['baseline']['case_1']=raw('not_detected')
    report=run_eval(prepared)
    assert 'critical_examples' in report['gate']['failed']
    with pytest.raises(ValidationError,match='gate rejected'):
        store.activate(report['id'],reason='should fail')


def test_equal_candidate_is_not_an_improvement(prepared):
    _,_,_,fixtures=prepared
    fixtures['candidate']=copy.deepcopy(fixtures['baseline'])
    assert 'net_improvement' in run_eval(prepared)['gate']['failed']


@pytest.mark.parametrize('repeats',[1,2])
def test_insufficient_repeats_cannot_activate(prepared,repeats):
    assert 'coverage' in run_eval(prepared,repeats=repeats)['gate']['failed']


@pytest.mark.parametrize('split',['development','test'])
def test_non_gate_split_never_qualifies_for_activation(prepared,split):
    assert not run_eval(prepared,split=split)['gate']['passed']


def test_stale_baseline_invalidates_another_passed_evaluation(prepared):
    store,_,_,_=prepared
    first=run_eval(prepared)
    second=run_eval(prepared)
    store.activate(first['id'],reason='first')
    with pytest.raises(ValidationError,match='baseline changed'):
        store.activate(second['id'],reason='stale')


def test_fixture_report_cannot_deploy_into_production(prepared,tmp_path):
    store,dataset,candidate,_=prepared
    report=run_eval(prepared)
    with RSIStore(tmp_path/'production') as production:
        production.import_dataset(manifest(tmp_path))
        production.candidate('toolbox',candidate['guidance'],candidate['rationale'])
        production.save_evaluation(report)
        with pytest.raises(ValidationError,match='live evaluations'):
            production.activate(report['id'],reason='not real evidence')
        with pytest.raises(ValidationError,match='sandbox'):
            evaluate(production,candidate['id'],dataset['id'],CONFIG,fixtures={})


def test_task_snapshot_survives_activation_and_new_task_sees_new_version(prepared):
    store,_,candidate,_=prepared
    original=pin_prompts(['toolbox'],store.root)['toolbox']
    report=run_eval(prepared)
    store.activate(report['id'],reason='new version')
    later=pin_prompts(['toolbox'],store.root)['toolbox']
    assert original['id']!=later['id']==candidate['id']
    calls=[]
    def request(*args,**kwargs):
        calls.append(args[3][0]['content'][0]['text'])
        return json.dumps(raw('detected'))
    image=np.full((64,80,3),90,dtype=np.uint8)
    result=inspect_toolbox(image,config=CONFIG,request=request,prompt_snapshot=original)
    assert result['prompt_version']==original['id'] and calls[0]==original['text']
    result=inspect_toolbox(image,config=CONFIG,request=request,prompt_snapshot=later)
    assert result['prompt_version']==candidate['id']


def test_active_prompt_rejects_another_model_endpoint_without_a_request(prepared):
    store,_,_,_=prepared
    active=store.activate(run_eval(prepared)['id'],reason='bound model')
    def forbidden(*args,**kwargs):
        pytest.fail('No request allowed after model compatibility mismatch')
    result=inspect_toolbox(np.full((64,80,3),90,dtype=np.uint8),
        config=replace(CONFIG,endpoint='https://another.invalid'),request=forbidden,prompt_snapshot=active)
    assert result['status']=='unknown' and result['error_kind']=='configuration'


def test_cross_split_scene_group_and_image_leakage_rejected(tmp_path):
    path=manifest(tmp_path)
    data=json.loads(path.read_text())
    data['cases'][6]['group_id']=data['cases'][0]['group_id']
    path.write_text(json.dumps(data))
    with RSIStore(tmp_path/'registry') as store:
        with pytest.raises(ValidationError,match='leaks'):
            store.import_dataset(path)
        assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0]==0


def test_relabeling_an_existing_case_is_rejected(prepared,tmp_path):
    store,_,_,_=prepared
    path=tmp_path/'manifest.json'
    data=json.loads(path.read_text())
    data['cases'][0]['expected']='unknown'
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError,match='immutable'):
        store.import_dataset(path)


def test_image_tampering_blocks_activation(prepared):
    store,dataset,_,_=prepared
    report=run_eval(prepared)
    (store.root/dataset['cases'][0]['image']).write_bytes(b'changed')
    with pytest.raises(ValidationError,match='checksum'):
        store.activate(report['id'],reason='invalid image')


def test_malformed_reply_is_technical_failure_not_a_correct_unknown(prepared):
    _,_,_,fixtures=prepared
    fixtures['candidate']['case_4']={'status':'unknown'}
    report=run_eval(prepared)
    assert report['status']=='INCOMPLETE' and not report['gate']['passed']
    assert any(r['error_kind']=='protocol' for r in report['rows'])


def test_request_and_token_budgets_fail_closed(prepared):
    with pytest.raises(ValidationError,match='budget'):
        run_eval(prepared,max_requests=1)
    report=run_eval(prepared,max_tokens=15)
    assert report['status']=='INCOMPLETE' and report['requests']==2
    assert not report['gate']['passed']


def test_missing_usage_stops_live_evaluation(prepared):
    store,dataset,candidate,_=prepared
    calls=[]
    def no_usage(*args,**kwargs):
        calls.append(True)
        return json.dumps(raw('detected'))
    report=evaluate(store,candidate['id'],dataset['id'],CONFIG,request=no_usage)
    assert report['status']=='INCOMPLETE' and len(calls)==1
    assert report['rows'][0]['error_kind']=='unaccounted_usage'


def test_gate_rechecks_cost_and_per_class_regression(prepared):
    _,dataset,_,_=prepared
    report=run_eval(prepared)
    for row in report['rows']:
        if row['role']=='candidate':
            row['tokens']=100
            row['duration_s']=10
    verdict=assess(report,dataset)
    assert not verdict['passed']
    assert {'token_cost','latency'}<=set(verdict['failed'])


def test_model_proposer_sees_development_only_and_cannot_activate(prepared):
    store,dataset,_,_=prepared
    def request(*args,**kwargs):
        body=json.loads(args[3][1]['content'])
        assert {c['id'] for c in body['development_cases']}=={'case_6','case_7','case_8'}
        assert kwargs['max_output_tokens']<=1024
        kwargs['turn']['telemetry']={'total_tokens':20}
        return json.dumps({'guidance':'Require visible latch geometry.','rationale':'Development counterexample'})
    original=store.active('toolbox')['id']
    candidate=propose(store,'toolbox',dataset['id'],CONFIG,request=request)
    assert candidate['source']=='model' and candidate['parent']==original
    assert store.active('toolbox')['id']==original
    assert store.db.execute('SELECT count(*) FROM proposals').fetchone()[0]==2


def test_proposer_unknown_usage_rejects_candidate(prepared):
    store,dataset,_,_=prepared
    def request(*args,**kwargs):
        return json.dumps({'guidance':'New advice','rationale':'No usage'})
    count=store.db.execute('SELECT count(*) FROM prompts').fetchone()[0]
    with pytest.raises(ValidationError,match='usage unknown'):
        propose(store,'toolbox',dataset['id'],CONFIG,request=request)
    assert store.db.execute('SELECT count(*) FROM prompts').fetchone()[0]==count


def test_registry_kind_is_immutable(prepared):
    store,_,_,_=prepared
    with pytest.raises(ValidationError,match='registry kind'):
        RSIStore(store.root,kind='production')


def test_executor_pins_all_visual_prompts_before_first_robot_action(prepared,monkeypatch,tmp_path):
    from robopilot.backends import MockBackend
    from robopilot.executor import MissionExecutor
    from robopilot.schemas import Pose, parse_plan
    from robopilot.storage import MissionStore
    store,_,candidate,_=prepared
    report=run_eval(prepared)
    monkeypatch.setenv('ROBOPILOT_RSI_DIR',str(store.root))
    original=store.active('toolbox')['id']
    selected=[]
    def inspect(*args,**kwargs):
        version=kwargs['prompt_snapshot']
        selected.append(version['id'])
        return {'status':'detected','reason':'fixture','prompt_version':version['id'],
                'prompt_sha256':version['sha256']}
    monkeypatch.setattr('robopilot.toolbox_vision.inspect_toolbox',inspect)
    class ActivateWhileMoving(MockBackend):
        switched=False
        def navigate(self,*args,**kwargs):
            if not self.switched:
                self.switched=True
                store.activate(report['id'],reason='Switch after mission has started')
            return super().navigate(*args,**kwargs)
    places={'room':Pose(1.,0.,0.)}
    plan=parse_plan({'version':1,'name':'pinned_mission','steps':[
        {'id':'go','action':'navigate','place':'room'},
        {'id':'look','action':'inspect','place':'room','target':'toolbox','depends_on':['go']}]},places)
    missions=MissionStore(tmp_path/'missions')
    try:
        first=MissionExecutor(ActivateWhileMoving(),missions).run(plan,places)
        second=MissionExecutor(MockBackend(),missions).run(plan,places)
    finally:
        missions.close()
    assert first['status']==second['status']=='SUCCEEDED'
    assert selected==[original,candidate['id']]
    assert first['observations'][0]['prompt_version']==original


def test_offline_demo_cli_runs_without_model_configuration(tmp_path):
    from robopilot.cli import main
    output=tmp_path/'demo'
    assert main(['rsi','demo','--output',str(output)])==0
    summary=json.loads((output/'summary.json').read_text())
    assert summary['bad_candidate_blocked'] and summary['rollback_restored_baseline']
    assert summary['model_requests']==summary['robot_actions']==0


def test_evaluator_code_change_requires_new_evaluation(prepared,monkeypatch):
    store,_,_,_=prepared
    report=run_eval(prepared)
    monkeypatch.setattr('robopilot.rsi_store.evaluator_fingerprint',lambda:'changed-code')
    with pytest.raises(ValidationError,match='Evaluator code changed'):
        store.activate(report['id'],reason='Stale evaluator')


def test_completed_reports_are_immutable_and_checksums_are_verified(prepared):
    store,_,_,_=prepared
    report=run_eval(prepared)
    with pytest.raises(ValidationError,match='immutable'):
        store.save_evaluation(report)
    with store.db:
        store.db.execute('UPDATE evaluations SET sha256=? WHERE id=?',('broken',report['id']))
    with pytest.raises(ValidationError,match='checksum'):
        store.evaluation(report['id'])


def test_registered_image_cannot_be_duplicated_under_another_case_id(prepared,tmp_path):
    store,_,_,_=prepared
    data=json.loads((tmp_path/'manifest.json').read_text())
    data['cases']=[{**data['cases'][0],'id':'renamed_case'}]
    path=tmp_path/'duplicate.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError,match='already registered'):
        store.import_dataset(path)
