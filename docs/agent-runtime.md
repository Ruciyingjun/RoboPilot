# 两层 Agent Runtime（首版）

2026-11-15 新增 `workflow` 入口。它与既有 `run`、`mission` 和顺序搜索 `agent` 并存。
外层管理 Planning / Executing / Reviewing 三个阶段；内层由模型根据观测选择工具。
本版 Planning 校验已有 JSON 计划并建立任务契约，不声称已实现开放式任务分解。
自然语言可先通过既有 `plan` 入口生成并校验，再将计划交给 workflow。

## 模块与执行

| 模块 | 职责 |
|---|---|
| `workflow_runtime.py` | 阶段调度、Agent 决策循环、预算、暂停与恢复、复核反馈 |
| `runtime_store.py` | SQLite checkpoint 历史、context.json 投影、运行目录单写租约 |
| `runtime_tools.py` | 工具白名单、参数/依赖/尝试次数检查、执行和独立结果复核 |
| `workflow_cli.py` | 运行/恢复入口、模型配置、同机器人 workflow 互斥、离线测试决策 |
| `ros_adapter.py` | 稳定目标 UUID、按精确 UUID 查询/取消/等待导航终态 |

Planning 保存经过校验的任务契约、地点快照和初始消息。
Executing 每轮保存模型请求意图，收到回复后保存用量与决策，再保存工具意图并执行。
工具完成后一次 checkpoint 保存结果、任务状态和完整工具反馈消息。
模型可补拍、查询位置/记忆、在允许次数内重试、复访已完成的导航点，也可请求复核。
它不能修改原任务的地点、目标、依赖或 `max_retries`，不执行任意 shell。

Reviewing 独立核对每个必要步骤、当前任务的检查证据和返航位置。
模型调用 finish_task 只会提交复核，不能自行宣告成功。
复核失败会把问题返回内层循环；阶段最多进入三次，所有尝试受同一总预算约束。
`not_detected` 表示有效检查未发现目标，仍可完成检查；本版不把它解释为整个房间不存在。

## 离线体验

在服务器项目目录运行，不启动仿真或请求模型：

```bash
bash scripts/container.sh run python -m robopilot workflow \
  --places src/robopilot/config/places.demo.yaml \
  --plan src/robopilot/examples/inspection.json \
  --backend mock --decider scripted \
  --script src/robopilot/examples/workflow.mock-tools.json \
  --output runs/workflow-demo
```

scripted 是明确标记的测试决策，验证 runtime 机制，不代表模型理解或机器人导航能力。
每个新 workflow 使用新输出目录；对已有目录必须使用 `--resume`。

## 模型驱动的 MuJoCo 任务

先启动 `./robopilot sim` 并等待 ready=true。另一个服务器终端执行：

```bash
./robopilot workflow \
  --places src/robopilot/config/places.home.yaml \
  --plan src/robopilot/examples/home_inspection.json \
  --max-turns 24 --max-tokens 16000 --total-timeout 600 \
  --output runs/workflow-home-01
```

这会调用配置的真实模型并移动机器人，模型调用产生用量。
快捷入口按需加载 `robopilot.local.env`；不要同时运行旧 inspect/search 或手动导航控制。
第一版仅允许本地 red_marker 检查，云端语义视觉尚未接入统一预算，不会从该入口调用。
模型使用 thinking=disabled，消息保留工具调用协议，不持久化私有推理内容或 API 密钥。

## Checkpoint 与恢复

```bash
./robopilot workflow --resume --output runs/workflow-home-01
```

恢复使用 checkpoint 内的原始计划、地点、模型来源和已消耗预算，不能通过重传参数增加预算。
已完成阶段跳过；已持久化的模型决策不重复请求；已完成工具不自动重放。
`runtime.sqlite3` 是权威记录，`context.json`、任务 JSON 与报告均为可重新生成的投影。
消息历史可能包含任务和现场观测，属于项目运行数据。

对中断工具作如下处理：

- 导航：调用前持久化 UUID。恢复时只针对该 UUID 查询结果并请求取消，等待终态。
  已成功则提交结果；已取消/中止则返回失败观测，让模型在原预算内决定。
  UUID 未知、结果已过期或无法确认终态时，保持 BLOCKED，禁止盲目重新发送。
- 检查/补拍：未提交的结果视为中断失败，孤立图片不能作为已完成检查。
  模型需要重新决策并取得新证据，受原有尝试次数约束。
- 模型：请求已经发出但回复或用量丢失时，保持 BLOCKED，避免未知用量下自动重试。

ROS 恢复要求同一容器实例和 ROS 域，并拒绝时钟回退；跨容器/新仿真世界不自动恢复。
运行目录及同机器人 workflow 都有进程租约；旧入口目前不参与新租约，不要并行控制。
BLOCKED 不提供强制忽略状态的按钮，需核对现场；确认停止旧任务后可创建新任务目录。
这不是对现实机器人动作的 exactly-once 保证：意图已保存但目标可能尚未发出时，宁可阻止自动恢复。

## 预算与边界

- 轮数、活跃墙上时间、模型已报告总 Token 数写入 checkpoint；服务停机时间不消耗活跃时间。
- 每次请求限制输出 Token，并按服务报告累计输入与输出 Token；请求前不知道精确输入消耗，
  最后一轮可能使已计费用量超出上限。此时立即停止且不执行回复中的工具，不声称硬性费用封顶。
- 未报告用量时阻止继续；失败请求是否计费不可推断，不会将用量归零。
- 工具受步骤期限和总期限约束；导航超时后按 ROS 取消协议核对终态。
- 本版没有上下文压缩、开放式动态子任务、跨仿真实例恢复、多机器人调度或云端视觉预算。
- 规划契约、工具循环、确定性复核均已实现；真实模型 + MuJoCo 新 runtime 验收另行记录。

测试入口：

```bash
bash scripts/container.sh run python -m pytest -q
```
