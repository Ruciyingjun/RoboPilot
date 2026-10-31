<!-- 用途：说明受约束工具反馈循环、运行方法、验证口径及与静态计划模式的区别。 -->
# 工具反馈搜索 Agent

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

首版支持明确搜索契约：按给定地点顺序寻找 red_marker，找到即停止搜索；否则尝试下一处，最后返回本次任务起点。每轮由真实模型提交一个 robot_tool 调用，执行结果作为 tool 消息返回模型。不是先生成完整计划，也不是脚本冒充 LLM 决策。

## 使用

先在 Linux 桌面终端执行 ./robopilot sim-lite，等待 ready=true。另一个项目终端：

```bash
./robopilot search bedroom living_room
```

等价于：

```bash
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
set -a
source robopilot.local.env
set +a
ros2 run robopilot robopilot agent --places src/robopilot/config/places.home.yaml --search-places bedroom living_room --backend ros --output runs/home-agent-search
```

便捷脚本会清除通用密钥优先覆盖，再加载本机配置；手动运行应同样按需清除 ROBOPILOT_LLM_API_KEY。不要并行启动其他任务控制同一机器人。每次工具轮询都会调用模型并产生用量。

不启动 ROS 也可验证真实模型+合成图像分支：把 backend 改为 mock，并增加 --mock-images empty,red，使用单独输出目录。模型仍真实调用，mock 图像不代表仿真或真机。

## 首版范围

- 指令通过 --search-places 显式表达搜索契约，不接收任意自然语言搜索需求。自然语言 task 入口目前仍为原静态计划模式，未偷换为循环。
- 支持 list_places、query_memory、navigate_to、inspect_target、return_to_start、finish_task，共用一个 robot_tool 函数的 action 参数，不引入新框架或多 Agent。
- inspect_target 必须填写当前已成功到达且尚未检查的 place。检查对象仅 red_marker，图片不发给文本模型，模型接收结构化检测结果和本地证据路径。
- query_memory 仅返回历史地点/状态/时间摘要，不能当作本次检测。观测写入与报告由工具自动完成。
- 找到后禁止继续搜索；返航成功才允许 finish_task。所有有效观测均 not_detected 时可以完成搜索，但结果 found_at=null，不能描述为找到目标。
- 未知图像、地点不可达导致搜索不完整时为 PARTIAL；模型断连、协议错误、预算耗尽或不安全取消为 FAILED/CANCELED。不会把模型口述当作实际成功。
- 默认最多 24 轮、总墙上时间 600 秒；每次导航不超过 120 秒、图像不超过 15 秒；重复相同调用最多两次，预算耗尽仍失败停止。
- 总预算耗尽、模型断连或不安全取消时中止循环并尝试取消，不保证自动返航；没有崩溃恢复和真实人形动力学。

## 结构与清理

仅新增 agent_loop.py，复用原 HTTP、Nav2 后端、MissionExecutor 图像检查、SQLite 与报告。HTTP 客户端将工具名称参数化，避免复制第二套 API 客户端。便捷脚本的模型配置加载抽为一个函数，静态规划和循环共用；删除废弃 humanoid 字节码缓存，保留有效回归和实验失败证据。

报告沿用 report.md 与 mission.json，新增 agent.contract、agent.turns，保存工具参数、实际结果和 token 计数。不持久化模型 reasoning_content；DeepSeek 所需协议字段仅留在当前进程会话内。

静态 inspect/task 模式继续保留，用于固定路线与对照，未删除仍有用途的导航、错误处理和评测代码。

## 2026-10-30 验收

- 真实 DeepSeek+mock：6 轮，SUCCEEDED，卧室 not_detected→客厅 detected→返航，共服务报告 5446 tokens。报告 runs/agent-live-mock/20261030T051013Z_a8f8466f6b2a/report.md。
- 真实 DeepSeek+Gazebo（域70）：7 轮，SUCCEEDED，同样按观测反馈完成分支与返航，共服务报告 6796 tokens。模型第2轮 inspect_target 漏填地点，被拒绝后第3轮自行补齐，错误未执行且审计保留。报告 runs/agent-live-gazebo/20261030T051051Z_4d47bce12619/report.md。
- 完整回归 138 passed；新增10个循环测试，包括预算、提前结束、错序、未到点检查、unknown、模型断连、不安全导航与返航失败。
- 两条单次结果不是泛化成功率，不代表任意任务理解。单次模型请求次数从静态计划一次变为多轮，token与网络耗时随历史增长；因此保留静态模式。

## 工具箱目标扩展

当前可显式 --target toolbox，便捷入口 ./robopilot search-toolbox bedroom living_room。toolbox检查会把相机图像发送到已配置DeepSeek视觉服务，red_marker保持本地颜色检测；query_memory按目标区分。真实完整任务已单次成功，卧室unknown、客厅detected并返航。此前“仅红色”是首版历史范围，最新操作与反例见 [工具箱视觉说明](toolbox-vision.md)。任意自然语言循环仍未开放。
