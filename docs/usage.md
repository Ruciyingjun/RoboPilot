<!-- 用途：说明 v0.2 的构建、仿真诊断、视觉巡检、中文规划、历史查询、统计与测试步骤。 -->
# RoboPilot v0.2 使用指南

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

新增固定指令规划评测见 [规划评测与复现](planner-benchmark.md)。

项目现状见 [README](../README.md)，验证记录见 [验收结果](acceptance.md)。v0.3 新增 mission 中文任务、地点别名及模型配置，见 [自然语言规划指南](planning.md)。所有终端先进入项目根目录。

## 1. 构建与加载环境

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
source /opt/ros/jazzy/setup.bash
colcon build --packages-select robopilot --symlink-install
source install/local_setup.bash
ros2 run robopilot robopilot --help
```

每打开一个新终端，都需要重新 source 上述两个 setup 文件。已安装依赖包括 Nav2、最小 TB3 仿真、ros_gz_image、cv_bridge、OpenCV、NumPy、YAML。

## 2. 启动 Gazebo 与环境诊断

在虚拟机 Ubuntu 桌面内的终端 1：

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 launch "$PWD/install/robopilot/share/robopilot/launch/simulation.launch.py" robot_body:=turtlebot headless:=False
```

默认在现成世界中加入红色标记，给机器人增加 RGB 相机；不修改 /opt/ros 的文件。可用 `demo_marker:=False` 启动无标记场景。资源紧张时设 `headless:=True use_rviz:=True`，保留 RViz；纯无窗口运行可设 `use_rviz:=False`，但传感器仍需要图形渲染上下文。

在终端 2 加载环境后，对**刚启动、机器人还没移动的默认演示场景**运行：

```bash
ros2 run robopilot robopilot doctor --initialize-demo --timeout 45
```

`--initialize-demo` 明确将定位初始化到默认出生位置 x=-2、y=-0.5、yaw=0。机器人已经移动或使用其他地图时不要使用此选项，改用 RViz 设置正确初始位姿，并运行不带初始化选项的 `doctor`。

预期 JSON 中 clock_advancing=true、scan_samples=360、camera.available=true、ready=true，并输出定位位姿。相机为 320×240，主题为 `/robopilot/camera/image_raw`。

启动仿真后请尽快运行上述初始化，不必等 RViz 所有状态变绿。Nav2 在等待 map→base_link 超时后可能中止导航栈激活；此时再设置位姿也不会自动重新激活整个导航栈。若日志出现 `Failed to bring up all requested nodes. Aborting bringup.`，先关闭并重新启动仿真，再及时执行初始化和诊断。

截图中的「map frame does not exist」曾由 AMCL 缺少初始位姿引起；本次默认场景设置初始位姿后已恢复。若 doctor 未通过，先看它的错误信息及仿真终端日志。

## 3. 执行真实仿真巡检

在终端 2：

```bash
ros2 run robopilot robopilot run \
  --places src/robopilot/config/places.demo.yaml \
  --plan src/robopilot/examples/inspection.json \
  --backend ros --output runs/demo
```

预期：前往 A → 检查红色标记 → 前往 B → 再检查 → 返回本次任务起点。默认场景 A 朝向红色标记，B 朝向另一方向，预期结果分别为 detected、not_detected。

not_detected 表示检查已完成但当前视野没发现目标，因此该检查步骤可以是 SUCCEEDED；unknown 表示无法判断，步骤为 FAILED。

在编辑器中预览终端输出路径中的 report.md，查看真实相机证据；mission.json 保存位姿、时间戳、错误码与耗时。仅观察机器人运动，也可使用 examples/navigation.json。places.demo.yaml 只适用于默认地图，其他地图需重新标定观察位姿和朝向。

按 Ctrl+C 请求取消当前任务。取消未确认时执行器停止发送后续目标。运行任务时不要同时用 RViz 发送其他导航目标。

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

可选环境变化实验：在本次演示世界中移除标记，再执行复查：

```bash
gz service -s /world/default/remove \
  --reqtype gz.msgs.Entity --reptype gz.msgs.Boolean \
  --timeout 5000 --req 'name: "red_marker", type: MODEL'
```

若设置过 GZ_PARTITION，服务命令必须与仿真使用相同值。重新启动仿真会恢复默认标记。

## 6. mock 与故障演示

无需启动 ROS/Gazebo：

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
