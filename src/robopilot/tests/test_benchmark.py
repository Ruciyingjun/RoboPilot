"""用途：用独立人工预期验证意图约束，并检查评测不会把遗漏、网络失败或应用拦截误计为模型成功。"""

import io
import json
from pathlib import Path

import pytest

from robopilot.benchmark import FixtureMemory, load_cases, run_benchmark
from robopilot.intent import extract_contract, IntentMismatch, ClarificationRequired
from robopilot.llm_client import LLMError
from robopilot.planning_context import aliases_from_file
from robopilot.planner import generate_plan
from robopilot.schemas import load_inputs, parse_plan, ValidationError

ROOT = Path(__file__).parents[1]
CASES = ROOT / 'examples/planner_benchmark.json'
PLACES, _ = load_inputs(ROOT/'config/places.demo.yaml')
ALIASES = aliases_from_file(ROOT/'config/aliases.demo.yaml', PLACES)
DATA = load_cases(CASES, PLACES)


def from_expected(steps):
    generated, last = [], None
    for index, step in enumerate(steps):
        step = dict(step, id=f's{index}')
        if step['action']=='navigate':
            last=step['id']
        if step['action']=='inspect':
            step['depends_on']=[last]
        generated.append(step)
    return parse_plan({'version':1,'name':'fixture','steps':generated},PLACES)


@pytest.mark.parametrize('case',[c for c in DATA['cases'] if c['expected']['decision']=='accept'],ids=lambda c:c['id'])
def test_contract_agrees_with_independent_hand_written_expectations(case):
    memory=FixtureMemory(case['memory']).last_seen('red_marker')
    contract=extract_contract(case['instruction'],PLACES,ALIASES,memory)
    contract.validate(from_expected(case['expected']['steps']))


@pytest.mark.parametrize('steps',[
    [{'action':'navigate','place':'checkpoint_a'},{'action':'return_to_start'}],
    [{'action':'navigate','place':'checkpoint_b'},{'action':'inspect','place':'checkpoint_b','target':'red_marker'},{'action':'return_to_start'}],
    [{'action':'navigate','place':'checkpoint_a'},{'action':'inspect','place':'checkpoint_a','target':'red_marker'}],
])
def test_valid_protocol_is_not_enough_when_task_steps_are_missing_or_wrong(steps):
    contract=extract_contract('去A点检查红色标记；返回起点',PLACES,ALIASES)
    with pytest.raises(IntentMismatch):
        contract.validate(from_expected(steps))


def test_forbidden_place_and_forbidden_return_are_checked():
    contract=extract_contract('不要去B点，只去A点检查红色标记，不用返回起点',PLACES,ALIASES)
    wrong=from_expected([{'action':'navigate','place':'checkpoint_b'}])
    with pytest.raises(IntentMismatch,match='禁止'):
        contract.validate(wrong)
    wrong=from_expected([{'action':'navigate','place':'checkpoint_a'},
                        {'action':'inspect','place':'checkpoint_a','target':'red_marker'},
                        {'action':'return_to_start'}])
    with pytest.raises(IntentMismatch,match='返航'):
        contract.validate(wrong)


@pytest.mark.parametrize('text',['如果A点没有标记就去B点','去那里检查红色标记',
                                '不要去A点；去A点检查红色标记',
                                '去A点检查红色标记，唱首歌，返回起点',
                                '别去B点先去A点，返回起点'])
def test_unsupported_or_conflicting_intent_does_not_call_model(monkeypatch,text):
    def forbidden(*args,**kwargs):
        pytest.fail('Unresolved instruction reached model')
    monkeypatch.setattr('urllib.request.urlopen',forbidden)
    audit={}
    with pytest.raises(ClarificationRequired):
        generate_plan(text,PLACES,ALIASES,FixtureMemory('none'),'ros','llm',audit)
    assert audit['stage']=='intent_contract'
    assert not audit.get('model_request_attempts')


def write_subset(tmp_path,ids):
    path=tmp_path/'cases.json'
    path.write_text(json.dumps({'version':1,'cases':[c for c in DATA['cases'] if c['id'] in ids]}))
    return path


def test_first_incomplete_candidate_and_successful_repair_are_scored_separately(tmp_path,monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-secret')
    calls=[]
    correct=from_expected(DATA['cases'][0]['expected']['steps']).to_dict()
    def reply(request,timeout):
        calls.append(json.loads(request.data))
        candidate=correct if len(calls)>1 else from_expected([
            {'action':'navigate','place':'checkpoint_a'},{'action':'return_to_start'}]).to_dict()
        return io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(candidate)}}]}).encode())
    monkeypatch.setattr('urllib.request.urlopen',reply)
    _,report=run_benchmark(write_subset(tmp_path,['simple_a']),PLACES,ALIASES,tmp_path/'out','llm',on_event=lambda _:None)
    assert report['results'][0]['passed']
    assert report['metrics']['first_model_plan_schema']['rate']==1
    assert report['metrics']['first_model_task_complete_on_accept_cases']['rate']==0
    assert report['metrics']['accepted_task_complete']['rate']==1
    assert report['metrics']['model_request_attempts']==2
    attempts=report['results'][0]['audit']['attempts']
    assert attempts[0]['protocol_valid'] and not attempts[0]['intent_valid']
    assert len(attempts[0]['candidate']['steps'])==2


def test_application_rejection_is_not_counted_as_model_refusal(tmp_path):
    _,report=run_benchmark(write_subset(tmp_path,['open_door']),PLACES,ALIASES,tmp_path/'out','llm',on_event=lambda _:None)
    assert report['metrics']['correct_rejection']['rate']==1
    assert report['metrics']['precheck_rejections']==1
    assert report['metrics']['model_refusals']==0
    assert report['metrics']['model_request_attempts']==0
    assert report['robot_execution'] is False


def test_network_failure_is_never_scored_as_correct_rejection(tmp_path,monkeypatch):
    def fail(text,places,aliases,store,backend,planner,audit,*args):
        audit.update(model_request_attempts=1,stage='planning')
        raise LLMError('network unavailable')
    monkeypatch.setattr('robopilot.benchmark.generate_plan',fail)
    directory,report=run_benchmark(write_subset(tmp_path,['open_door','grasp']),PLACES,ALIASES,tmp_path/'out','llm',on_event=lambda _:None)
    assert report['status']=='STOPPED_ON_TECHNICAL_ERROR'
    assert report['metrics']['correct_rejection']['passed']==0
    assert report['metrics']['case_coverage']['rate']==0.5
    assert report['results'][0]['decision']=='error'
    assert (directory/'summary.json').is_file()


def test_dataset_path_traversal_is_rejected_before_creating_output(tmp_path):
    data={'version':1,'cases':[dict(DATA['cases'][0],id='../bad')]}
    path=tmp_path/'bad.json';path.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        run_benchmark(path,PLACES,ALIASES,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_invalid_model_plan_is_recorded_but_does_not_stop_other_cases(tmp_path,monkeypatch):
    def invalid(text,places,aliases,store,backend,planner,audit,*args):
        audit.update(model_request_attempts=1,stage='planning')
        raise ValidationError('model response is not a valid plan')
    monkeypatch.setattr('robopilot.benchmark.generate_plan',invalid)
    _,report=run_benchmark(write_subset(tmp_path,['simple_a','two_points']),PLACES,ALIASES,
                           tmp_path/'out','llm',on_event=lambda _:None)
    assert report['status']=='COMPLETE'
    assert len(report['results'])==2
    assert report['metrics']['case_pass']['passed']==0
    assert report['metrics']['error_kinds']=={'plan_validation':2}


def test_completed_results_survive_interruption(tmp_path,monkeypatch):
    calls=[]
    original=generate_plan
    def interrupt(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:
            raise KeyboardInterrupt
        return original(*args,**kwargs)
    monkeypatch.setattr('robopilot.benchmark.generate_plan',interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_benchmark(write_subset(tmp_path,['simple_a','two_points']),PLACES,ALIASES,tmp_path/'out',on_event=lambda _:None)
    saved=json.loads(next((tmp_path/'out').glob('*/summary.json')).read_text())
    assert saved['status']=='INTERRUPTED' and len(saved['results'])==1
