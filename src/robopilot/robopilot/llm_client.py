"""用途：调用可配置的聊天补全服务，限制响应大小并解析 JSON 或工具调用，不记录密钥。"""

import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .schemas import ValidationError, decode_json


class LLMError(RuntimeError):
    pass


def request_plan(endpoint, model, api_key, messages, schema, response_mode='json', timeout_s=30,
                 *, provider='generic', thinking='enabled', reasoning_effort='high', turn=None,
                 tool_name='create_plan', tool_description='Submit a robot mission for validation, not execution'):
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValidationError('LLM endpoint must be a complete HTTPS URL without user credentials or fragment')
    if not isinstance(api_key, str) or not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
        raise ValidationError('LLM API key must be non-empty printable ASCII without whitespace')
    if response_mode not in ('json', 'tools'):
        raise ValidationError('LLM response mode must be json or tools')
    if provider not in ('generic', 'deepseek'):
        raise ValidationError('Unsupported LLM provider')
    payload = {'model': model, 'messages': messages, 'stream': False}
    if provider == 'deepseek':
        if thinking not in ('enabled', 'disabled') or reasoning_effort not in ('low', 'high', 'max'):
            raise ValidationError('Invalid DeepSeek thinking settings')
        payload['thinking'] = {'type': thinking}
        if thinking == 'enabled':
            payload['reasoning_effort'] = reasoning_effort
        if response_mode == 'json':
            payload['response_format'] = {'type': 'json_object'}
    else:
        payload['temperature'] = 0
    if response_mode == 'tools':
        payload.update(tools=[{'type': 'function', 'function': {
            'name': tool_name, 'description': tool_description,
            'parameters': schema}}], tool_choice={'type': 'function', 'function': {'name': tool_name}})
        # DeepSeek thinking mode rejects named/required tool choices (HTTP 400).
        if provider == 'deepseek' and thinking == 'enabled':
            payload['tool_choice'] = 'auto'
    request = urllib.request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode(),
                                     headers={'Content-Type': 'application/json',
                                              'Authorization': 'Bearer ' + api_key}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise LLMError('LLM response exceeded 1 MiB')
        body = decode_json(raw)
        choice = body['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise LLMError('LLM output was truncated; no plan accepted')
        message = choice['message']
        if message.get('refusal'):
            raise LLMError('LLM declined this request')
        if response_mode == 'tools':
            calls = message['tool_calls']
            if len(calls) != 1 or calls[0].get('type') != 'function':
                raise LLMError(f'Expected exactly one {tool_name} tool call')
            function = calls[0]['function']
            if function['name'] != tool_name:
                raise LLMError('Unexpected LLM tool name')
            content = function['arguments']
            if provider == 'deepseek' or tool_name != 'create_plan':
                if not isinstance(calls[0].get('id'), str) or not calls[0]['id']:
                    raise LLMError('Tool response is missing call ID')
                if turn is not None:
                    turn['assistant_message'] = {'role': 'assistant', 'content': message.get('content') or '',
                                                  'tool_calls': calls}
                    if 'reasoning_content' in message:
                        turn['assistant_message']['reasoning_content'] = message['reasoning_content']
        else:
            content = message['content']
        if not isinstance(content, str) or not content.strip():
            raise LLMError('LLM returned no plan text')
        if turn is not None:
            usage = body.get('usage', {})
            turn['telemetry'] = {k: usage[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                                 if isinstance(usage, dict) and type(usage.get(k)) is int and usage[k] >= 0}
        return content
    except urllib.error.HTTPError as exc:
        # Do not include upstream bodies, request headers or credential-bearing URLs.
        raise LLMError(f'LLM HTTP {exc.code}; check service configuration, authentication or quota') from None
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        raise LLMError('LLM service connection failed or timed out') from None
    except (KeyError, IndexError, TypeError, UnicodeError, ValidationError) as exc:
        raise LLMError('LLM response envelope is invalid') from exc
