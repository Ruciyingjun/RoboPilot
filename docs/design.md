<!-- 用途：说明 v0.2 的模块职责、巡检协议、观测记忆、执行状态与实现边界。 -->
# v0.2 设计说明

## 模块与数据流

结构化 JSON 或中文指令 → planner → schemas 严格校验 → MissionExecutor → NavigationBackend → ROS/Nav2 或 mock。

inspect 分支通过 backend.capture_image 获取图像 → perception 红色检测 → MissionStore 写入 SQLite、JSON 与带图像的 Markdown。

- schemas：与 ROS 无关的数据结构及输入校验。
- planner：受限中文语法、历史地点解析、可选 LLM 请求；输出统一校验。
- executor：顺序、依赖、有限重试、异常策略和记录。
- ros_adapter：独立 Context/SingleThreadedExecutor，Nav2 Action、TF、相机与取消。
- perception：红色连通区域检测及证据绘制，不查询仿真真值。
- storage：missions、steps、observations 持久化与报告。
- diagnostics / evaluation：运行环境诊断与只读任务统计。

## 计划协议 version=1

顶层 version、name、steps 必填，可选字符串 $comment 仅用于说明。1–32 个步骤，ID 唯一且为 ASCII 标识符；拒绝未知字段、重复 JSON/YAML 键、非法参数与非有限数值。

| 动作 | 参数与约束 |
|---|---|
| navigate | place 必填，来自命名地点配置 |
| inspect | place 必填、target=red_marker；depends_on 必须含最近一次移动步骤，且该步骤为导航到同一 place |
| return_to_start | 不带 place，使用任务开始时捕获的定位位姿 |

公共参数：timeout_s 为 0.1–600 秒，max_retries 为 0–2，on_failure 为 continue/abort，depends_on 为不重复的前序步骤 ID。

地点配置 version=1、frame_id=map，每个地点保存 x/y/yaw。places.demo.yaml 仅用于默认 tb3_sandbox；其他地图需重新标定。

## 状态与取消

任务状态 PENDING → RUNNING → SUCCEEDED / PARTIAL / FAILED / CANCELED；步骤状态还包括 TIMED_OUT 和 SKIPPED。

任一依赖未成功时跳过步骤。全部步骤完成为 SUCCEEDED，部分成功为 PARTIAL；检查结果 not_detected 表示有效检查没发现目标，可以是步骤成功。unknown 表示无法判断，为检查失败。

导航期限使用单调墙上时间，包含发送与等待结果。取消应答不等于结束，必须收到终态才能继续；未确认终态时停止后续目标。Nav2 自身恢复和任务重试分开记录。

## 相机与图像证据

仿真 RGB 320×240、2 Hz，主题 /robopilot/camera/image_raw。inspect 订阅后只接受时间戳晚于检查开始、且不超过 2 秒旧的图像。等待对应图像时刻的 map→base_link TF，将位姿、图像时间戳和 frame_id 一同写入观测。

红色 HSV 阈值加连通区域面积过滤，方法名 opencv_hsv_red_v1。画面过暗/无效/缺失为 unknown；有效画面没有足够大的红色区域为 not_detected；保存 PNG，检测到时加框。该方法不识别工具箱类别，不证明房间覆盖完整。

## 追加观测与记忆

observations 每条包含 id、mission_id、step_id、place、target、backend、observed_at、status、图像时间戳、位姿与 evidence_path（如有）。重复保存任务不会重复插入观测。

last_seen 查询指定后端下最新 detected；后来的 not_detected/unknown 不覆盖历史。历史只用于选择复查地点，当前结论来自新观察。mock 和 ROS 不混用，更换地图须另建运行目录。

UTC 用于记录，单调时间用于期限，ROS 时间用于 TF 和图像。SQLite 为持久记录，JSON/Markdown 为导出快照；进程突然退出可能留下 RUNNING，不自动恢复。

## 规划边界

rules 模式是受限中文解析器，不是 LLM。外部 LLM 模式通过 HTTPS 聊天补全兼容接口生成纯 JSON，再严格校验；没有配置服务时明确报错，不自动伪造模型结果。接口目前仅有模拟响应测试，未进行实际模型调用。

## 验证边界

当前单机器人、单任务执行器，默认命名空间、map/base_link 坐标系。没有实现 VLM、工具箱语义识别、门状态、SLAM、自动探索或真机部署。真实实验与日志见 acceptance.md；少量功能验收不能证明泛化能力。

## v0.3 规划扩展

planning_context 校验中文别名，向规划器提供 canonical 地点 ID、last_seen 与最近 10 条观测摘要；不传图像文件和凭据。

llm_client 支持纯 JSON 和单个 create_plan 工具调用。planner 严格校验每次响应，最多一次修复；协议、服务或最终校验失败不使用规则兜底。规则解析明确标记 rules。

planning_io 保存原始指令、来源、上下文、校验结果和耗时，用摘要关联规范化计划和地点快照；run 检查 sidecar 后才创建执行后端。mission 复用同一生成/校验/执行链路，默认 mock，可显式选择 ros。

规划审计是可追溯和一致性记录，不是签名。自动协议校验不保证完整理解用户语义。DeepSeek 的 JSON/工具小范围任务已真实验收，其他模型和泛化行为仍待测。操作见 planning.md。

## v0.4 真实模型反馈后的修正

capabilities 在模型请求前拒绝已知不支持技能和显式未知检查点，防止已知案例中的动作省略。模型 JSON refusal 触发 PlanningRefusal，直接结束，不使用格式修复覆盖拒绝。

DeepSeek 思考模式不允许强制指定工具，故使用 auto 并继续要求返回单个 create_plan；所有实际参数仍经相同校验。模型能力检查和应用层保守规则分开记录，不能据此声称完整意图验证。

## v0.5 有限意图约束与评测

intent.py 从有限中文表达提取独立约束，generate_plan 在请求前构造合同并澄清不支持结构，模型得到相同约束。每个候选先检查协议，再比较动作/地点/目标及顺序，保留首次候选和修复过程。

benchmark.py 加载人工标签与合成记忆，不创建导航后端。预期由数据集独立提供，不从 intent.py 生成。计分分开记录应用拒绝、模型拒绝、候选完整性和技术错误；无效模型计划继续计分，技术失败停止并展示覆盖率。

语义约束有限，不验证任意嵌套、否定或开放世界指令。固定集26/26是受约束管线结果。详见 planner-benchmark.md。
