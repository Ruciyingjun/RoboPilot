"""用途：验证工具反馈分支、顺序与返航约束、不确定观测、预算及不安全动作中止。"""

from robopilot.agent_loop import SearchAgent
from robopilot.backends import MockBackend
from robopilot.schemas import Pose
from robopilot.storage import MissionStore

PLACES={'a':Pose(1,0,0),'b':Pose(2,0,0)}


def scripted(calls, captured):
    def decide(messages, remaining):
        captured.append(messages[-1].copy())
        action,place=calls.pop(0)
        call={'action':action,'place':place}
        return call, {'assistant_message':{'role':'assistant','content':'','tool_calls':[
            {'id':f'call_{len(captured)}','type':'function','function':{'name':'robot_tool','arguments':'{}'}}]}}
    return decide


def run(tmp_path,calls,images=(),outcomes=(),turns=24):
    store=MissionStore(tmp_path)
    backend=MockBackend(outcomes,images=images)
    captured=[]
    try:
        result=SearchAgent(backend,store).run_search(PLACES,['a','b'],scripted(calls,captured),max_turns=turns)
        return result,backend,captured
    finally: store.close()


def test_feedback_drives_second_location_and_return(tmp_path):
    calls=[('navigate_to','a'),('inspect_target','a'),('navigate_to','b'),('inspect_target','b'),
           ('return_to_start',''),('finish_task','')]
    result,backend,messages=run(tmp_path,calls,['empty','red'])
    assert result['status']=='SUCCEEDED'
    assert [o['status'] for o in result['observations']]==['not_detected','detected']
    assert 'not_detected' in messages[2]['content']
    assert backend.visited==[PLACES['a'],PLACES['b'],backend.start]


def test_early_finish_and_inspection_without_navigation_rejected(tmp_path):
    calls=[('finish_task',''),('inspect_target','a'),('navigate_to','a'),('inspect_target','a'),
           ('return_to_start',''),('finish_task','')]
    result,backend,_=run(tmp_path,calls,['red'])
    assert result['status']=='SUCCEEDED'
    assert [t['result']['status'] for t in result['agent']['turns'][:2]]==['rejected','rejected']
    assert backend.visited==[PLACES['a'],backend.start]


def test_unknown_is_not_reported_as_complete_absence(tmp_path):
    calls=[('navigate_to','a'),('inspect_target','a'),('navigate_to','b'),('inspect_target','b'),
           ('return_to_start',''),('finish_task','')]
    result,_,_=run(tmp_path,calls,['dark','empty'])
    assert result['status']=='PARTIAL'


def test_unsafe_navigation_stops_all_further_tools(tmp_path):
    result,backend,messages=run(tmp_path,[('navigate_to','a'),('navigate_to','b')],outcomes=['unsafe'])
    assert result['status']=='FAILED'
    assert len(messages)==1 and len(backend.visited)==1 and backend.cancel_called


def test_budget_exhaustion_is_failure_and_cancels(tmp_path):
    result,backend,_=run(tmp_path,[('list_places','')],turns=1)
    assert result['status']=='FAILED' and backend.cancel_called


def test_wrong_order_and_unknown_place_never_move(tmp_path):
    result,backend,_=run(tmp_path,[('navigate_to','b'),('navigate_to','unknown')],turns=2)
    assert result['status']=='FAILED' and not backend.visited


def test_detection_forbids_further_search(tmp_path):
    result,backend,_=run(tmp_path,[('navigate_to','a'),('inspect_target','a'),('navigate_to','b'),
        ('return_to_start',''),('finish_task','')],['red'])
    assert result['status']=='SUCCEEDED'
    assert result['agent']['turns'][2]['result']['status']=='rejected'
    assert backend.visited==[PLACES['a'],backend.start]


def test_failed_return_cannot_finish_successfully(tmp_path):
    result,_,_=run(tmp_path,[('navigate_to','a'),('inspect_target','a'),
        ('return_to_start',''),('finish_task','')],['red'],['succeeded','failed'],turns=4)
    assert result['status']=='FAILED'
    assert result['agent']['turns'][-1]['result']['status']=='rejected'


def test_all_valid_negative_checks_are_completed_search(tmp_path):
    result,_,_=run(tmp_path,[('navigate_to','a'),('inspect_target','a'),('navigate_to','b'),
        ('inspect_target','b'),('return_to_start',''),('finish_task','')],['empty','empty'])
    assert result['status']=='SUCCEEDED'
    assert result['agent']['turns'][-1]['result']['found_at'] is None


def test_model_outage_preserves_failure_and_cancels(tmp_path):
    backend=MockBackend()
    store=MissionStore(tmp_path)
    def fail(messages, remaining):
        raise TimeoutError('model unavailable')
    try:
        result=SearchAgent(backend,store).run_search(PLACES,['a'],fail)
        assert result['status']=='FAILED' and backend.cancel_called
        assert not backend.visited
        assert (tmp_path/result['id']/'report.md').is_file()
    finally:store.close()
