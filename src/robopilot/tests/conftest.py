"""用途：隔离测试中的模型配置，防止测试继承本机真实密钥并意外调用外部服务。"""

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_model_configuration(monkeypatch):
    for key in list(os.environ):
        if key.startswith('ROBOPILOT_LLM_') or key == 'DEEPSEEK_API_KEY':
            monkeypatch.delenv(key, raising=False)
