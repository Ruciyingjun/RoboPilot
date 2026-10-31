<!-- 用途：说明 v0.3 中文任务、模型配置、工具调用、记忆上下文及规划审计的验证方法。 -->
# v0.3 自然语言规划指南

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

DeepSeek 用户先看 [专用配置与验证指南](deepseek.md)。

规则规划器可离线使用；真实 DeepSeek 的 JSON 和 create_plan 工具调用已在小范围任务中实测。两种来源都会经过同一任务校验器。

## 1. 中文指令直接执行

先构建并加载：

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
source /opt/ros/jazzy/setup.bash
colcon build --packages-select robopilot --symlink-install
source install/local_setup.bash
```

无需启动仿真即可体验完整 mock 链路：

```bash
ros2 run robopilot robopilot mission \
  --places src/robopilot/config/places.demo.yaml \
  --aliases src/robopilot/config/aliases.demo.yaml \
  --instruction '先去A点检查红色标记，再去B点检查红色标记，最后返回起点' \
  --planner rules --backend mock --mock-images red,empty \
  --output runs/language-demo
```

aliases.demo.yaml 将 A点/检查点A 映射到 checkpoint_a，B点/检查点B 映射到 checkpoint_b。这些只是地图标签，不代表自动理解房间。

mission 会先生成并严格校验计划、写规划审计，然后才创建执行后端。规则不支持的动作、地点或模型错误不会自动放行。

## 2. 在 Gazebo 中执行

终端 1（Ubuntu 虚拟机桌面，加载环境后）：

```bash
ros2 launch "$PWD/install/robopilot/share/robopilot/launch/simulation.launch.py" robot_body:=turtlebot headless:=False initialize_demo:=True
```

新选项 initialize_demo=True 显式对默认新场景初始化定位并运行 doctor，避免等人工操作时 Nav2 启动超时。只用于刚启动且出生位置没有改变的默认演示；其他地图或已移动的机器人不要使用它。默认仍为 False。

等待启动日志输出 ready=true。终端 2 加载环境后运行：

```bash
ros2 run robopilot robopilot mission \
  --places src/robopilot/config/places.demo.yaml \
  --aliases src/robopilot/config/aliases.demo.yaml \
  --instruction '先去A点检查红色标记，再去B点检查红色标记，最后返回起点' \
  --planner rules --backend ros --output runs/language-ros
```

同一 output 目录就是此入口的记忆库。任务成功后再执行：

```bash
ros2 run robopilot robopilot mission \
  --places src/robopilot/config/places.demo.yaml \
  --aliases src/robopilot/config/aliases.demo.yaml \
  --instruction '去上次发现红色标记的地方检查红色标记；返回起点' \
  --planner rules --backend ros --output runs/language-ros
```

规则模式使用固定语法；没有对应后端的历史发现时明确拒绝，不会猜地点。

## 3. 配置真正的 LLM

先选择提供聊天补全兼容接口的服务，确认完整 HTTPS 端点、模型 ID 和密钥。模板没有可用账号或密钥：

```bash
cp src/robopilot/config/llm.env.example robopilot.local.env
```

在本机编辑 robopilot.local.env，将三个值替换为实际配置。该文件名已加入忽略规则。然后在要调用模型的终端中加载：

```bash
set -a
source robopilot.local.env
set +a
```

先仅规划、不移动机器人：

```bash
ros2 run robopilot robopilot plan \
  --places src/robopilot/config/places.demo.yaml \
  --aliases src/robopilot/config/aliases.demo.yaml \
  --instruction '先到A点看看红色标记，再检查B点，完成后回到起点' \
  --planner llm --llm-format json \
  --memory runs/language-ros --backend ros --output runs/llm-plan.json
```

检查生成的 steps 顺序和动作是否符合原意，再执行：

```bash
ros2 run robopilot robopilot run \
  --places src/robopilot/config/places.demo.yaml \
  --plan runs/llm-plan.json --backend ros --output runs/language-ros
```

若服务支持工具调用，将规划命令改为 --llm-format tools。模型只能提交一个 create_plan 调用；工具调用的参数仍需通过严格校验，模型本身不能调用 ROS。

默认最多修复一次不合法计划（最多两次模型请求），可设置 --repair-attempts 0 禁用。HTTP 错误、超时、截断响应、拒绝或错误工具名直接失败，不降级成规则成功。通用服务单次超时 30 秒，DeepSeek 默认 120 秒，响应上限 1 MiB。

模板的 example.invalid 只是占位地址，不是服务。配置不存在时命令返回 2，不创建导航后端。真实模型结果见 live-deepseek.md；不能把离线测试当作模型泛化能力结果。

## 4. 模型知道哪些事实

请求中包含：已知地点 ID、别名、支持目标、指定后端的最近一次发现和最多 10 条近期观测摘要。

上下文仅包含观测 ID、地点、目标、结果和时间；不发送图像文件、数据库路径或密钥。近期未检测到与历史发现同时保留，提示模型历史不能证明当前仍存在。新计划仍需通过地点、动作、参数和依赖校验。

上下文跟随 output/memory 数据库与 backend 选择。切换地图应使用新库；当前尚未实现通用跨地图物体关联。

## 5. 如何追溯计划

plan 命令生成两个文件：

- plan.json：可执行的规范化任务。
- plan.planning.json：原始指令、规划器、模型名（如有）、记忆上下文、每次输出校验结果、耗时及计划/地点摘要。

mission 会保存到 output/plans/ 下；执行后的 mission.json 中保留 planning，report.md 展示任务来源。服务端点、请求鉴权头和密钥不会自动写入审计。

run 检查同名审计文件；若计划步骤或地点配置自规划后变动、审计为 REJECTED，将拒绝执行。摘要是文件一致性检查，不是身份认证或防篡改签名。没有 sidecar 的旧 JSON 仍可按手写计划使用，报告标记 json_file。

规划失败会记录 REJECTED 审计，没有机器人任务运行结果。对同一文件重新规划失败后，旧计划仍被拒绝执行，需重新生成合法计划。

## 6. 已有与待补验证

已通过：别名解析、mock 中文任务和历史复查、JSON/工具协议测试、一次修复上限、非法地点拒绝、缺少配置不创建后端、敏感错误脱敏、计划/地点变更拒绝。

已完成真实 DeepSeek 小范围调用与 Gazebo 执行，记录样本 token 用量和耗时。仍待补：更多指令理解正确性、其他服务商兼容性、开放式指令及多场景评测。自动校验只能确认协议和可执行边界，不能完全判断模型是否理解了用户意图。

## v0.4 拒绝与能力检查

请求前保守拦截已知不支持能力和显式未知检查点。模型返回 {"refusal":"原因"} 时记录 MODEL_REFUSAL，不再尝试修复成合法子任务；工具思考模式使用 auto 而非指定函数。

这针对真实测试中模型静默省略开门动作的问题，不能替代任意自然语言的完整语义验证。复杂指令仍应先 plan 并核对步骤，再 run。证据见 [真实模型验收](live-deepseek.md)。
