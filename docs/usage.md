<!-- 用途：说明 v0.2 的构建、仿真诊断、视觉巡检、中文规划、历史查询、统计与测试步骤。 -->
# RoboPilot v0.2 使用指南

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

新增固定指令规划评测见 [规划评测与复现](planner-benchmark.md)。

项目现状见 [README](../README.md)，验证记录见 [验收结果](acceptance.md)。v0.3 新增 mission 中文任务、地点别名及模型配置，见 [自然语言规划指南](planning.md)。所有终端先进入项目根目录。

## 1. 当前环境与导航

安装、启动、SSH 实时画面及巡检见 [快速开始](quickstart.md)。
使用 `./robopilot sim` 启动 MuJoCo，在另一终端执行 `./robopilot inspect`。
底层 CLI 在运行中的容器内通过 `bash scripts/container.sh exec python -m robopilot ...` 调用。
本页其余 `ros2 run robopilot robopilot ...` 等价于容器内 `python -m robopilot ...`。
`places.demo.yaml` 为离线示例；家居实机式仿真使用 `places.home.yaml`，小场景用
`places.mujoco-demo.yaml`。不要在不匹配的地图执行旧示例导航坐标。

检查结果 `not_detected` 表示检查完成但未发现对象，`unknown` 表示无法判断。
报告、结构化记录和相机证据位于 `runs/`。任务期间不要发送其他导航目标或速度指令。

## 4. 中文指令生成计划

无需模型服务的规则模式，支持以下受限句式和已配置地点 ID：

```bash
ros2 run robopilot robopilot plan \
  --places src/robopilot/config/places.demo.yaml \
  --instruction '先去checkpoint_a检查红色标记，再去checkpoint_b检查红色标记，最后返回起点' \
  --output runs/instruction.json
```

plan 只生成并校验计划，不移动机器人。查看 JSON 后，用 run 的 --plan 指向该文件即可执行。支持「去<地点>」「去<地点>检查红色标记」「返回起点」，用逗号或分号分隔；不支持的动作和地点不会被猜测。

可选 LLM 模式：在本地设置 `ROBOPILOT_LLM_ENDPOINT`（完整 HTTPS 聊天补全端点）、`ROBOPILOT_LLM_MODEL`、`ROBOPILOT_LLM_API_KEY`，再在 plan 命令添加 `--planner llm`。接口使用 messages/model 请求和 choices[0].message.content 响应，要求模型返回纯 JSON，最终仍由同一校验器检查。外部服务尚未实测，规则模式不依赖该服务。

## 5. 查询记忆并复查

先运行一次真实巡检，确保 runs/demo 内有 detected 观测，然后：

```bash
ros2 run robopilot robopilot memory --memory runs/demo --backend ros

ros2 run robopilot robopilot plan \
  --places src/robopilot/config/places.demo.yaml \
  --instruction '去上次发现红色标记的地方检查红色标记；返回起点' \
  --memory runs/demo --backend ros --output runs/recheck.json

ros2 run robopilot robopilot run \
  --places src/robopilot/config/places.demo.yaml \
  --plan runs/recheck.json --backend ros --output runs/demo
```

mock 与 ROS 观测分开查询。not_detected/unknown 会追加历史，不会删除旧的 detected。历史发现仅决定复查地点，当前结论来自新的图像。更换地图时使用新的 --output/--memory 目录。

## 6. mock 与故障演示

无需启动 ROS/MuJoCo：

```bash
PYTHONPATH=src/robopilot python3 -m robopilot run \
  --places src/robopilot/config/places.demo.yaml \
  --plan src/robopilot/examples/inspection.json \
  --backend mock --mock-images red,empty --output runs/mock-demo
```

mock 图像为合成数据，不是机器人证据。--mock-images 按检查次数依次消耗，支持 red/empty/dark/missing，用尽后默认 red。导航故障用 --mock-outcomes succeeded/failed/timeout/unsafe，以逗号分隔，按导航尝试消耗，用尽后成功。

真实导航超时注入使用 examples/timeout.json：它故意给导航设置 0.1 秒期限，以验证取消确认后继续返航；成功表现是任务 PARTIAL、第一步 TIMED_OUT、返航 SUCCEEDED，退出码 1。

## 7. 输出与统计

每次任务保存在 --output/<任务ID>/ 下：

- mission.json：任务、地点快照、步骤、观测与执行细节。
- report.md：可阅读报告，明确区分 mock/ROS，巡检时嵌入图像。
- evidence/*.png：当前相机图像及检测框。
- --output/robopilot.sqlite3：任务、步骤和追加式 observations。

```bash
ros2 run robopilot robopilot evaluate --memory runs/demo --backend ros
```

evaluate 只读数据库，统计任务与导航步骤完成率、平均任务耗时和检查结果分布。它没有人工真值，不能给出视觉准确率；少量相关复查任务的完成率不能代表泛化能力。

退出码：0 成功；1 失败或部分完成；2 输入/规划无效；130 取消。不支持进程被强制终止后的自动续跑，恢复前需核对机器人状态。

## 8. 自动测试

```bash
python3 -m pytest -q -m 'not ros'
source /opt/ros/jazzy/setup.bash
python3 -m pytest -q
colcon test --packages-select robopilot --return-code-on-test-failure
colcon test-result --verbose
```

ROS 测试使用独立域 173 的临时服务端，验证 Action、生命周期、TF 与图像新鲜度，不启动 Gazebo。实测记录见 acceptance.md。

项目维护文件开头均注明用途；JSON 使用可选字符串 $comment，XML 声明后使用注释。构建文件、数据库及历史输出保持原生格式。
