"""Crash boundaries, budget persistence, review gating and observation-driven tool decisions."""
import json
from dataclasses import asdict

import pytest

from robopilot.backends import MockBackend, NavigationResult
from robopilot.runtime_store import CheckpointStore
from robopilot.schemas import Pose, parse_plan
from robopilot.storage import MissionStore
from robopilot.workflow_runtime import WorkflowRuntime


PLACES = {'room':Pose(1.,0.,0.)}
PLAN = parse_plan({'version':1,'name':'runtime_test','steps':[
    {'id':'go','action':'navigate','place':'room','max_retries':1},
    {'id':'look','action':'inspect','place':'room','target':'red_marker',
     'depends_on':['go'],'max_retries':1},
    {'id':'home','action':'return_to_start','max_retries':1}]}, PLACES)
CALLS = [('navigate_to','go'),('inspect_target','look'),('return_to_start','home'),('finish_task','')]


def scripted(calls=CALLS, tokens=5):
    def decide(messages, remaining, output_tokens):
        index = sum(m['role']=='assistant' for m in messages)
        action, step = calls[index]
        call = {'action':action,'step':step}
        return call, {'telemetry':{'total_tokens':tokens}, 'assistant_message':{
            'role':'assistant','content':'','tool_calls':[{'id':f'call_{index}','type':'function',
                'function':{'name':'robot_tool','arguments':json.dumps(call)}}]}}
    return decide


class Crash(BaseException):
    """Simulates process death, bypassing normal exception cleanup."""


class CrashCheckpoint(CheckpointStore):
    def __init__(self, root, event, occurrence=1):
        super().__init__(root)
        self.event, self.occurrence = event, occurrence

    def save(self, context, event):
        super().save(context, event)
        if event == self.event:
            self.occurrence -= 1
            if self.occurrence == 0:
                raise Crash(event)


class DurableMock(MockBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.goals = {}
        self.crash_after_motion = False
        self.identity = {'backend':'mock','instance':'test-world'}
        self.sim_time = 100

    def runtime_identity(self):
        return self.identity

    def runtime_time_ns(self):
        return self.sim_time

    def navigate(self, pose, timeout_s, *, goal_id=None):
        result = super().navigate(pose, timeout_s, goal_id=goal_id)
        self.goals[goal_id] = result
        if self.crash_after_motion:
            self.crash_after_motion = False
            raise Crash('motion executed, result not checkpointed')
        return result

    def reconcile_goal(self, goal_id, timeout_s):
        return self.goals.get(goal_id, NavigationResult('FAILED','UNKNOWN','Unknown goal',False))


def run(root, backend=None, decide=None, resume=False, cp_type=CheckpointStore, **kwargs):
    store = MissionStore(root)
    try:
        with cp_type(root) as cp:
            runtime = WorkflowRuntime(backend or DurableMock(), store, cp, decide or scripted(), on_event=lambda _:None)
            return runtime.run(None if resume else PLAN, None if resume else PLACES, resume=resume, **kwargs)
    finally:
        store.close()


def test_full_workflow_and_independent_review(tmp_path):
    context = run(tmp_path)
    assert context['status']=='SUCCEEDED'
    assert all(s['status']=='DONE' for s in context['stages'].values())
    assert context['budget']['tokens']==20 and context['budget']['turns']==4
    assert context['review']=={'accepted':True,'issues':[]}
    assert len(context['mission']['observations'])==1
    assert (tmp_path/context['mission']['id']/'report.md').is_file()


def test_rejected_tool_never_moves_robot(tmp_path):
    backend = DurableMock()
    ctx = run(tmp_path,backend,scripted([('delete_everything',''),*CALLS]))
    assert ctx['status']=='SUCCEEDED'
    assert ctx['calls'][0]['result']['status']=='rejected'
    assert len(backend.visited)==2


def test_observation_driven_retry_after_navigation_failure(tmp_path):
    backend = DurableMock(outcomes=['failed','succeeded','succeeded'])
    ctx = run(tmp_path,backend,scripted([('navigate_to','go'),('observe',''),*CALLS]))
    assert ctx['status']=='SUCCEEDED'
    assert len(ctx['mission']['steps'][0]['attempts'])==2
    assert ctx['calls'][1]['result']['pose']['x']==0


def test_premature_finish_returns_review_feedback(tmp_path):
    ctx = run(tmp_path,decide=scripted([('finish_task',''),*CALLS]))
    assert ctx['status']=='SUCCEEDED'
    assert ctx['stages']['reviewing']['attempts']==2
    assert any('"review"' in m.get('content','') for m in ctx['messages'])


def test_completed_tool_is_not_replayed_after_crash(tmp_path):
    backend = DurableMock()
    cp = lambda root:CrashCheckpoint(root,'tool_completed')
    with pytest.raises(Crash):
        run(tmp_path,backend,cp_type=cp)
    ctx = run(tmp_path,backend,resume=True)
    assert ctx['status']=='SUCCEEDED'
    assert len(backend.visited)==2
    assert ctx['budget']['tokens']==20
    assert ctx['stages']['planning']['attempts']==1


def test_executed_but_uncommitted_goal_reconciles_exact_uuid(tmp_path):
    backend = DurableMock()
    backend.crash_after_motion = True
    with pytest.raises(Crash):
        run(tmp_path,backend)
    ctx = run(tmp_path,backend,resume=True)
    assert ctx['status']=='SUCCEEDED'
    assert len(backend.visited)==2  # First move was reconciled, never replayed.
    assert ctx['calls'][0]['result']['status']=='SUCCEEDED'


def test_unsent_or_unknown_goal_blocks_recovery(tmp_path):
    backend = DurableMock()
    with pytest.raises(Crash):
        run(tmp_path,backend,cp_type=lambda root:CrashCheckpoint(root,'tool_intent'))
    ctx = run(tmp_path,backend,resume=True)
    assert ctx['status']=='BLOCKED'
    assert backend.visited==[]
    assert ctx['active_call'] is not None


def test_lost_model_response_blocks_unaccounted_retry(tmp_path):
    with pytest.raises(Crash):
        run(tmp_path,cp_type=lambda root:CrashCheckpoint(root,'model_requested'))
    def forbidden(*_):
        pytest.fail('Must not call the provider after losing unaccounted usage')
    ctx = run(tmp_path,resume=True,decide=forbidden)
    assert ctx['status']=='BLOCKED' and ctx['budget']['turns']==1


def test_checkpointed_model_decision_is_reused(tmp_path):
    backend = DurableMock()
    with pytest.raises(Crash):
        run(tmp_path,backend,cp_type=lambda root:CrashCheckpoint(root,'model_decided'))
    ctx = run(tmp_path,backend,resume=True)
    assert ctx['status']=='SUCCEEDED'
    assert ctx['budget']['turns']==4 and ctx['budget']['tokens']==20


def test_terminal_resume_does_not_invoke_model_or_move(tmp_path):
    ctx = run(tmp_path)
    def forbidden(*_):
        pytest.fail('Completed workflow should return its stored result')
    backend = DurableMock()
    resumed = run(tmp_path,backend,forbidden,resume=True)
    assert resumed['mission']['id']==ctx['mission']['id'] and not backend.visited


@pytest.mark.parametrize('budget,expected', [({'max_tokens':4},'BUDGET_EXHAUSTED'),
                                          ({'max_turns':1},'BUDGET_EXHAUSTED')])
def test_budget_cannot_be_reset_by_resume(tmp_path,budget,expected):
    backend = DurableMock()
    ctx = run(tmp_path,backend,**budget)
    assert ctx['status']==expected
    visited = len(backend.visited)
    resumed = run(tmp_path,backend,resume=True,max_tokens=100000,max_turns=100)
    assert resumed['status']==expected and len(backend.visited)==visited
    if 'max_tokens' in budget:
        assert backend.visited==[]


def test_changed_simulation_identity_blocks_new_actions(tmp_path):
    backend = DurableMock()
    with pytest.raises(Crash):
        run(tmp_path,backend,cp_type=lambda root:CrashCheckpoint(root,'tool_completed'))
    backend.identity = {'backend':'mock','instance':'different-world'}
    ctx = run(tmp_path,backend,resume=True)
    assert ctx['status']=='BLOCKED' and len(backend.visited)==1


def test_simulation_clock_rewind_blocks_new_actions(tmp_path):
    backend = DurableMock()
    with pytest.raises(Crash):
        run(tmp_path,backend,cp_type=lambda root:CrashCheckpoint(root,'tool_completed'))
    backend.sim_time = 1
    ctx = run(tmp_path,backend,resume=True)
    assert ctx['status']=='BLOCKED' and len(backend.visited)==1


def test_checkpoint_has_single_writer(tmp_path):
    with CheckpointStore(tmp_path):
        with pytest.raises(RuntimeError, match='Another workflow'):
            CheckpointStore(tmp_path)


def test_lost_inspection_not_inferred_from_orphan_image(tmp_path):
    backend = DurableMock()
    # Crash after committing navigation, then checkpoint inspection intent without executing.
    with pytest.raises(Crash):
        run(tmp_path,backend,cp_type=lambda root:CrashCheckpoint(root,'tool_intent',2))
    decide = scripted([CALLS[0],CALLS[1],CALLS[1],*CALLS[2:]])
    ctx = run(tmp_path,backend,decide,resume=True)
    assert ctx['status']=='SUCCEEDED'
    assert len(ctx['mission']['observations'])==1
    assert ctx['mission']['steps'][1]['attempts'][0]['result']['code']=='INTERRUPTED_TOOL'


def test_review_detects_missing_evidence(tmp_path):
    backend = DurableMock()
    with pytest.raises(Crash):
        run(tmp_path,backend,cp_type=lambda root:CrashCheckpoint(root,'execution_submitted'))
    for image in tmp_path.glob('*/evidence/*.png'):
        image.unlink()
    ctx = run(tmp_path,backend,decide=scripted([*CALLS,('observe','')]),resume=True,max_turns=4)
    assert ctx['status']!='SUCCEEDED'
    assert 'evidence' in ctx['review']['issues'][0]['reason']


def test_wall_time_expiring_during_model_call_prevents_tool(tmp_path,monkeypatch):
    clock = [100.]
    monkeypatch.setattr('robopilot.workflow_runtime.time.monotonic',lambda:clock[0])
    def slow_decide(*args):
        clock[0] += 2
        return scripted()(*args)
    backend = DurableMock()
    ctx = run(tmp_path,backend,slow_decide,total_timeout=1.)
    assert ctx['status']=='BUDGET_EXHAUSTED' and not backend.visited
    assert ctx['budget']['tokens']==5 and ctx['budget']['elapsed_s']>=2


def test_missing_provider_usage_blocks_tool_execution(tmp_path):
    def no_usage(*args):
        call, turn = scripted()(*args)
        turn['telemetry']={}
        return call,turn
    backend = DurableMock()
    ctx = run(tmp_path,backend,no_usage)
    assert ctx['status']=='BLOCKED' and not backend.visited


def test_revisit_repairs_pose_after_failed_inspection(tmp_path):
    class Drifted(DurableMock):
        drift = True
        def runtime_pose(self, timeout_s):
            if self.drift:
                self.drift=False
                self.position=Pose(2.,0.,0.)
            return self.position
    backend = Drifted()
    ctx = run(tmp_path,backend,scripted([*CALLS[:2],('revisit','go'),*CALLS[1:]]))
    assert ctx['status']=='SUCCEEDED'
    assert ctx['calls'][1]['result']['code']=='WRONG_OBSERVATION_POSE'
    assert len(backend.visited)==3


def test_review_rejects_false_return_success_then_model_repairs(tmp_path):
    class BadReturn(DurableMock):
        wrong = True
        def navigate(self, pose, timeout_s, **kwargs):
            old = self.position
            result = super().navigate(pose,timeout_s,**kwargs)
            if pose.x==0 and self.wrong:
                self.wrong=False
                self.position=old
            return result
    ctx = run(tmp_path,BadReturn(),scripted([*CALLS,*CALLS[2:]]))
    assert ctx['status']=='SUCCEEDED' and ctx['stages']['reviewing']['attempts']==2
    assert len(ctx['mission']['steps'][-1]['attempts'])==2


def test_projection_corruption_does_not_replace_sqlite_checkpoint(tmp_path):
    ctx = run(tmp_path)
    (tmp_path/'context.json').write_text('broken projection')
    resumed = run(tmp_path,resume=True)
    assert resumed['mission']['id']==ctx['mission']['id']


def test_model_source_change_rejected_on_resume(tmp_path):
    run(tmp_path)
    with pytest.raises(Exception,match='model/decision source'):
        run(tmp_path,resume=True,model_info={'source':'different-provider'})


def test_abort_policy_is_preserved(tmp_path):
    data = PLAN.to_dict()
    data['steps'][0].update(max_retries=0,on_failure='abort')
    plan = parse_plan(data,PLACES)
    store = MissionStore(tmp_path)
    try:
        with CheckpointStore(tmp_path) as cp:
            backend = DurableMock(outcomes=['failed'])
            ctx = WorkflowRuntime(backend,store,cp,scripted(),on_event=lambda _:None).run(plan,PLACES)
            assert ctx['status']=='FAILED' and len(backend.visited)==1
    finally:
        store.close()


def test_over_budget_decision_crash_cannot_bypass_token_guard(tmp_path):
    backend = DurableMock()
    with pytest.raises(Crash):
        run(tmp_path,backend,max_tokens=4,cp_type=lambda root:CrashCheckpoint(root,'model_decided'))
    ctx = run(tmp_path,backend,resume=True)
    assert ctx['status']=='BUDGET_EXHAUSTED' and not backend.visited


def test_crash_after_finish_receipt_resumes_review_without_another_model_call(tmp_path):
    backend = DurableMock()
    with pytest.raises(Crash):
        run(tmp_path,backend,cp_type=lambda root:CrashCheckpoint(root,'tool_completed',4))
    def forbidden(*_):
        pytest.fail('Finish receipt already submitted execution to review')
    ctx = run(tmp_path,backend,forbidden,resume=True)
    assert ctx['status']=='SUCCEEDED' and ctx['budget']['turns']==4


def test_model_adapter_caps_output_and_does_not_persist_private_reasoning(monkeypatch):
    from types import SimpleNamespace
    from robopilot.workflow_runtime import model_decider
    def request(endpoint,model,key,messages,schema,mode,timeout,**options):
        assert options['max_output_tokens']==37 and options['thinking']=='disabled'
        assert timeout==4 and options['tool_name']=='robot_tool'
        options['turn'].update(telemetry={'total_tokens':7},assistant_message={
            'reasoning_content':'private reasoning', 'role':'assistant','tool_calls':[]})
        return '{"action":"observe","step":""}'
    monkeypatch.setattr('robopilot.llm_client.request_plan',request)
    config = SimpleNamespace(endpoint='https://example.invalid',model='test',api_key='local-secret',
                             timeout_s=30,provider='generic',reasoning_effort='high')
    call, turn = model_decider(config)([],4,37)
    assert call['action']=='observe' and turn['telemetry']['total_tokens']==7
    assert 'reasoning_content' not in turn['assistant_message']
    assert 'local-secret' not in json.dumps(turn)
