"""用途：从环境变量加载通用或 DeepSeek 模型配置，提供默认参数与独立密钥来源。"""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .schemas import ValidationError


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    endpoint: str
    model: str
    api_key: str = field(repr=False)
    thinking: str | None
    reasoning_effort: str | None
    timeout_s: float


def load_llm_config():
    endpoint = os.environ.get('ROBOPILOT_LLM_ENDPOINT', '')
    provider = os.environ.get('ROBOPILOT_LLM_PROVIDER', '')
    if not provider:
        provider = ('deepseek' if urlsplit(endpoint).hostname == 'api.deepseek.com'
                    or (not endpoint and os.environ.get('DEEPSEEK_API_KEY')) else 'generic')
    if provider not in ('generic', 'deepseek'):
        raise ValidationError('ROBOPILOT_LLM_PROVIDER must be generic or deepseek')
    model = os.environ.get('ROBOPILOT_LLM_MODEL', '')
    key = os.environ.get('ROBOPILOT_LLM_API_KEY', '')
    thinking = effort = None
    if provider == 'deepseek':
        endpoint = endpoint or 'https://api.deepseek.com/chat/completions'
        if urlsplit(endpoint).path.rstrip('/') in ('', '/v1'):
            endpoint = endpoint.rstrip('/') + '/chat/completions'
        model = model or 'deepseek-flash'
        key = key or os.environ.get('DEEPSEEK_API_KEY', '')
        thinking = os.environ.get('ROBOPILOT_LLM_THINKING', 'enabled')
        effort = os.environ.get('ROBOPILOT_LLM_REASONING_EFFORT', 'high')
        if thinking not in ('enabled', 'disabled') or effort not in ('low', 'high', 'max'):
            raise ValidationError('DeepSeek thinking must be enabled/disabled; reasoning effort low/high/max')
    if not all((endpoint, model, key)):
        if provider == 'deepseek':
            raise ValidationError('Set DEEPSEEK_API_KEY or ROBOPILOT_LLM_API_KEY in this terminal')
        raise ValidationError('Set ROBOPILOT_LLM_ENDPOINT, ROBOPILOT_LLM_MODEL, ROBOPILOT_LLM_API_KEY')
    try:
        timeout = float(os.environ.get('ROBOPILOT_LLM_TIMEOUT_S', '120' if provider == 'deepseek' else '30'))
        if not 1 <= timeout <= 300:
            raise ValueError
    except ValueError:
        raise ValidationError('ROBOPILOT_LLM_TIMEOUT_S must be between 1 and 300') from None
    return LLMConfig(provider, endpoint, model, key, thinking, effort, timeout)
