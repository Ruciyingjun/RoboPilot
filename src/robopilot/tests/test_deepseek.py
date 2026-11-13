"""用途：验证 DeepSeek 参数、密钥来源、思考工具修复协议和不含密钥/推理文本的审计。"""

import io
import json

import pytest

from robopilot.llm_config import load_llm_config
from robopilot.planner import plan_instruction, plan_with_llm, generate_plan
from robopilot.schemas import Pose, ValidationError
from robopilot.planner import PlanningRefusal

PLACES = {'checkpoint_a': Pose(1., 0., 0.)}


def body(data, *, tools=False, reasoning='temporary-reasoning', usage=True):
    text = json.dumps(data)
    message = {'content': text, 'reasoning_content': reasoning}
    if tools:
        message.update(content=None, tool_calls=[{'id': 'call_plan_1', 'type': 'function',
                         'function': {'name': 'create_plan', 'arguments': text}}])
    response = {'choices': [{'message': message, 'finish_reason': 'tool_calls' if tools else 'stop'}]}
    if usage:
        response['usage'] = {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}
    return io.BytesIO(json.dumps(response).encode())


def candidate():
    return plan_instruction('去checkpoint_a检查红色标记；返回起点', PLACES).to_dict()


def test_deepseek_key_alone_selects_user_requested_defaults(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret')
    config = load_llm_config()
    assert config.provider == 'deepseek'
    assert config.endpoint == 'https://api.deepseek.com/chat/completions'
    assert config.model == 'deepseek-flash'
    assert config.thinking == 'enabled' and config.reasoning_effort == 'high'
    assert config.timeout_s == 120
    assert 'test-secret' not in repr(config)


@pytest.mark.parametrize('url', ['https://api.deepseek.com', 'https://api.deepseek.com/v1/'])
def test_deepseek_base_url_is_expanded_to_full_endpoint(monkeypatch, url):
    monkeypatch.setenv('ROBOPILOT_LLM_ENDPOINT', url)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret')
    assert load_llm_config().endpoint == url.rstrip('/') + '/chat/completions'


@pytest.mark.parametrize('name,value', [
    ('ROBOPILOT_LLM_THINKING', 'maybe'), ('ROBOPILOT_LLM_REASONING_EFFORT', 'invalid'),
    ('ROBOPILOT_LLM_TIMEOUT_S', 'nan'), ('ROBOPILOT_LLM_TIMEOUT_S', '0'),
    ('ROBOPILOT_LLM_PROVIDER', 'unknown'),
])
def test_invalid_provider_configuration_is_rejected(monkeypatch, name, value):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret')
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        load_llm_config()


def test_deepseek_missing_key_is_actionable(monkeypatch):
    monkeypatch.setenv('ROBOPILOT_LLM_PROVIDER', 'deepseek')
    with pytest.raises(ValidationError, match='DEEPSEEK_API_KEY'):
        load_llm_config()


def test_sdk_equivalent_json_payload_and_credential_free_audit(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret')
    seen = []
    def reply(request, timeout):
        seen.append(json.loads(request.data))
        assert timeout == 120
        assert request.full_url == 'https://api.deepseek.com/chat/completions'
        assert request.get_header('Authorization') == 'Bearer test-secret'
        return body(candidate())
    monkeypatch.setattr('urllib.request.urlopen', reply)
    audit = {}
    plan = generate_plan('去A点检查红色标记；返回起点', PLACES, {'A点': 'checkpoint_a'}, None,
                         'ros', 'llm', audit)
    payload = seen[0]
    assert payload['thinking'] == {'type': 'enabled'}
    assert payload['reasoning_effort'] == 'high' and payload['stream'] is False
    assert payload['model'] == 'deepseek-flash'
    assert payload['response_format'] == {'type': 'json_object'}
    assert 'temperature' not in payload and 'extra_body' not in payload
    assert audit['status'] == 'VALIDATED' and audit['provider'] == 'deepseek'
    assert audit['attempts'][0]['usage']['total_tokens'] == 150
    assert plan.steps[0].place == 'checkpoint_a'
    assert 'test-secret' not in json.dumps(audit)
    assert 'temporary-reasoning' not in json.dumps(audit)


def test_deepseek_tool_repair_preserves_transient_turn_not_audit(monkeypatch):
    requests = []
    def reply(request, timeout):
        requests.append(json.loads(request.data))
        assert requests[-1]['tool_choice'] == 'auto'
        plan = candidate()
        if len(requests) == 1:
            plan['steps'][0]['place'] = 'invented'
        return body(plan, tools=True)
    monkeypatch.setattr('urllib.request.urlopen', reply)
    audit = {}
    plan_with_llm('巡检', PLACES, 'https://api.deepseek.com/chat/completions',
                  'deepseek-flash', 'test-secret', response_mode='tools', audit=audit,
                  request_options={'provider': 'deepseek'})
    assert len(requests) == 2
    messages = requests[1]['messages']
    assistant = next(m for m in messages if m['role'] == 'assistant')
    tool = next(m for m in messages if m['role'] == 'tool')
    assert assistant['reasoning_content'] == 'temporary-reasoning'
    assert assistant['content'] == ''
    assert tool['tool_call_id'] == assistant['tool_calls'][0]['id']
    assert 'validation_error' in tool['content']
    assert 'temporary-reasoning' not in json.dumps(audit)
    assert 'tool_calls' not in json.dumps(audit)


def test_disabled_thinking_is_not_reenabled_by_effort(monkeypatch):
    def reply(request, timeout):
        payload = json.loads(request.data)
        assert payload['thinking'] == {'type': 'disabled'}
        assert 'reasoning_effort' not in payload
        return body(candidate())
    monkeypatch.setattr('urllib.request.urlopen', reply)
    plan_with_llm('巡检', PLACES, 'https://api.deepseek.com/chat/completions',
                  'deepseek-flash', 'test-secret', request_options={
                      'provider': 'deepseek', 'thinking': 'disabled', 'reasoning_effort': 'high'})


def test_deepseek_non_thinking_can_still_force_tool(monkeypatch):
    def reply(request, timeout):
        payload = json.loads(request.data)
        assert payload['tool_choice']['function']['name'] == 'create_plan'
        return body(candidate(), tools=True)
    monkeypatch.setattr('urllib.request.urlopen', reply)
    plan_with_llm('巡检', PLACES, 'https://api.deepseek.com/chat/completions', 'deepseek-flash',
                  'test-secret', response_mode='tools', request_options={
                      'provider': 'deepseek', 'thinking': 'disabled'})


def test_model_refusal_is_never_repaired_into_executable_plan(monkeypatch):
    calls = []
    def reply(request, timeout):
        calls.append(request)
        return body({'refusal': '无法识别该地点，请先配置'})
    monkeypatch.setattr('urllib.request.urlopen', reply)
    audit = {}
    with pytest.raises(PlanningRefusal):
        plan_with_llm('去不存在的地点检查', PLACES, 'https://api.deepseek.com/chat/completions',
                      'deepseek-flash', 'test-secret', audit=audit)
    assert len(calls) == 1
    assert audit['attempts'][0]['refused'] is True


@pytest.mark.parametrize('text', ['去A点打开门，然后返回起点', '去C点检查红色标记',
                                 '去A点检查工具箱', '去A点抓取物体', '自动建图并探索未知环境'])
def test_unsupported_capabilities_are_rejected_before_api(monkeypatch, text):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret')
    def forbidden(*args, **kwargs):
        pytest.fail('Unsupported task reached model API')
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    audit = {}
    with pytest.raises(ValidationError):
        generate_plan(text, PLACES, {'A点': 'checkpoint_a'}, None, 'ros', 'llm', audit)
    assert audit['status'] == 'REJECTED'
    assert audit['stage'] == 'capability_check'
    assert audit['attempts'] == []
