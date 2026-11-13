<!-- 用途：按用户提供的 DeepSeek 调用格式说明 Linux 密钥配置、只规划试调用和机器人闭环验证。 -->
# DeepSeek 接入与实测步骤

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

本项目接入 DeepSeek 的聊天补全协议，默认 deepseek-flash、thinking=enabled、reasoning_effort=high、stream=false。
这与你提供的 OpenAI SDK 示例对应同一 HTTP API；现有实现直接使用 Python 标准库，不需要安装 SDK 或修改 ROS 的 Python 环境。

2026-10-28 已完成真实 DeepSeek JSON 与工具规划，并分别在 Gazebo 执行成功。详细证据及已发现边界见 [真实模型验收](live-deepseek.md)。规则模式与真实 DeepSeek 调用始终分开标记。

## 1. 构建与配置（Ubuntu 虚拟机内）

也可直接编辑项目根目录 [robopilot.local.env](../robopilot.local.env)，其中已预填模型参数，将 DEEPSEEK_API_KEY 的空字符串替换为真实密钥。
使用该文件时，在同一个终端执行 `unset ROBOPILOT_LLM_API_KEY`，然后 `set -a`、`source robopilot.local.env`、`set +a` 加载。
本机配置不会自动加载；不要把真实密钥写进下面的公共模板。README 第 3 节给出了完整加载命令。

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
source /opt/ros/jazzy/setup.bash
colcon build --packages-select robopilot --symlink-install
source install/local_setup.bash

set -a
source src/robopilot/config/deepseek.env.example
set +a

read -rsp 'DeepSeek API Key: ' DEEPSEEK_API_KEY
export DEEPSEEK_API_KEY
```

read 命令会等待在本机终端输入密钥，输入不显示，按 Enter 完成。不要把模板中的示例模型配置误认为密钥已经存在。每个新终端都需要重新加载配置与密钥。

密钥也可由现有 robopilot.local.env 提供，该文件被忽略；不要将真实密钥写入示例配置、README 或测试。若旧配置中存在 ROBOPILOT_LLM_API_KEY，它优先于 DEEPSEEK_API_KEY；改用 DeepSeek 密钥前可先运行 `unset ROBOPILOT_LLM_API_KEY`。

只有 DEEPSEEK_API_KEY 时也可自动选择 DeepSeek 默认配置；显式加载模板能避免之前的通用端点/模型环境变量影响配置。

## 2. 先只调用模型生成计划

不需要启动 Gazebo，也不会移动机器人：

```bash
ros2 run robopilot robopilot plan \
  --places src/robopilot/config/places.demo.yaml \
  --aliases src/robopilot/config/aliases.demo.yaml \
  --instruction '先到A点看看红色标记是否还在，然后到B点也检查一下，最后返回起点' \
  --planner llm --llm-format json \
  --memory runs/my-demo --backend ros \
  --output runs/deepseek-plan.json
```

预期依次产生 navigate A、inspect A、navigate B、inspect B、return_to_start。模型可使用其他步骤 ID，但动作与顺序需符合指令。
打开 deepseek-plan.json 和 deepseek-plan.planning.json：status 应为 VALIDATED、planner=llm、provider=deepseek、model=deepseek-flash；attempts 中包含校验结果与服务实际返回的 usage（如有）。

JSON 格式正确不保证语义完全正确，需要检查模型是否保留了检查和返回步骤。没有配置密钥、鉴权失败或最终校验失败时，程序返回 2，不能据此认为模型调用成功。

## 3. 复用已验证机器人能力

终端 1 加载环境后，在虚拟机桌面启动新默认场景：

```bash
ros2 launch "$PWD/install/robopilot/share/robopilot/launch/simulation.launch.py" robot_body:=turtlebot headless:=False initialize_demo:=True
```

等待 ready=true，再在已加载环境的终端 2 执行刚才的计划：

```bash
ros2 run robopilot robopilot run \
  --places src/robopilot/config/places.demo.yaml \
  --plan runs/deepseek-plan.json --backend ros --output runs/my-demo
```

run 使用已保存计划，不会再次调用模型；报告保留指令和 DeepSeek 规划来源。任务结束后再核对相机证据及步骤。

之后可将指令改为「去上次发现红色标记的地方重新检查，再返回起点」，仍使用同一个 --memory 数据库重新 plan，验证模型是否利用上下文中的历史地点。

## 4. 工具调用与思考参数

- --llm-format json：发送 response_format=json_object，使用最终 content 作为计划。推荐先验证此模式。
- --llm-format tools：请求 create_plan 工具，工具参数仍严格校验；模型不能直接控制 ROS。思考模式使用 tool_choice=auto，强制指定工具会被 DeepSeek 以 HTTP 400 拒绝。
- DeepSeek 思考工具修复会在内存中保留并回传 reasoning_content 和原工具调用，附上对应 tool_call_id 的校验结果，避免丢失协议字段。中间推理文本不写入审计或报告。
- 最多修复一次不合法计划，可用 --repair-attempts 0 禁用；网络和鉴权错误不重试，也不降级到规则模式。
- 默认单次请求 120 秒，可用 ROBOPILOT_LLM_TIMEOUT_S 设置 1–300 秒；通用服务默认仍为 30 秒。
- ROBOPILOT_LLM_THINKING 支持 enabled/disabled，ROBOPILOT_LLM_REASONING_EFFORT 支持 low/high/max。disabled 时不发送 effort，避免重新开启思考。

## 5. 示例代码与实际 HTTP 字段对应

| SDK 示例 | 本项目 HTTP 请求 |
|---|---|
| base_url=https://api.deepseek.com | POST https://api.deepseek.com/chat/completions |
| os.environ.get('DEEPSEEK_API_KEY') | Authorization: Bearer（同一终端的密钥） |
| model=deepseek-flash | model 字段 |
| stream=False | stream=false |
| reasoning_effort=high | reasoning_effort=high |
| extra_body thinking enabled | 顶层 thinking={type: enabled}，不额外嵌套 extra_body |

官方依据：[首次调用](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[思考与工具对话](https://api-docs.deepseek.com/guides/thinking_mode/)、[JSON 输出](https://api-docs.deepseek.com/guides/json_mode/)。

当前实测边界：92 项回归通过，真实 API 的 JSON/工具规划及对应 Gazebo 闭环已小范围验收。尚未建立大规模模型任务理解评测、人工感知准确率或泛化结论。已知不支持能力会被前置保守规则拒绝；模型明确拒绝不触发修复。
