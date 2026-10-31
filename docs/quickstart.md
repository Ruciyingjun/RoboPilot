<!-- 用途：提供 RoboPilot 的环境安装、密钥配置、仿真运行和测试步骤。 -->
# 安装与运行


### 环境准备

已验证环境：Ubuntu 24.04 ARM64 虚拟机、ROS 2 Jazzy、Gazebo Harmonic，4 核 CPU、约 6 GiB 内存，使用 llvmpipe 软件渲染。相机配置为 320×240、2 Hz，以控制虚拟机负载。尚未对其他系统组合完成验证。

先安装与 Ubuntu 24.04 匹配的 ROS 2 Jazzy，并确保 `/opt/ros/jazzy/setup.bash` 存在。以下命令在 **Linux 虚拟机内**执行；macOS 宿主机不直接运行该 ROS 工作区。

```bash
# 安装构建工具与依赖管理器（已安装可跳过）
sudo apt update
sudo apt install python3-colcon-common-extensions python3-rosdep python3-pytest

# 将 GitHub 仓库克隆到本机，然后进入包含本 README 的项目根目录。
source /opt/ros/jazzy/setup.bash

# 首次使用 rosdep 时执行一次；已经初始化则跳过 init。
sudo rosdep init
rosdep update
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy

./robopilot build
```

依赖由 ROS 包的 `package.xml` 声明，包括 Nav2、最小 TurtleBot3 仿真、图像桥接、OpenCV、NumPy 和 YAML。模型客户端使用 Python 标准库 HTTP 接口，无需安装 OpenAI SDK。

### 第一步：启动仿真

终端 1，在项目根目录运行：

```bash
./robopilot sim-lite
```

该命令启动家居世界、Gazebo 窗口和导航栈，初始化新世界的机器人定位；省略 RViz 以减小负载。需要 RViz 时使用 `./robopilot sim`。等待启动诊断输出 `ready: true`。

终端 2，同样进入项目根目录：

```bash
./robopilot doctor
./robopilot inspect
```

`inspect` 执行客厅→卧室→返回起点的本地红色标记巡检，**不需要 API 密钥**，也不会启动仿真。两个终端的 ROS 域配置应保持一致。

启动新世界前关闭旧仿真；机器人移动后不要重复初始化出生位姿。同一机器人只运行一个任务执行器，执行期间不要在 RViz 同时发送导航目标。

### 第二步：配置 DeepSeek

在项目根目录创建本机配置：

```bash
cp src/robopilot/config/deepseek.env.example robopilot.local.env
chmod 600 robopilot.local.env
```

用编辑器打开 `robopilot.local.env`，保留模板中的模型配置，并增加：

```bash
DEEPSEEK_API_KEY='填写你的密钥'
```

便捷命令会按需自动加载该文件。`*.local.env` 已被 Git 忽略；不要将真实密钥写入源码、公开模板或提交记录。直接使用底层 Python / ROS CLI 时，需要自行导出环境变量，详见 [模型配置](deepseek.md)。

语义检查会向配置的模型服务上传当前仿真相机图像，并产生 API 用量；本地红色检测不上传图片。

### 第三步：选择检查或体验 Agent

保持仿真运行，在另一个项目终端执行：

```bash
# 查看可执行任务，不调用模型
./robopilot tasks

# 预览三个家居检查，不移动机器人或调用模型
./robopilot check --instruction '2,3,4' --preview

# 交互选择编号或中文要求，确认后执行
./robopilot check

# LLM 接收工具结果，按顺序搜索红色标记并返航
./robopilot search bedroom living_room

# 使用视觉模型搜索工具箱
./robopilot search-toolbox bedroom living_room

# 另一条独立入口：自然语言生成静态计划后执行
./robopilot task '先去卧室检查红色标记，再去客厅检查红色标记，最后返回起点。'
```

### 查看结果与运行测试

任务结束后，终端会打印本次 `report.md` 的路径。打开该文件查看检查结论、相机图片、错误信息与返航记录；同目录的 `mission.json` 保存结构化明细。运行结果位于 `runs/`，默认不随源码上传 GitHub。

无需 Gazebo，可使用合成图像验证执行与报告流程：

```bash
PYTHONPATH=src/robopilot python3 -m robopilot run \
  --places src/robopilot/config/places.demo.yaml \
  --plan src/robopilot/examples/inspection.json \
  --backend mock --mock-images red,empty
```

Mock 结果不代表真实导航或视觉识别效果。运行完整测试：

```bash
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
python3 -m pytest -q
```

更多命令见 `./robopilot help`。启动与定位排查见 [家居场景指南](home-scene.md)，交互任务定义见 [自选检查指南](user-inspection.md)。

