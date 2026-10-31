<!-- 用途：持续记录已完成工作、当前状态、下一步计划、验证结果及开发历史。 -->
# RoboPilot 项目进度

> 本文件是项目状态入口。每次开发结束都更新「当前状态」「已完成」「下一步」「验证记录」。
> 已编写、自动测试通过、Gazebo 实测通过分别记录；mock 结果不能作为机器人实验结果。

> 2026-10-30 清理说明：旧 smoke、mock、早期校准目录和构建日志已删除。下方历史路径用于追溯开发经过，不保证文件仍存在；保留的最新证据见 README 与 log/verification/cleanup-summary.json。

## 当前状态

- 更新时间：2026-10-31（Asia/Shanghai）。当前版本：v0.5；增量支持三类家居关系/状态检查。
- 阶段：M1 导航、M2 受控视觉、M3 地点级记忆均已有 Gazebo 实测；M4 已实现受限中文规则规划和可配置 LLM 接口；M5 已建立小样本验收与统计。
- 正在做：受约束工具反馈搜索已完成首版实测与代码/产物清理；下一步扩展语义感知与任务契约。
- 本轮完成：26 条人工预期、benchmark-plan 命令、首次候选/应用拒绝/技术错误分开计分、规则基线与真实 DeepSeek 评测、否定与反向顺序 Gazebo 验证、生命周期查询有界重试。
- 验证结论：最新完整回归 205 项通过；真实模型工具循环成功，家居三轮固定任务成功。历史规划评测 DeepSeek 26/26（含10条应用前检）、规则17/26，见 docs/planner-benchmark.md。
- 尚未完成：独立语义视觉测试集、多类别/多视角评测、模型任务理解大样本验证及视频；工具箱VLM已接入，颜色目标仍独立保留。

最新增量：工具箱VLM已完成反例复核与真实反馈循环，续作补齐配置/超时与相机裁切问题，162项回归通过；受约束 LLM 工具反馈搜索已完成真实 DeepSeek+Gazebo 分支验收，138 项测试通过；2026-10-30 同一世界连续三轮家居巡检 3/3 成功，独立 Nav2 进程正常关闭且资源清理通过；酒店服务机器人已完成客厅→卧室→起点闭环，头部相机客厅检测到红色、卧室未检测到；厨房导航与返航成功。单次受控验证，不代表泛化。查看 docs/home-scene.md。

## 已完成的实现

| 功能 | 实现内容 | 验证状态 |
|---|---|---|
| 计划校验与执行 | navigate / inspect / return_to_start，顺序、依赖、有限重试、超时与取消 | 核心与 ROS 测试通过 |
| Gazebo 导航 | 默认地图检查点 A、B 与本次起点返航 | 真实 Nav2 导航通过 |
| 相机与场景 | RGB 320×240、2 Hz，演示标记，保留原雷达和导航 | doctor 实测 ready=true |
| 视觉检查 | 必须使用检查开始后的新图像；关联图像时刻 TF；红色区域检测与 PNG 证据 | A detected / B not_detected 实测通过 |
| 语义观测记忆 | observations 追加历史、最近发现查询、mock/ROS 分离 | 查询驱动实际复查、目标移除后更新通过 |
| 中文规则规划 | 中文地点别名、mission 入口、命名地点与历史复查 | v0.3 真实中文巡检与复查通过 |
| 外部 LLM 接口 | JSON/工具、历史上下文、有限修复及明确拒绝、token 审计 | 真实 DeepSeek 两种模式成功；历史复查已执行 |
| 记录与报告 | SQLite、JSON、Markdown、规划来源及上下文、计划/地点摘要 | 审计一致性、失败不执行与真实报告验证通过 |
| 任务统计 | 按后端只读汇总记录、任务/导航完成率和耗时 | 测试和真实数据汇总通过；无视觉准确率结论 |

## 接下来做什么

优先：重复验证家居巡检稳定性与不同起点，再接工具箱语义识别。

1. 在固定回归集之外扩充独立改写和扰动，重复评测拒绝误判、完整性边界及启动稳定性；不能将当前 26/26 当作泛化结论。
2. 根据岗位需求决定是否将红色标记升级为工具箱检测或 VLM；保留 unknown 和证据约束。
3. 多起点、障碍、遮挡和目标变化重复评测，记录人工真值，区分任务、导航和感知指标。
4. 录制实际 Gazebo 演示视频，整理可复现材料与准确简历表述。

下一次继续开发时，先读本文、README 和 docs/acceptance.md，避免重新实现已通过功能。运行步骤见 docs/usage.md。

## 里程碑

| 里程碑 | 验收条件 | 当前状态 |
|---|---|---|
| M0 环境 | ROS/Gazebo/Nav2、传感器和定位可用 | 本机实测通过 |
| M1 导航执行 | A→B→起点，失败策略有证据 | 实测通过，含超时取消后返航 |
| M2 视觉检查 | 到点新图像、结果和证据 | 红色标记受控版本实测通过；非语义识别 |
| M3 语义记忆 | 历史查询驱动再次检查 | 实测通过，含目标移除场景 |
| M4 自然语言 | 自然语言→计划→执行闭环，记录拒绝与失败 | 真实 DeepSeek 小范围通过；语义完整性与泛化评测仍待扩展 |
| M5 评测交付 | 可复现实验、指标、视频 | 固定 26 条评测、规则/模型对比与代表执行已完成；独立扰动和重复评测、视频待做 |

## 已知限制与设计决定

- 当前虚拟机：Ubuntu 24.04 ARM64、4 核、约 6 GiB 内存，OpenGL 使用 llvmpipe 软件渲染。
- 先使用现成 Nav2 地图，不开发 SLAM 或自定义导航算法。
- 默认后端为 mock；必须显式指定 `--backend ros` 才会发送导航目标。
- places.demo.yaml 已在默认 tb3_sandbox 验证；更换地图或出生设置须重新标定。地点不代表真实办公室/实验室。
- v0.2 接受 inspect，但当前仅支持 red_marker；检查必须依赖最近一次到达同地点的导航。
- 导航取消必须确认终态；无法确认时中止任务，不继续发送目标。
- 超时使用单调墙上时钟，暂停仿真不会导致无限等待；取消另有有限等待时间。
- SQLite 保存任务、步骤及 observations；记忆按运行数据库与后端隔离，更换地图应使用新目录。
- 暂不支持任务崩溃后自动续跑；被强制终止时遗留 RUNNING 记录，需要人工核对。
- 当前为单机器人、单任务执行器；运行时不要再用 RViz 或其他客户端发送竞争导航目标。
- 包的维护者信息是占位值；公开发布前由项目拥有者填写维护者和许可证。

## 验证记录

| 日期 | 验证 | 结果 | 能证明什么 |
|---|---|---|---|
| 2026-10-27 | 环境与包依赖检查（前序会话） | 通过 | Nav2 与仿真依赖已安装 |
| 2026-10-27 | 启动文件解析、Python 导航接口导入（前序会话） | 通过 | 软件接口可加载 |
| 2026-10-27 | OpenGL 检查（前序会话） | llvmpipe，无硬件加速 | 可创建 GL 上下文，尚不能证明仿真帧率 |
| 2026-10-27 | pytest，含 ROS 测试服务端 | 35 passed，4.28 秒 | 核心任务逻辑、真实 DDS/Action 通信与取消边界通过 |
| 2026-10-27 | colcon build | 1 package finished | ament_python 包可构建并安装入口及配置资源 |
| 2026-10-27 | colcon test | 35 passed，4.32 秒 | 标准 ROS 工作空间测试流程能发现全部测试并通过 |
| 2026-10-27 | 安装后 CLI：validate / 成功 / 部分完成 / 取消未确认 | 退出码分别为 0 / 0 / 1 / 1，状态符合预期 | 安装入口、打包资源和任务报告链路可用 |
| 2026-10-27 | 安装后的 simulation.launch.py --show-args | 通过 | 启动描述与依赖可解析；未启动仿真 |

验证文件（本机生成，build/log/runs 被 .gitignore 排除）：

- [pytest XML](log/verification/pytest.xml)、[colcon pytest XML](build/robopilot/pytest.xml)、[CLI 冒烟记录](log/verification/cli-smoke.txt)。
- [成功演示报告](runs/smoke-success/20261027T120210Z_3070afdfeb8c/report.md)。
- [部分完成演示报告](runs/smoke-partial/20261027T120210Z_51ec649e73f3/report.md)。
- [取消未确认演示报告](runs/smoke-unsafe/20261027T120210Z_c610bd2012f6/report.md)。
- 以上演示全部使用 mock 后端，不能计入机器人任务成功率。

## 开发日志

### 2026-10-27：建立初版执行链路

- 创建项目目录、Python ROS 包、配置与示例计划。
- 将计划/执行/存储与 ROS 适配分开，使执行逻辑可独立验证。
- 加入任务级状态、每次尝试结果、失败传播和报告后端标记。
- 编写核心测试与 ROS Action 测试服务端，开始验证。

### 2026-10-27：网络中断后接续、修复并完成初版验证

- 保留已有架构与代码，从未完成的自动验证接续。
- 首次测试发现 5 项失败：4 项源于自定义 ROS Context 与默认执行器不匹配，1 项源于内存中的元组与落盘 JSON 列表不一致。
- 为 ROS 导航后端绑定独立 SingleThreadedExecutor，并在关闭时释放；修复任务序列化，使保存的计划可以重新校验。
- 拒绝重复 YAML 键和过大数值，防止地点被静默覆盖或校验异常退出。
- 补充延迟接受目标、取消被拒绝、导航未激活、过期 TF、缺失仿真时钟等回归测试。
- 标准 colcon test 首次未发现测试；在 setup.py 声明 pytest 测试依赖后修复，全部 35 项通过。
- 验证安装后的 CLI 成功/部分完成/停止执行路径及本地报告；更新 README 与本文。
- 本轮未启动 Gazebo；地图检查点标定、机器人运动效果和渲染性能仍待实测。

### 2026-10-27：补齐文件用途说明与效果查看指南

- 核对并补齐项目维护文件的开头用途说明，覆盖源码、测试、配置、打包文件、资源标记与文档。
- JSON 示例使用字符串 `$comment` 字段；校验器允许并忽略该说明，仍拒绝其他未知字段。
- XML 声明保持首行，用途注释放在声明后；自动构建产物及历史运行数据保持原生格式。
- README 增加成功、部分失败、取消未确认三种演示的预期效果，以及报告和 Gazebo 的查看方法。
- 验证：35 项既有测试通过，带用途说明的示例计划校验通过；文件头与 JSON/XML 格式兼容检查通过。

### 2026-10-28：整理 README 为四个明确部分

- 按「1. 项目目标、2. 已完成、3. 当前阶段、4. 下一步」重整 README。
- 保留一条可直接运行的 mock 演示命令，将完整构建、仿真和测试步骤移到 docs/usage.md。
- 明确当前仅完成代码与自动验证，Gazebo 实测、视觉、语义记忆和 LLM 尚未完成。
- 本次仅修改文档，未新增功能、未启动仿真、未重新运行功能测试。

### 2026-10-28：完成 v0.2 巡检与记忆闭环

- 独立 ROS 域 41 复现 AMCL 等待初始位姿的问题，设置默认出生位姿后导航恢复；实际 A→B→起点通过。
- 在 launch 时扩展已安装机器人和世界，增加低频 RGB 相机和红色标记，不修改系统包。
- 增加 inspect 协议与执行分支、新图像/图像时刻 TF 检查、颜色检测和证据落盘；unknown 视为检查未完成，not_detected 仍可为已完成检查。
- observations 追加式记录、最近发现查询与后端隔离；验证 A 检测到、B 未检测到、历史驱动复查、移除标记后复查未检测到且历史保留。
- 增加 plan / memory / doctor / evaluate 命令，提供受限中文规则规划和可配置外部 LLM 接口；没有实际外部模型调用。
- 注入真实导航 0.1 秒超时，确认取消终态后返航成功；失败样本单独保存。
- 标准构建与测试通过：52 tests、0 errors、0 failures、0 skipped。
- 更新 README 四部分结构、使用指南、设计说明与独立验收文档。已有 3 次相关巡检任务、4 次真实图像观测，不将少量样本作为泛化指标。

### 2026-10-28：排查手动运行的 Nav2 就绪超时

- 查看 my-demo/20261028T073840Z_0c9cafd5eb27 失败记录：未捕获起点、没有发送导航目标，准备阶段 30 秒超时。
- 对应日志确认：15:37:11 全局代价地图因缺少 map→base_link 激活失败，导航生命周期管理器中止启动；15:37:25 才收到初始位姿，因此初始化后导航栈仍未完整激活。
- 15:40:07 用户通过 Ctrl+C 关闭仿真；之后的退出报错不能当作此次准备失败的起因。
- 使用指南补充：启动后及时初始化；若导航 bringup 已中止，应重启仿真后再初始化与检查。本次仅诊断和补充文档，未替用户启动或控制仿真。

### 2026-10-28：v0.3 中文任务、模型上下文与规划审计

- 检查确认 ROBOPILOT_LLM_ENDPOINT / MODEL / API_KEY 均未配置，本轮没有请求外部模型。
- 新增中文地点别名配置，允许 A点、B点等标签映射到已有检查点，拒绝未知地点和别名冲突。
- LLM 获得指定后端的历史发现与最多 10 条观测摘要；JSON 与 create_plan 工具调用均复用严格校验。非法计划最多修复一次，网络/协议错误不降级为规则成功。
- 新增 mission 指令入口；规划与审计成功后才创建执行后端。保存原始指令、规划器、上下文与校验结果；run 拒绝摘要不匹配或 REJECTED 的规划记录。
- 新增 initialize_demo=True 启动选项；首次集成暴露普通 CLI 不接受 launch Node 附带 --ros-args，改用 ExecuteProcess 后自动诊断 ready=true。
- 初次启动失败记录保留于 runs/v03-gazebo/20261028T104952Z_13f99908873c，不作为成功样本；修正后两次真实任务均成功。
- 中文巡检报告：runs/v03-gazebo/20261028T105122Z_cc9fc14cc789/report.md。
- 历史复查报告：runs/v03-gazebo/20261028T105248Z_87ad42fd85a8/report.md；审计包含前一次 A 点发现记录。
- 最终 colcon build/test 通过：73 tests、0 errors、0 failures、0 skipped。源码测试 XML：log/verification/pytest-v03.xml；标准流程报告：build/robopilot/pytest.xml。
- 新增 docs/planning.md 和空密钥配置模板，同步 README、设计及使用指南；没有将模板当作已配置的模型。

- 收尾补充鉴权头非法字符检查，避免底层异常回显密钥；最终回归为 73 项通过。规划配置资源已安装，文件头说明和文档链接检查通过；本轮测试仿真已退出。

### 2026-10-28：按用户示例适配 DeepSeek（v0.3.1）

- 核对 DeepSeek 官方首次调用、思考模式、JSON 和工具调用文档；支持 deepseek-flash、thinking=enabled、reasoning_effort=high、stream=false。
- 新增 llm_config，支持 DEEPSEEK_API_KEY 和 DeepSeek 默认端点；通用 ROBOPILOT 配置继续兼容。单次 DeepSeek 请求默认超时 120 秒，可配置 1–300 秒。
- 使用标准库发送与 SDK 等效的 HTTP 请求，不安装 SDK、不改变 ROS Python 环境；JSON 模式发送 response_format=json_object，不给思考模式传无效 temperature。
- 思考工具调用修复在内存中保留并回传原 assistant/tool 对话字段；审计只记录参数、校验结果和 token 用量，不写推理文本或鉴权信息。
- 新增 deepseek.env.example 和 docs/deepseek.md；配置对象 repr 隐藏密钥，测试自动隔离真实模型环境变量，避免误发付费请求。
- 最终构建与回归：85 tests、0 errors、0 failures、0 skipped；结果见 build/robopilot/pytest.xml 和 log/verification/pytest-deepseek.xml。
- 本机未配置 DEEPSEEK_API_KEY / ROBOPILOT_LLM_API_KEY，本轮所有模型响应均为本地测试替身，不能作为真实模型验收结果。

### 2026-10-28：README 补充 DeepSeek 密钥配置位置

- README 保留四部分结构，在第 3 节明确本机配置位置、填写字段、环境加载和仅显示设置状态的检查命令。
- 根目录 robopilot.local.env 不存在时创建，预填 DeepSeek 参数，密钥为空，权限 600；不覆盖已有配置。
- 该文件由 *.local.env 忽略规则排除；补充清除通用密钥优先覆盖和同终端 source 的说明。
- 本次仅更新本地配置模板与文档，没有读取或输出真实密钥，也没有实际 API 调用。

### 2026-10-28：v0.4 真实 DeepSeek→Gazebo 验收

- 用户配置本地密钥后，加载配置进行真实请求。首次自动审批拦截后，核对上下文仅含默认仿真 A/B 标签和红色标记摘要；在相同数据范围下复核获准后发送。未输出密钥，也未发送图片或个人文档。
- JSON 模式首条真实计划符合 A→检查→B→检查→返航，耗时 3.564 秒，服务报告 total_tokens=1466；Gazebo 执行成功。
- 工具模式首次 HTTP 400，官方文档确认思考模式不支持 required/指定函数 tool_choice；改为 auto、保持模型显式提交 create_plan 后，真实历史复查规划成功，耗时 1.884 秒，total_tokens=1750，随后 Gazebo 执行成功。
- 异常指令实测发现：未知 C 点被模型拒绝；「去 A 点打开门」却被模型静默省略开门动作并提交部分计划。该计划从未执行，已保存原始证据并将其审计状态改为 REJECTED。
- 新增 capabilities 前置保守检查：已知不支持的门操作、工具箱语义、抓取、探索及显式未知检查点，在请求模型前拒绝。它只覆盖已知模式，不能保证理解任意自然语言。
- 新增 PlanningRefusal，模型返回明确 refusal 时立即结束，不请求修复。真实未知房间指令一轮拒绝，耗时 1.174 秒，total_tokens=1037。
- 真实报告：runs/deepseek-gazebo/20261028T114703Z_25067ead64f0/report.md（JSON）；runs/deepseek-gazebo/20261028T114950Z_093c8c432ca0/report.md（工具历史复查）。
- 原始负例、前置拒绝与汇总见 log/verification/deepseek-negative-probes.json、deepseek-capability-guard.json、deepseek-live-summary.json；初次 HTTP 400 审计单独保留。
- 自动回归 92 项通过；最终构建和 colcon 测试结果继续记录于 build/robopilot/pytest.xml。本次仿真使用独立域 43，收尾停止，不改变默认域的用户任务。

### 2026-10-29：v0.5 固定规划评测与有限完整性约束

- 新增 intent.py，提取有限中文任务的动作/地点/目标序列、禁止地点、不返航与历史地点约束；检查遗漏、多余、顺序错误，条件/循环/歧义/冲突明确澄清。
- 保留模型首次候选的 protocol_valid、intent_valid 和计划内容；应用可最多修复一次，明确 refusal 不修复。约束会发送给模型，不能把结果解释为无约束模型能力。
- 新增 26 条独立人工预期（16 accept、10 reject），使用纯合成历史夹具，不读取真实观测库；新增 benchmark-plan、逐例落盘、中断保留和清晰退出码。
- 规则基线最终 17/26，9 个句式解析失败保留；真实 DeepSeek 管线 26/26，其中 16 个模型样本首轮完整、10 条应用前检拒绝、0 次模型拒绝。16 次请求共服务报告 16704 tokens，平均案例 2.299 秒。
- 真实报告：runs/planner-benchmark-deepseek/20261029T055346Z_48c129c4；规则最终报告：runs/planner-benchmark-rules-final/20261029T060124Z_a0fde3ff。
- Gazebo 三次执行尝试：首次反向任务准备超时、全部 SKIPPED；禁止 B 点的 A 巡检成功；环境诊断后反向 B→A 巡检重试成功。首次失败未删除，不能声称 2/2 首次成功。
- 回归曾出现一次生命周期准备超时；检查发现待处理查询没有单次期限，补充 1 秒查询重试和具体未就绪诊断，延迟响应故障注入测试通过。不将其当作所有超时根因的证明。
- 最终 colcon test：124 passed、1 warning（DDS 响应清理），0 errors/0 failures/0 skipped；报告快照 log/verification/pytest-benchmark-final.xml。
- 新增 docs/planner-benchmark.md，同步 README、PROGRESS 与设计。测试仿真在域 44 中完成并已停止；没有修改用户默认域进程，也未改动本机密钥。

### 2026-10-29：家居场景第一版

- 新增 home_scene.py，生成客厅、卧室、厨房、玄关及本地几何家具，工具箱带箱盖与提手；不下载外部模型。
- 增加 scene:=home 启动选择，默认 demo 保持；新场景机器人出生在 (2.7,-2.1,1.5708)，拒绝误用旧 initialize_demo。
- 从相同碰撞几何生成配套地图；places.home.yaml 为候选点，尚未导航验收。
- colcon build 通过；域 61 短时 Gazebo 启动确认地图 220×180 成功读取、机器人创建成功，之后停止。日志 log/verification/home-startup.log。
- ROS 系统 Python 回归 124 passed；首次非 ROS Python 111 passed、1 skipped 后已补跑。
- 没有设置初始定位、未宣称端到端家居巡检通过；工具箱仍是布景，没有语义检测能力。文档 docs/home-scene.md 与 README 已同步。

### 2026-10-29：修正家居 GUI 世界连接冲突

- 用户截图显示 RViz 为家居地图、Gazebo 为 Panda 机械臂场景；检查发现多个 Gazebo server，其中两个残留 server 使用默认 Transport 分区；上游 GUI 未指定世界，存在跨世界连接冲突。
- 启动入口为每次启动设置独立 GZ_PARTITION，传递给服务器、GUI、桥接和机器人生成服务，避免跨世界发现。未终止其他项目进程。
- 先前短时验证仅证明地图读取和实体创建，不能证明 GUI 显示正确世界；此前验证范围不足。更新文档，需用户重启当前启动后复核画面。

### 2026-10-29：家居第二版视觉细化

- 根据截图中方块感较强的问题，增加木地板、瓷砖缝、沙发坐垫/抱枕、桌腿/书/杯子、窗框、床头灯、柜门、灶眼、水龙头、冰箱和工具箱细节。
- 植物叶簇使用球体，灯与杯子使用圆柱；场景背景及环境光调整。未引入外部资产或图片服务。
- 装饰不添加碰撞，保留现有粗碰撞与同源地图；场景 219 个模型、37 个碰撞体，模型名唯一。
- colcon build 与 gz sdf -k 通过；尚未核对第二版实际 GUI 画面及软件渲染帧率，需重启查看，不能声称照片级真实。
- README 与家居指南同步；下一步根据 GUI 反馈调整视觉和性能，随后进行房间导航与观察点校准。

### 2026-10-29：家居第三版材质与软装

- 新增 home_materials.py，标准库生成固定种子的 6 张 256×256 PNG，使用 PBR albedo/roughness/metalness，零新增依赖，无网络素材。
- 为木地板/木家具、沙发、墙面、地毯及台面应用纹理，共 142 处引用；补充圆润抱枕、电视柜抽屉、壁画和果盘。
- 保留原粗碰撞与路线；装饰不进入地图，不新增目标识别能力。
- colcon build、gz sdf -k 与纹理路径检查通过；记录 log/verification/home-material-check.txt。实际 GUI 美观程度与帧率仍待用户重启复核。
- 完整回归 124 passed；隔离域 62 短时启动确认地图读取和机器人生成。日志包含虚拟机 EGL 警告与未初始定位的 TF 警告，未据此宣称图形渲染性能已通过；日志 home-material-startup.log。

### 2026-10-29：连续木地板修正白缝

- 根据截图，白色短线疑似零高度网格与地板共面/拼板间隙造成；未将截图推断当作已复现的根因。
- 删除 100 块独立拼板，改为连续地板表面；视觉抬高 4 mm，碰撞不动。新增 512×512 木地板纹理，以棕色细线代替几何缝隙。
- 保留厨房和地毯覆盖层、原地图与家具碰撞；减少场景实体数量。
- 构建、连续地板结构与 SDF 验证；实际 GUI 白缝消除情况待重启确认。README、家居指南同步。

### 2026-10-29：人形外观与头部相机

- 新增 humanoid.py，固定头部、躯干、双臂与双腿，保留底盘/轮子/雷达和差速运动；约 1.33 米高。上身为简化碰撞，仍沿用底盘惯性，不是人形动力学或双足控制。
- 相机移动到 base_link 的 (0.15,0,1.23)，俯角约 20 度；保留图像话题/分辨率/频率，新增 camera_link 与 optical_frame 固定 TF。
- Gazebo 和 RViz 使用相同生成的外观，关闭上游重复 robot_state_publisher；默认 humanoid，可显式切回 turtlebot。
- colcon build 通过。后续必须重新验证头部视角的目标可见性、导航和碰撞；不复用旧低位相机的视觉成功结论。
- README、家居说明同步。
- 两种 robot_body 的 SDF 校验均通过，相机帧和 URDF 固定关节检查通过；校验保留上游 gz_frame_id 扩展字段警告。完整回归 124 passed；新外形实际运行、头部图像及导航尚未完成验收。

### 2026-10-29：按用户要求替换为酒店服务机器人

- 删除 humanoid.py，使用 service_robot.py；默认 robot_body:=service，取消人形模式。
- 新造型为圆底座、立柱、胸前屏幕、圆形顶部与镜头，约 1.2 米高；无四肢。12 个外观部件，仍为原差速驱动，屏幕为静态装饰。
- 相机改为 (0.17,0,1.075)、俯视约 20 度；Gazebo、URDF 与光学 TF 同步，导航与视觉仍需实测。
- 检查发现额外两个 Gazebo server 占用 CPU，但未确定 GUI 无响应根因，未擅自停止其他项目；建议先关闭 RViz 查看外观。
- 更新 README 与家居指南；构建和两种模式 SDF 检查，实际 GUI 流畅性待重启确认。

### 2026-10-29：酒店服务机器人家居巡检实际校准

- 新增 doctor --initialize-home（与 --initialize-demo 不可同时使用），从默认玄关出生位姿初始化；launch 增加 initialize_home:=True，仅适用于新鲜家居世界。初始化实测 clock advancing、360 束雷达、头部相机及定位 ready=true。
- 发现客厅/厨房原门洞约 0.3 m，修正为 1.1 m；同源几何地图同步更新。首次任务主动中断以修改门洞，报告 PARTIAL，保留 runs/home-calibration/20261029T135406Z_d5b659493fac/report.md，不能归为纯导航失败率样本。
- 新增 aliases.home.yaml、home_inspection.json、home_kitchen.json；客厅点 (-2.5,1.1,0.367)、卧室 (1.7,1.5,0)、厨房 (-2.5,-2.3,-1.57)，起点为本次执行捕获实际位姿。
- 客厅→检查→卧室→检查→返航全部 SUCCEEDED：runs/home-calibration-v2/20261029T135516Z_0b55658fb1e8/report.md。客厅 detected、卧室 not_detected，目视核对相机证据可见工具箱红色区域，不是语义识别。
- 厨房→返航 SUCCEEDED：runs/home-kitchen-calibration/20261029T135631Z_c0ea642305c7/report.md。未进行厨房视觉验收；玄关仅验证出生/返航邻域，不将 entrance 命名点当作额外独立导航测试。
- colcon build 与完整回归 124 passed。单次受控成功不等于不同起点、场景变化或 GUI 性能通过。校准使用独立 ROS 域，停止自建仿真，不终止其他服务；未调用模型或使用密钥。
- README 与家居操作指南更新可复现命令及初始化边界；下一步重复实验和工具箱语义识别。

收尾发现：发送 SIGINT 后 Nav2 组件容器在清理阶段出现 Magick/SIGSEGV（最终退出 -6）；发生在两份任务报告成功完成之后，未遗留本次启动进程。该退出异常根因尚未确认，不能将运行成功等同于退出清理无异常，后续需排查。日志 log/verification/home-service-calibration2.log。

### 2026-10-30：路线分析与持久快捷入口

- 核对用户真实 LLM 任务 runs/home-llm-demo/20261030T021627Z_22fe93054485/report.md：deepseek-flash、卧室→客厅→返航、SUCCEEDED。与旧 JSON 的房间访问顺序相反；局部轨迹差异没有足够日志比较，不声称模型决定绕行。
- 新增根目录可执行 robopilot：sim/sim-lite、inspect、task、plan、doctor、build；自动定位项目、source Jazzy/工作区，task/plan 按需加载本机密钥。未修改用户 shell 配置，密钥未写入脚本或打印。
- 固定家居地图/别名、真实 ROS 后端、输出目录与 90 秒准备期限；允许末尾追加 CLI 参数。
- bash -n、帮助入口、inspect --help、task --help 通过；本轮未调用模型、未移动机器人，未重跑无关全量回归。
- README 与家居指南同步，明确 sim 初始化只适用于全新世界、输出记忆库分离与预览不执行。

### 2026-10-30：家居重复巡检与关闭稳定性

- 检查时无残留 Gazebo，无操作其他项目进程；glxinfo 证实 CPU llvmpipe、无硬件加速，GUI 卡顿根因不直接归于外观。
- 首次启动因根目录同名 robopilot 文件触发 malformed launch argument；修正便捷脚本为明确 launch 文件绝对路径，文档启动命令同步更新。该启动失败独立保留在 home-stability-launch.log，不算巡检成功样本。
- 原 OnShutdown 会在子进程运行时删除纹理/地图，改为 atexit 清理；默认 use_composition=False，避免共享组件容器并发关闭风险。两项同时调整，未证明原 SIGSEGV 根因。
- 域 66 同一世界固定计划连续 3 轮 SUCCEEDED，耗时 53.871/49.902/52.867 秒，每轮客厅红色 detected、卧室 not_detected、返航成功。未重置出生位姿，不代表不同场景泛化。
- SIGINT 正常关闭，launch 退出 0，各独立 Nav2 进程正常退出，无本次 Magick/SIGSEGV；临时资源目录清除。记录 log/verification/home-stability-launch2.log、home-stability-summary.json、home-stability-rounds.json。
- 构建通过，124 项回归通过、1 条 DDS 清理警告。新增 docs/stability.md，更新 README 与使用说明。

- GUI 首次域 67 冒烟发现上游 shell/ruby 包装退出而 GUI 子进程残留；已核对身份并清理自己的残留，原失败日志保留。
- 新增 gazebo_gui.py，以独立进程组运行 GUI，关闭时对本组有界升级 INT/TERM/KILL；上游仅启动服务器，本入口管理 GUI，避免包装进程退出而实际 GUI 残留。
- 修正后域 68 GUI 短时启动 15 秒、doctor ready=true、launch 退出 0，无本次进程残留，无本次 Magick/SIGSEGV。没有测量 GUI 帧率和交互响应，不宣称原卡顿完全修复。
- 新增 test_gazebo_gui.py，验证自然退出码与忽略关闭信号时的清理，最终完整回归 126 passed（本次无警告）。记录 home-gui-managed.log/json；新增稳定性报告 docs/stability.md。

### 2026-10-30：修正 GUI 条件被上游覆盖

- 用户重启后导航 ready=true 却无窗口；检查当前 launch 日志没有 GUI 进程启动，确认不是加载缓慢。
- 根因是上游 IncludeLaunchDescription 写入共享 headless=True（用于关闭上游 GUI），后续自管 GUI 条件再次读取共享配置而被跳过。修正为在 simulation(context) 内捕获原始 headless 字符串，GUI 条件使用该固定值。
- 新增两种 headless 值的回归测试，模拟上游覆盖后仍保持用户原始 GUI 意图。
- 此前 managed GUI 验证只证明 launch 存活与退出，没有核对窗口是否创建，验收不足；本轮加入 xwininfo 实际窗口检查，保留原记录。

本轮独立域 69 实测 gui_window_present=true，关闭 launch 退出 0；完整回归 128 passed、1 条 DDS 警告。用户原域仿真未被停止。

### 2026-10-30：受约束工具反馈循环（首版）

- 新增 agent_loop.py（约172行），复用 MissionExecutor 检查、Nav2、HTTP与SQLite报告；没有额外Agent框架。单一robot_tool函数分发6类工具，每轮接收真实执行结果，模型再决策。
- 首版为显式 --search-places 契约：按顺序找red_marker，检测到即停止搜索并返航。不是任意自然语言任务；原task入口继续静态计划，不混淆两者。
- 检查需先成功到点，拒绝越界/错序/提前finish；确认返航才完成。不安全动作中止，默认24轮/600秒/导航120秒，unknown或不可达保留不完整结果，不把模型总结当执行证据。
- llm_client 工具名参数化，复用DeepSeek工具协议与临时reasoning字段，不落盘推理文本。模型只收到仿真标签、检测状态/本地证据路径，未发送图片或个人文档。
- 真实DeepSeek+mock 6轮成功、5446 tokens；真实DeepSeek+Gazebo 7轮成功、6796 tokens。卧室not_detected后去客厅detected，返航并finish。Gazebo第2轮漏填检查地点被拒绝，第3轮模型自行修正；拒绝日志保留。
- 报告：runs/agent-live-mock/20261030T051013Z_a8f8466f6b2a/report.md；runs/agent-live-gazebo/20261030T051051Z_4d47bce12619/report.md；汇总log/verification/agent-loop-summary.json。
- 完整回归138 passed；新增10个行为测试。构建与便捷脚本语法通过。
- 清理：HTTP不复制第二套实现；便捷脚本加载密钥提取为共用函数，新增 ./robopilot search bedroom living_room；删除已废弃humanoid字节码缓存。保留有效静态模式、评测、失败证据，不为减少文件数删有用功能。
- 更新README、docs/agent-loop.md。未添加两个新物品或语义识别，先验证现有感知的反馈循环；后续再扩展目标与自然语言契约。

### 2026-10-30：冗余代码与历史产物清理

- 静态扫描业务模块未发现未使用导入，未为减少文件数删除有效代码；删除 home_materials 中已失效的 oak_board 材质分支及无使用者的橡木纹理生成，移除测试中的未使用导入。
- 删除早期 smoke/mock/v02/v03、旧校准、旧导航和重复评测产物；删除旧 colcon 日志、多轮 pytest XML、Python 与 pytest 缓存。精确清单见 log/verification/cleanup-summary.json。
- 保留当前三个命令输出库 home-agent-search/home-llm-demo/my-home-demo，以及最新 agent-live-gazebo、home-stability、两份最终规划基线。保留源码测试、示例与配置、运行中的仿真、密钥及安装目录。
- 修复22处指向已删除运行文件的 Markdown 链接，历史开发路径加说明，不将删除后不可查看的文件继续作为现存证据。
- 构建与138项回归通过，1条既有DDS警告；清理未停止当前用户仿真。没有在工作区之外进行系统包卸载或删除。

### 2026-10-30：工具箱语义视觉首版

- 核实官方deepseek-flash支持图像输入，复用原HTTP/密钥/配置；新增 toolbox_vision.py，无Torch/Transformers或SDK依赖。
- image_problem抽取共用质量检查；toolbox使用严格JSON视觉结果，至少两类外形特征且含handle/latch；view_clear=false强制unknown。模型声称的特征非独立标注，不提供伪置信概率或精确物体坐标。
- schemas、执行器、工具循环支持显式target=toolbox；自动观测持久化、按target查询记忆、报告标注方法/模型。默认red_marker行为保留；task自然语言静态入口未擅自放开工具箱能力。
- 新增 ./robopilot search-toolbox bedroom living_room，复用现有search分支及密钥加载；launch增加toolbox_state四态，默认布置不变。删除了图像质量重复代码；修正cli模块主入口定义顺序。
- 自建独立域71导航到客厅，采集在位/移除/普通红箱/遮挡四张Gazebo图片并真实请求VLM。初版遮挡被误判not_detected；保留initial结果，增加独立view_clear字段后原四图复核为detected/not_detected/not_detected/unknown。该数据用于调提示词，不作为独立集准确率。
- 完整Gazebo搜索6轮SUCCEEDED，卧室unknown→客厅detected→返回本次实际起点；不能把卧室unknown改写为阴性检查成功。报告runs/toolbox-agent/20261030T100328Z_918abb85f9f4/report.md。
- 图片/首版失败/修正结果与汇总在runs/toolbox-validation；规划5782tokens、视觉1095tokens，四图复核2212tokens，均为服务上报。
- 本轮只上传Gazebo相机图像，未上传个人文件/桌面截图；API异常无颜色兜底。不支持其他未经验证视觉模型。
- 构建通过、154项回归通过，1条既有DDS警告；新增16项视觉/协议/故障/变体/目标存储测试。README、docs/toolbox-vision.md同步，下一步独立视角与不同箱类混淆评测。

### 2026-10-31：中断续作、边界补齐与新视角校准

- 先审计已有实现与报告：VLM、四态场景、target隔离与真实工具循环已在上次保留，不重复造模块。复核官方Vision文档确认既有图像调用格式。
- 补齐inspect_toolbox直接调用时配置缺失/未验证提供方的unknown处理；拒绝无效或耗尽预算，编码时间计入总预算，避免编码后仍发超时请求。新增7项预算/配置测试。
- 新观察姿态(-2.35,1.35,0.22)实测在位漏检not_detected、普通红箱unknown；目视发现箱体在图像下缘严重裁切。失败保留runs/toolbox-recheck-20261031，不计作通过。
- 仅将服务机器人相机俯角0.35→0.55弧度，URDF/SDF同步，旧TurtleBot不变；新增相机外参一致性回归。视觉提示词v2不变。
- 独立域72/73初次复核、74/75修正后采图，自动关闭自建仿真，未上传个人文件或桌面截图。修正后结果见runs/toolbox-recheck-aimed-20261031；属于校准样本，不作为独立准确率。
- 构建通过，最新完整回归162 passed；README、工具箱与家居指南同步，旧完整任务记录未冒充新相机配置验收。

- 相机修正后新图：present=detected；distractor=unknown（未误报，但不满足事先not_detected预期）。未将unknown重标为通过；对照report.md与原始summary完整保留。当前仍需独立集验证不确定性与阴性边界。

2026-10-31 最终新相机闭环：SUCCEEDED，卧室unknown→客厅detected→返航→finish，共6轮。报告 runs/toolbox-final-20261031/20261031T030619Z_ef49cdd83ecc/report.md。规划5724 tokens、视觉1099 tokens，均为服务上报；unknown不作阴性成功。

### 2026-10-31：背包挂墙、门关闭、厨房果盘

- 新增集中目标表 targets.py，三类完整命题与可见证据约束；扩展现有toolbox_vision请求，不新增SDK或独立客户端。参数/协议/图像质量与预算规则复用。
- schemas、执行器、Agent target、目标隔离记忆、报告支持新类别；新命题须在专用观察点执行，不让模型凭图片猜厨房。静态自然语言入口显式拒绝尚未支持的背包/果盘指令，避免静默省略。
- 场景新增低墙钩背包与挂墙/落地/移除/遮挡状态、真实外墙开口上的门扇与关闭/打开/半开状态、厨房低台果盘与有水果/空盘/移除状态。是静态布景变体，不实现自动开关门或物体操作。
- 新增household_inspection.json、10条预期的household_cases.json和 ./robopilot household，复用固定执行链路；条件满足结果与执行状态分开展示。
- 首轮实测背包unknown、门和果盘detected，返航阶段主动取消，CANCELED保留；调整背包点和门点后再做实际导航。
- 真值位姿取图仅作视觉校准，7张样本6张符合预期（开门近图unknown失败、后移图not_detected）；四种变体尚无真实样本，未将空image计为完成。正反例原图与结果保留runs/household-samples。
- 文档 docs/household-inspection.md、README同步；当前完整任务与最终回归状态见后续追加，不将中间结果冒充全部通过。

- 调整后独立域78完整巡检SUCCEEDED：backpack_hanging、door_closed、fruit_bowl均detected，返航成功。报告runs/household-inspection/20261031T055130Z_cc3afcc8f34d/report.md。不是全部10种变体验收。
- 构建通过，最终183 passed、1条既有DDS警告；新增21个命题证据、状态反例、场景、地点和报告语义测试。所有自建域76/77/78场景停止，不停止用户其他世界。

### 2026-10-31：任务清单与用户自选入口

- 新增 task_catalog.py，列出5项支持的固定地点检查；中文完整句式或编号组合映射为现有结构化计划，按输入顺序执行并加返航。不调用LLM做目录解析，不宣称任意自然语言理解。
- 新增 ./robopilot tasks 与 ./robopilot check；CLI支持 --instruction/--preview。预览展示完整条件，输入y/是才构造后端；取消、EOF、未知任务均不发送机器人目标。
- 不支持的片段、否定、条件分支、重复选择或未支持位置整条拒绝，不收集关键词后忽略其余内容。果盘任务完整要求含水果，预览明确说明。
- 复用配置加载函数与MissionExecutor，无新执行框架；清单和预览无API调用，实际语义检查仍上传图像。中文三项预览与编号5的mock执行成功，本轮未启动实际仿真或付费服务。
- 新增15个解析/拒绝/预览与取消安全测试；文档 docs/user-inspection.md 与README同步，最终结果见追加。

- 最终完整回归198 passed，本轮无警告；构建通过，便捷脚本bash语法通过。没有对用户当前运行的仿真发送任何目标。

### 2026-10-31：用户编号2的PARTIAL排查与修复

- 读取原报告：去程SUCCEEDED，视觉not_detected（模型误判）但检查执行SUCCEEDED，返航NAV2_0_STATUS_6 FAILED。原bt_navigator日志定位compute_path_to_pose目标确认超时，随后follow_path halt失败并中止。关键日志已复制到验证目录。
- 核对Nav2 Jazzy官方文档，默认内部确认等待20ms。启动临时参数改为server_timeout=2000ms、wait_for_service=5000ms、bt_loop=20ms，其余沿用；未扩大任务总预算或修改系统安装。
- 改善背包袋体/前袋曲面、肩带与拉链，保持几何状态与原视觉证据约束，不强制返回detected。
- 独立域79连续3轮相同check编号2全部执行/返航SUCCEEDED，无同类确认超时。识别detected/not_detected/detected，仍有1次在位误判；任务成功不等于识别正确，视觉问题未完全解决。原失败及新3份报告均保留。
- 补充PARTIAL控制台输出具体步骤与错误码，并增加相应测试；运行参数文件已核对2000ms（ros2 param发现节点失败未据此冒充成功查询）。
- README和家居指南同步；下一步针对背包真实外观与独立图像集继续处理，不能宣称通用可靠识别。

- 最终完整回归199 passed（本轮无警告）；独立复测仿真已停止。

### 2026-10-31：修正厨房外门附近墙角缺口

- 用户截图中的厨房横隔墙右端为x=-0.2，玄关竖墙左边为x=0.22，存在0.42m意外缺口；延长横墙至竖墙厚度内，保持厨房正式入口宽度不变。
- 南侧外墙与左右门框原有2.5cm/6.5cm小缝同步补齐，保留外门实际门洞，不把门洞填死。
- 场景碰撞与占据地图同源更新；新增回归检查墙角像素占据、正式厨房入口空闲及门框交接。
- README与家居指南同步；需重启世界应用，未对当前用户仿真强制重置。

- 本轮构建通过，完整回归200 passed，无警告；墙角碰撞与地图回归通过，实际GUI效果待重启复核。

### 2026-10-31：三指标实验设计与完成

- 新增 scripts/measure_household.py，固定P/N/N/P/P/N顺序，各场景三次，每轮重启世界。通过现有check目录2,3,4执行，不创建另一套任务框架；预注册protocol含代码散列、人工预期、计时边界、返航阈值。
- 端到端成功要求三次导航、三个判断符合场景真值、返航成功且AMCL位置/朝向误差≤0.35m/0.35rad，unknown/漏检/识别错/启动失败都不计成功。并非程序SUCCEEDED比例。
- 六轮结果：trial01成功93.728s；trial02启动失败、任务未提交；trial03成功95.546s；trial04成功88.288s；trial05程序成功但背包误判89.352s；trial06开门unknown、PARTIAL90.902s。严格成功3/6=50%。
- 原计划18次检查，启动失败未发生3次；实际15张图片由助手逐图复核为可判读（非盲评），正确明确13/15=86.7%。背包4/5、门4/5、果盘5/5；unknown未剔除或当作阴性成功。
- 任务时间为提交命令到进程退出的perf_counter墙上时间，含客户端准备、API、保存与返航，不含仿真启动/人工确认等待；5次已提交含失败样本均值91.5632s、中位90.902s、范围88.288–95.546s。成功子集3次另列均值92.5207s。
- trial02 Gazebo报无法找到/加载世界文件，保留90s就绪超时；疑似准备时序但根因未定，实验期间未改动业务代码/提示词或重跑替换失败。冻结散列复核一致，独立域80–85无残留。
- 原始任务/15张图片/日志/可判读标签/汇总与诊断在 runs/metrics-20261031；视觉服务6831 tokens，不涉及个人文档或桌面图。
- 新增5个严格评分测试，完整回归在实测结束后运行，205 passed；docs/metrics-experiment.md、README同步。小样本同地图重复实验，不代表独立泛化或GUI性能，下一步依据此次失败修复启动和观测可靠性。

### 2026-10-31：记忆有效性与离线配对消融

- 已做：新增确定性assess_memory；配置摘要、目标/后端/检查点隔离、TTL、未来/无效时间、后续否定/unknown、证据引用及本次任务来源检查。旧历史保留，last_seen语义不变。
- 已做：接入静态规划上下文、Agent记忆工具、现场发现门控、固定任务及Agent观测报告；先保存新观测再从数据库判定，保留原有强制现场巡检。
- 已做：新增14场景三策略离线配对实验；宽松最后肯定复用6/14正确、错误复用8、复查2；判别器14/14、错误0、复查12；原有强制复查14/14、错误0、复查14。复查用理想真值，不是Gazebo/VLM端到端成绩，也不是原生产准确率提高。
- 实验产物：runs/memory-validity-20261031/results.json、report.md；设计复现及局限见docs/memory-validity.md。README同步更新。
- 准备做：真实场景变化后的LLM误用记忆与导航/VLM配对耗时实验；当前只测离线策略耗时，禁止用此实验声称机器人总耗时优化或真实风险降低比例。
- 最终验证：完整回归210 passed（18.91s）；ROS包colcon构建通过。新增5个测试覆盖14项边界案例、数据库更新语义及消融评分。未调用真实API或启动仿真。

### 2026-10-31：整理 GitHub 项目首页

- 已做：重写 README 为功能、设计、安装运行、实验与计划四部分，移除个人绝对路径、过时版本状态与重复开发流水。
- 已做：核对便捷脚本、依赖声明、密钥加载方式、210项最新回归记录及记忆有效性实验，区分静态规划、交互清单和工具反馈循环。
- 已做：公开首页只链接仓库内实验说明，明确 runs 原始产物默认忽略，保留失败数据口径及非盲小样本局限；说明当前未提供开源许可证。
- 验证：本轮仅文档改动，检查本地链接与命令入口，不重跑导航或付费模型实验。
- 准备做：按既有计划修复启动可靠性、扩充视觉独立样本及真实记忆配对实验；发布演示素材与许可证由后续发布安排确定。

### 2026-10-31：展示型 README

- 已做：首页改为演示、能力亮点、运行入口与实测结果四部分，减少实现细节，保留功能边界和失败口径。
- 已做：完整安装说明迁移至 docs/quickstart.md；为 GIF 留出注释位置，未虚构尚未提供的附件地址。
- 验证：仅文档调整，检查 README 与快速开始的本地链接，不重新运行仿真或模型。
- 准备做：用户上传 GIF 后填入演示位置，继续既有稳定性与感知改进计划。
