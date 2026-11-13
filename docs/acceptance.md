<!-- 用途：记录 v0.2 在本机真实 Gazebo 与自动测试中的验收结果，区分实测证据和未验证能力。 -->
# v0.2 验收记录

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

日期：2026-10-28（Asia/Shanghai）。环境：Ubuntu 24.04 ARM64 虚拟机、4 核、约 6 GiB 内存、ROS 2 Jazzy、Gazebo Harmonic、llvmpipe 软件渲染。

本次实测使用 ROS_DOMAIN_ID=41 和独立 GZ_PARTITION，测试结束后停止本次启动的仿真。用户照使用指南运行时可以使用默认域；同一次验证的所有终端需保持域和 partition 一致。

## 已验证场景

| 场景 | 实际结果 | 本机证据 |
|---|---|---|
| 无相机的初版导航 | A、B、返回起点均 SUCCEEDED | 报告（旧运行产物已清理） |
| 相机环境诊断 | 时钟推进、激光 360 样本、TF 可用、RGB 240×320×3，ready=true | [诊断 JSON](../log/verification/doctor.json) |
| 两地点巡检 | A 检测到红色标记，B 未检测到，返航成功 | 报告（旧运行产物已清理） |
| 历史地点复查 | 由规则中文指令查询上次发现地点，导航到 A，再次检测到并返航 | 报告（旧运行产物已清理） |
| 环境变化复查 | 通过 Gazebo 服务移除标记后到 A，未检测到；旧发现仍保留 | 报告（旧运行产物已清理） |
| 超时取消与继续 | 0.1 秒期限注入：第一步 TIMED_OUT，取消终态已确认，返航 SUCCEEDED，任务 PARTIAL | 报告（旧运行产物已清理） |
| v0.2 标准构建与测试 | 当时 52 项通过；当前最新报告为下文 v0.3 的 73 项 | 历史见 PROGRESS.md |

报告和日志属于本机生成数据，未纳入版本管理；其他机器应重新执行使用指南生成。

## 图像证据

A 点检测到标记：

!A 点真实仿真图像（旧运行产物已清理）

B 点未检测到标记：

!B 点真实仿真图像（旧运行产物已清理）

输入为相机图像，检测器没有读取 Gazebo 对象列表或世界真值。marker 的移除仅用于实验场景控制。

## 当前统计与解释

runs/gazebo-inspection 中记录 3 次相关任务、7 个导航步骤，全部报告成功；4 次观测包括 detected=2、not_detected=2。平均任务墙上耗时为 11.693 秒。

这是单场景功能验收，不是独立随机评测。Nav2 成功沿用其导航容差，不能据此声称精确回到原坐标。检查完成与目标存在分开统计；not_detected 不等于执行失败。

统计来源：[汇总 JSON](../log/verification/gazebo-summary.json)。失败注入存于单独的 runs/gazebo-timeout，避免混入正常流程统计。

## 尚未验收

- 外部 LLM 服务：只有模拟响应的接口和校验测试，没有实际模型调用结果。
- 工具箱语义识别、VLM、开放场景搜索、门状态判断、真机部署。
- 多地图泛化、视觉人工标注准确率、大规模重复实验和演示视频。

恢复运行请按 [使用指南](usage.md) 从启动仿真开始，不对已经移动的机器人再次使用默认初始位姿。

## v0.3 增量验收（2026-10-28）

| 验证 | 结果 | 本机证据 |
|---|---|---|
| 中文指令直接巡检 | aliases + mission + rules，A 检测到/B 未检测到，返回起点，SUCCEEDED | 报告（旧运行产物已清理） |
| 中文历史地点复查 | 从 ROS 历史发现解析 checkpoint_a，复查检测到并返航，SUCCEEDED；报告含原始指令与历史上下文 | 报告（旧运行产物已清理） |
| initialize_demo=True | 自动设置默认出生位姿，doctor 输出 ready=true，进程正常退出 | [启动日志](../log/verification/v03-simulation-fixed.log) |
| 规划协议与错误边界 | JSON/工具模式、最多一次修复、服务错误、上下文隔离、摘要不匹配拒绝、失败不创建后端 | [最新测试 XML](../build/robopilot/pytest.xml) |

本轮使用独立 ROS 域 42 与 GZ_PARTITION。第一次集成因 launch Node 为普通 CLI 附加 --ros-args 导致自动初始化未执行；失败任务记录保留，随后改用 ExecuteProcess，重新启动并通过。并未把首次失败删除或计入成功率。

73 项测试包含 61 项核心/巡检/规划与 12 项 ROS 通信测试。模型响应由测试替身提供，没有实际外部 LLM 请求；上述中文 Gazebo 任务的规划器为 rules，不能据此宣称验证了大模型理解能力。

复现步骤见 [v0.3 自然语言规划指南](planning.md)。

## v0.3.1 DeepSeek 适配（离线验证）

用户提供 DeepSeek API 调用格式后，新增参数、配置与对话修复适配。最终 colcon build/test 通过：85 tests、0 errors、0 failures、0 skipped。新增 12 项覆盖密钥来源、默认模型/端点、请求参数、工具修复、审计及错误配置。

[测试报告](../log/verification/pytest-deepseek.xml)。本机没有真实密钥，未发出外部 API 请求，未启动新的 Gazebo 任务。已有 Gazebo 成果仍属于前述 rules 模式。下一项是真实 DeepSeek 计划及对应机器人执行验收，见 [DeepSeek 指南](deepseek.md)。

## v0.4 真实模型阶段

DeepSeek 的真实 JSON 和工具规划已分别在 Gazebo 完成巡检与历史复查。HTTP 400、模型静默省略动作、能力前置拒绝与模型明确拒绝均保留证据，详见 [真实模型验收](live-deepseek.md)。当前回归测试为 92 项。

## v0.5 固定规划评测（2026-10-29）

固定 26 条人工预期：DeepSeek 受约束管线 26/26，规则基线 17/26。16 条实际模型请求、10 条应用前检拒绝，不能归因于模型拒绝能力。两条代表计划最终 Gazebo 成功，首次准备失败保留。当前软件回归为 124 项通过、1 条 DDS 清理警告。具体指标、失败与复现见 [规划评测报告](planner-benchmark.md)。

## 2026-10-29 家居酒店机器人校准

- 初始定位 (2.7,-2.1,pi/2)，doctor 确认时钟、360 束雷达、头部相机 ready=true。
- 修正客厅/厨房门洞约 0.3 m→1.1 m，地图同步。
- 客厅红色 detected、卧室 not_detected、返回任务起点：SUCCEEDED。报告 runs/home-calibration-v2/20261029T135516Z_0b55658fb1e8/report.md。
- 厨房导航并返航：SUCCEEDED。报告 runs/home-kitchen-calibration/20261029T135631Z_c0ea642305c7/report.md。
- 首次修改前任务人为中止，PARTIAL 保留；不声称所有尝试均成功。厨房无视觉检查、无语义工具箱识别、无 GUI 性能或泛化结论。
- colcon build 通过、124 tests passed。复现见 docs/home-scene.md 最新校准小节。

收尾发现：发送 SIGINT 后 Nav2 组件容器在清理阶段出现 Magick/SIGSEGV（最终退出 -6）；发生在两份任务报告成功完成之后，未遗留本次启动进程。该退出异常根因尚未确认，不能将运行成功等同于退出清理无异常，后续需排查。日志 log/verification/home-service-calibration2.log。

## 2026-10-30 重复运行与关闭

同一世界固定家居巡检连续三轮 3/3 SUCCEEDED，客厅 detected、卧室 not_detected、返航成功。改用独立 Nav2 进程并延后资源清理后，一次无 GUI 关闭与一次受控 GUI 关闭均未复现原 Magick/SIGSEGV。GUI 首次发现孤儿子进程已修正，保留失败记录。最终回归 126 passed。详见 docs/stability.md，不将有限验证视为 GUI 性能或泛化结论。

## 2026-10-30 工具反馈搜索

真实DeepSeek+mock（6轮）及DeepSeek+Gazebo（7轮）均单次SUCCEEDED：卧室未检测到→客厅检测到→返航→finish。Gazebo包含一次漏填地点的工具拒绝与模型修正。138项自动测试通过。有限顺序搜索契约，不代表通用自然语言规划或工具箱语义识别；详见docs/agent-loop.md。

## 2026-10-30 工具箱VLM

四张固定Gazebo图片首版遮挡误判保留，增加view_clear后同图复核：在位detected、移除not_detected、红箱not_detected、遮挡unknown；不是独立测试准确率。真实工具循环卧室unknown→客厅detected→返航，SUCCEEDED，报告runs/toolbox-agent/20261030T100328Z_918abb85f9f4/report.md。154项回归通过，1条DDS警告，详细见docs/toolbox-vision.md。

## 2026-10-31 续作验收

配置/预算边界及相机观察修正后162项回归通过。初次新视角在位漏检保留；相机俯角增大后在位detected、红箱unknown（未达到预设not_detected）。新配置完整任务SUCCEEDED，卧室unknown、客厅detected、返回实际起点。报告runs/toolbox-final-20261031/20261031T030619Z_ef49cdd83ecc/report.md。校准数据不作为独立集准确率，详见docs/toolbox-vision.md。

## 2026-10-31 三类家居检查

- 新增背包挂墙、门关闭、厨房果盘完整命题与场景变体，复用视觉/导航/存储/报告。
- 首轮背包裁切unknown且返航主动取消，记录CANCELED；调整观察点后完整任务SUCCEEDED，三项detected并返航。报告runs/household-inspection/20261031T055130Z_cc3afcc8f34d/report.md。
- 真值位姿采集7张校准图，6张符合预期；开门近图unknown失败保留，后移复核not_detected。四种变体仍无真实图，不算全部评测通过。
- 构建与183项测试通过，1条DDS警告；详见docs/household-inspection.md。

## 2026-10-31 三指标实验

固定六轮家居目录检查：端到端严格成功3/6；视觉13/15（助手非盲可判读复核）；5次提交任务平均91.56秒，中位90.90秒，不含仿真启动。失败：启动一次、背包误判一次、开门unknown一次；不换样本、不在实验期间调代码。205项回归通过。完整口径与原始证据见 docs/metrics-experiment.md。
