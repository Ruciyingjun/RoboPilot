"""用途：验证中文别名、LLM 工具协议、有限修复、规划审计及无效计划不会触发机器人执行。"""

import io
import json
import socket
import urllib.error
from pathlib import Path

import pytest

from robopilot.backends import MockBackend
from robopilot.cli import main
from robopilot.executor import MissionExecutor
from robopilot.llm_client import LLMError
from robopilot.planner import plan_instruction, plan_with_llm, generate_plan
from robopilot.planning_context import aliases_from_file, planning_context
from robopilot.planning_io import load_audit, save_plan
from robopilot.schemas import Pose, ValidationError, load_inputs
from robopilot.storage import MissionStore

ROOT = Path(__file__).parents[1]
PLACES_FILE = ROOT / 'config/places.demo.yaml'
ALIASES_FILE = ROOT / 'config/aliases.demo.yaml'
PLACES = {'checkpoint_a': Pose(1., 0., 0.), 'checkpoint_b': Pose(1., 1., 0.)}


def candidate():
    return plan_instruction('去checkpoint_a检查红色标记；返回起点', PLACES).to_dict()


def envelope(plan, mode='json', function='create_plan'):
    content = json.dumps(plan)
    message = ({'content': content} if mode == 'json' else {'tool_calls': [{
        'type': 'function', 'function': {'name': function, 'arguments': content}}]})
    return io.BytesIO(json.dumps({'choices': [{'message': message}]}).encode())


def test_aliases_resolve_to_canonical_coordinates():
    aliases = aliases_from_file(ALIASES_FILE, PLACES)
    plan = plan_instruction('先去A点检查红色标记，再去B点，最后返回起点', PLACES, aliases=aliases)
    assert [(s.action, s.place) for s in plan.steps] == [
        ('navigate', 'checkpoint_a'), ('inspect', 'checkpoint_a'),
        ('navigate', 'checkpoint_b'), ('return_to_start', None)]


@pytest.mark.parametrize('mapping', [
    'A点: unknown', 'checkpoint_a: checkpoint_b', '"": checkpoint_a',
    'A点: checkpoint_a\n  A点: checkpoint_b',
])
def test_invalid_aliases_cannot_change_destinations(tmp_path, mapping):
    path = tmp_path / 'aliases.yaml'
    path.write_text('version: 1\naliases:\n  ' + mapping + '\n')
    with pytest.raises(ValidationError):
        aliases_from_file(path, PLACES)


@pytest.mark.parametrize('mode', ['json', 'tools'])
def test_llm_receives_memory_and_alias_context_without_evidence_or_key(monkeypatch, mode):
    context = {'aliases': {'A点': 'checkpoint_a'}, 'last_seen': {'place': 'checkpoint_a'}}
    requests = []
    def reply(request, timeout):
        requests.append(json.loads(request.data))
        assert timeout == 30
        assert 'test-secret' not in request.data.decode()
        return envelope(candidate(), mode)
    monkeypatch.setattr('urllib.request.urlopen', reply)
    plan = plan_with_llm('复查上次地点', PLACES, 'https://example.invalid/v1/chat/completions',
                         'model', 'test-secret', context=context, response_mode=mode)
    assert plan.steps[0].place == 'checkpoint_a'
    prompt = requests[0]['messages'][0]['content']
    assert 'A点' in prompt and 'last_seen' in prompt
    if mode == 'tools':
        assert requests[0]['tool_choice']['function']['name'] == 'create_plan'


def test_invalid_model_plan_has_only_one_repair_and_is_audited(monkeypatch):
    calls = []
    def reply(request, timeout):
        calls.append(json.loads(request.data))
        data = candidate()
        if len(calls) == 1:
            data['steps'][0]['place'] = 'invented'
        return envelope(data)
    monkeypatch.setattr('urllib.request.urlopen', reply)
    audit = {}
    plan = plan_with_llm('检查A', PLACES, 'https://example.invalid/chat', 'model', 'key', audit=audit)
    assert len(calls) == 2
    assert 'Validation error' in calls[1]['messages'][-1]['content']
    assert [a['valid'] for a in audit['attempts']] == [False, True]
    assert plan.steps[0].place == 'checkpoint_a'


def test_repeated_invalid_output_never_falls_back_to_rules(monkeypatch):
    calls = []
    def reply(request, timeout):
        calls.append(request)
        data = candidate()
        data['steps'][0]['place'] = 'invented'
        return envelope(data)
    monkeypatch.setattr('urllib.request.urlopen', reply)
    with pytest.raises(ValidationError, match='unknown place'):
        plan_with_llm('去checkpoint_a', PLACES, 'https://example.invalid/chat', 'model', 'key')
    assert len(calls) == 2


@pytest.mark.parametrize('mode', ['empty', 'wrong_tool', 'truncated', 'oversized'])
def test_broken_protocol_is_not_executed(monkeypatch, mode):
    def reply(request, timeout):
        if mode == 'empty':
            return io.BytesIO(b'{"choices": []}')
        if mode == 'wrong_tool':
            return envelope(candidate(), 'tools', 'move_robot')
        if mode == 'truncated':
            return io.BytesIO(b'{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}')
        return io.BytesIO(b' ' * (1024*1024+1))
    monkeypatch.setattr('urllib.request.urlopen', reply)
    with pytest.raises(LLMError):
        plan_with_llm('巡检', PLACES, 'https://example.invalid/chat', 'model', 'key',
                      response_mode='tools' if mode == 'wrong_tool' else 'json')


@pytest.mark.parametrize('error', ['auth', 'timeout'])
def test_network_errors_are_not_retried_or_leaked(monkeypatch, error):
    calls = []
    def reply(request, timeout):
        calls.append(request)
        if error == 'timeout':
            raise socket.timeout('test-secret')
        raise urllib.error.HTTPError('https://example.invalid/?key=test-secret', 401,
                                     'test-secret', {}, io.BytesIO(b'test-secret'))
    monkeypatch.setattr('urllib.request.urlopen', reply)
    with pytest.raises(LLMError) as failure:
        plan_with_llm('巡检', PLACES, 'https://example.invalid/chat', 'model', 'test-secret')
    assert len(calls) == 1
    assert 'test-secret' not in str(failure.value)


def test_invalid_auth_header_never_echoes_secret(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid credentials were sent to the network')
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    with pytest.raises(ValidationError) as failure:
        plan_with_llm('巡检', PLACES, 'https://example.invalid/chat', 'model', 'test-secret\n')
    assert 'test-secret' not in str(failure.value)


def test_changed_plan_or_coordinates_are_rejected_before_execution(tmp_path):
    store = MissionStore(tmp_path / 'runs')
    audit = {}
    try:
        plan = generate_plan('去A点', PLACES, {'A点': 'checkpoint_a'}, store, 'mock', 'rules', audit)
    finally:
        store.close()
    path = tmp_path / 'plan.json'
    save_plan(path, plan, audit)
    assert load_audit(path, plan, PLACES)['instruction'] == '去A点'
    with pytest.raises(ValidationError, match='Plan differs'):
        load_audit(path, plan_instruction('去checkpoint_b', PLACES), PLACES)
    with pytest.raises(ValidationError, match='coordinates changed'):
        load_audit(path, plan, dict(PLACES, checkpoint_a=Pose(99., 0., 0.)))


def test_one_command_mission_persists_instruction_and_source(tmp_path):
    assert main(['mission', '--places', str(PLACES_FILE), '--aliases', str(ALIASES_FILE),
                 '--instruction', '先去A点检查红色标记，再去B点检查红色标记，最后返回起点',
                 '--backend', 'mock', '--mock-images', 'red,empty', '--output', str(tmp_path)]) == 0
    record = json.loads(next(tmp_path.glob('*/mission.json')).read_text())
    assert record['status'] == 'SUCCEEDED'
    assert record['planning']['planner'] == 'rules'
    assert 'A点' in record['planning']['instruction']
    assert '原始指令' in next(tmp_path.glob('*/report.md')).read_text()
    assert len(list((tmp_path / 'plans').glob('*.planning.json'))) == 1


def test_no_model_configuration_never_constructs_backend(tmp_path, monkeypatch):
    for name in ('ENDPOINT', 'MODEL', 'API_KEY'):
        monkeypatch.delenv('ROBOPILOT_LLM_' + name, raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail('Backend was constructed before planning succeeded')
    monkeypatch.setattr('robopilot.cli.MockBackend', forbidden)
    assert main(['mission', '--places', str(PLACES_FILE), '--instruction', '去checkpoint_a',
                 '--planner', 'llm', '--output', str(tmp_path)]) == 2
    assert not list(tmp_path.glob('*/mission.json'))
    audit = json.loads(next((tmp_path / 'plans').glob('*.planning.json')).read_text())
    assert audit['status'] == 'REJECTED'


def test_context_keeps_last_detection_and_later_negative_observation(tmp_path):
    store = MissionStore(tmp_path)
    try:
        plan = plan_instruction('去checkpoint_a检查红色标记', PLACES)
        MissionExecutor(MockBackend(images=['red']), store).run(plan, PLACES)
        MissionExecutor(MockBackend(images=['empty']), store).run(plan, PLACES)
        context = planning_context(PLACES, {}, store, 'mock')
        assert context['last_seen']['status'] == 'detected'
        assert context['recent_observations'][0]['status'] == 'not_detected'
        assert 'evidence_path' not in json.dumps(context)
        assert planning_context(PLACES, {}, store, 'ros')['last_seen'] is None
    finally:
        store.close()


def test_failed_replanning_invalidates_existing_plan(tmp_path, monkeypatch):
    output = tmp_path / 'plan.json'
    args = ['plan', '--places', str(PLACES_FILE), '--instruction', '去checkpoint_a',
            '--memory', str(tmp_path / 'runs'), '--output', str(output)]
    assert main(args) == 0
    monkeypatch.delenv('ROBOPILOT_LLM_ENDPOINT', raising=False)
    assert main(args + ['--planner', 'llm']) == 2
    assert main(['run', '--places', str(PLACES_FILE), '--plan', str(output),
                 '--output', str(tmp_path / 'execution')]) == 2
    assert not (tmp_path / 'execution').exists()
