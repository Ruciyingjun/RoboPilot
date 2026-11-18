<!-- 用途：介绍 RoboPilot 的目标、当前能力、运行入口与实验依据。 -->
# RoboPilot：视觉感知与语义空间记忆驱动的具身 Agent 自主巡检系统

面向家居移动机器人的自主巡检场景，融合自然语言任务规划、ROS 2 导航、视觉环境感知与语义空间记忆，实现从用户指令、现场执行到证据报告的闭环。当前提供无头服务器上的 MuJoCo 家居仿真、实时网页画面，以及具备持久化状态与恢复检查的 Agent Runtime。

**技术栈：** Python · ROS 2 Jazzy · MuJoCo · Nav2 · AMCL · TF2 · DDS · Topic / Service / Action · LLM Tool Calling · VLM · OpenCV · SQLite · Docker

[快速开始](docs/quickstart.md) · [MuJoCo 仿真](docs/mujoco-navigation.md) · [Agent Runtime](docs/agent-runtime.md) · [RSI](docs/rsi.md) · [开发进度](PROGRESS.md)

## 项目亮点

- **具身任务规划与执行：** 将自然语言指令转换为经过校验的结构化计划，通过 ROS 2 工具执行导航、检查和返航；支持固定巡检及模型根据工具反馈决策的顺序搜索。执行结果关联现场图片，无法判断时明确返回 `unknown`。
- **两层 Agent Runtime：** 外层管理 Planning / Executing / Reviewing，内层执行模型与工具的反馈循环。统一约束工具白名单、参数、依赖、重试次数、时间与模型用量；通过 SQLite checkpoint 保存阶段、消息、工具调用和预算，独立复核证据与返航状态。恢复导航前核对已持久化的目标 UUID，状态未知时阻止自动重发。
- **语义感知与时空记忆：** 集成 VLM 检查工具箱、背包挂墙、门关闭、果盘有水果等条件，使用 SQLite 保存地点、时间、位姿与图像证据。记忆有效性判别器结合时效、上下文与后续观测区分历史线索和当前证据，避免直接用旧发现回答当前状态。
- **RSI 受控 Prompt 改进：** 支持人工复核失败案例、人工或模型生成候选、基线与候选配对评测、非退化门禁、显式激活及回滚。每个任务固定视觉 Prompt 版本；候选不能修改标签、输出协议或门禁规则。
- **无头仿真与可追溯报告：** MuJoCo 桥接速度指令、时钟、里程计、TF、激光与相机，接入 AMCL / Nav2；浏览器实时显示同一仿真状态。任务保存 SQLite、JSON、Markdown 报告和图片，便于核对执行过程与检查结论。

**当前边界：** 各能力有独立入口，尚未统一为任意自然语言驱动的完整自主系统。新 `workflow` 的 Planning 校验已有 JSON 计划，视觉仅支持本地红色标记；云端 VLM 已接入既有任务执行器和搜索入口，尚未纳入新 Runtime 的统一预算。上下文压缩、跨仿真实例恢复与真机验证尚未完成。详细边界见 [Runtime 设计](docs/agent-runtime.md)。

## 实时仿真与巡检

完成[容器环境与模型配置](docs/quickstart.md)后，在服务器项目目录运行：

```bash
# 终端 1：启动家居仿真、ROS 2 导航栈与网页查看器
./robopilot sim
```

等待 `ready: true`。在本地电脑建立 SSH 隧道（`b309` 为服务器 SSH 别名）：

```bash
ssh -N -L 18081:127.0.0.1:18081 b309
```

保持隧道开启，在本地浏览器打开 <http://localhost:18081>。服务器无需桌面环境；端口冲突与转发配置见 [MuJoCo 导航说明](docs/mujoco-navigation.md)。

```bash
# 服务器终端 2：执行已验收的本地红色标记巡检并返航
./robopilot inspect

# 或：使用 LLM 按给定地点顺序搜索，找到目标后返航
./robopilot search bedroom living_room
```

`search` 使用模型并产生 API 用量；云端语义检查还会上传仿真相机图片。背包、门和果盘等检查入口保留，MuJoCo 新渲染下的准确率待独立评测。

### 体验 Agent Runtime 与 RSI

新 Runtime 的运行、预算和断点恢复命令见 [Agent Runtime](docs/agent-runtime.md)。它与既有 `inspect` / `search` 并存；对同一机器人不要并行发起任务。

RSI 可先独立运行无需模型、无需仿真的机制演示：

```bash
./robopilot rsi demo --output runs/rsi-demo-01
```

输出目录必须尚不存在。演示验证候选拒绝、激活、任务版本隔离与回滚，使用合成图片和固定响应，不代表真实 VLM 质量提升。真实案例导入、模型评测与生产激活步骤见 [RSI 使用说明](docs/rsi.md)。

## 演示素材

以下为项目既有巡检演示素材，具体运行环境与成绩以实验记录为准。

<img width="80%" alt="项目既有巡检演示" src="https://github.com/user-attachments/assets/967563b8-1544-4292-8e9c-04f1c89b6457" />

## 系统结构与代码

```text
用户指令 → 规划与计划校验 → 任务执行 → 现场观测 → 复核与报告
                              ↕              ↕
                       ROS 2 / Nav2     视觉检查 / SQLite 记忆
                              ↕
                      MuJoCo / 实时 Web Viewer

workflow：Planning → Executing（模型 ↔ 工具 ↔ 观测）→ Reviewing
RSI：人工复核案例 → 候选 Prompt → 配对评测 → 门禁 → 激活 / 回滚
```

| 模块 | 代码入口 | 说明 |
|---|---|---|
| 任务规划 | [planner.py](src/robopilot/robopilot/planner.py) | 自然语言到结构化计划 |
| Workflow Runtime | [workflow_runtime.py](src/robopilot/robopilot/workflow_runtime.py) | 阶段调度、模型循环与预算 |
| Checkpoint 与恢复 | [runtime_store.py](src/robopilot/robopilot/runtime_store.py)、[ros_adapter.py](src/robopilot/robopilot/ros_adapter.py) | 持久化状态与导航目标核对 |
| 工具执行与复核 | [runtime_tools.py](src/robopilot/robopilot/runtime_tools.py) | 工具约束、观测与完成条件 |
| 视觉 Prompt | [prompt_registry.py](src/robopilot/robopilot/prompt_registry.py)、[toolbox_vision.py](src/robopilot/robopilot/toolbox_vision.py) | 视觉指导、版本快照与结果校验 |
| 记忆有效性 | [memory_validity.py](src/robopilot/robopilot/memory_validity.py) | 历史线索与当前证据判别 |
| RSI 评测与门禁 | [rsi_evaluator.py](src/robopilot/robopilot/rsi_evaluator.py)、[rsi_gate.py](src/robopilot/robopilot/rsi_gate.py) | 配对评测与独立准入检查 |

## 测试与实验结果

以下按实验环境和验证对象分别记录，不将工程测试通过数当作机器人任务成功率。

| 验证对象 | 已记录结果 | 范围与依据 |
|---|---|---|
| 当前工程回归 | **268 passed，1 warning** | 2026-11-16 容器完整回归；警告来自既有 ROS 未就绪场景的服务回复超时，见 [进度记录](PROGRESS.md) |
| MuJoCo 家居导航 | **完成一次客厅→卧室→返航闭环，返航真值位置误差约 0.15 m** | 本地红色标记检查；同地图单次验收，不作为统计成功率，见 [MuJoCo 导航](docs/mujoco-navigation.md) |
| 历史 Gazebo 端到端巡检 | **严格成功 3/6（50.0%）；已提交任务平均耗时 91.56 s（5 次）** | 六轮含一次启动失败；耗时含识别失败任务、不含仿真启动，见 [实验方法与逐轮记录](docs/metrics-experiment.md) |
| 历史 Gazebo 视觉检查 | **有效判定 13/15（86.7%）** | 同地图背包、门、果盘检查；含误判和未知，图像经助手非盲复核，见 [历史实验](docs/metrics-experiment.md) |
| 记忆有效性离线消融 | **错误复用 8/14 → 0/14，下降 57.1 个百分点** | 14 个人工案例，相对允许直接复用旧肯定的宽松基线；复查使用理想真值，原有强制复查也为 0/14，见 [实验说明](docs/memory-validity.md) |
| RSI 闭环机制 | **27 项新增测试；离线演示完成拒绝、激活、版本隔离与回滚** | 合成图片与固定响应，未调用真实模型；尚无真实 VLM 改善或机器人故障复发率下降结论，见 [RSI](docs/rsi.md) |

历史实验不代表当前 MuJoCo 或新 Runtime 的性能。现有记录不支持“20 类场景、85% 端到端成功率”，也不支持将离线记忆实验写成真实机器人错误率相对降低 57.1%。

运行工程回归：

```bash
bash scripts/container.sh run python -m pytest -q
```

## 后续工作

- 完成真实模型驱动的新 Runtime + MuJoCo 验收，将自然语言规划与云端视觉纳入统一预算。
- 收集独立人工标注的视觉案例，按场景分组划分开发、门禁和最终测试集，验证 RSI 的真实改善与代价。
- 扩充多起点、遮挡、状态变化及故障注入实验，分别报告导航、感知、任务完成率与失败原因。
- 实现上下文压缩，补充长期任务与真实机器人验证。

[安装与运行](docs/quickstart.md) · [自选巡检](docs/user-inspection.md) · [Agent 工具循环](docs/agent-loop.md) · [记忆有效性](docs/memory-validity.md) · [系统设计](docs/design.md)

当前包元数据为 Proprietary，尚未提供开源许可证。
