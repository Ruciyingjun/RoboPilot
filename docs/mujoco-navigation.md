# MuJoCo 家居导航与巡检

环境使用既有的用户专用 ROS Jazzy / Nav2 / MuJoCo Docker 镜像，无需重新构建。
源文件通过项目目录挂载。宿主机不需要安装 ROS、Nav2 或 Gazebo。

## 启动

先在旧 `bridge --web` 所在终端按 Ctrl+C，停止旧仿真。不要同时控制同一机器人。
在服务器项目目录执行：

```bash
bash scripts/container.sh sim
```

默认启动家居世界、ROS 桥接、地图服务器、AMCL、Nav2 控制器、规划器、行为树、
速度平滑与碰撞监控，以及实时 Web Viewer。等待终端诊断输出 `"ready": true`。
地图、MJCF、Nav2 参数生成到 `runs/mujoco-sim/`，随容器重启重新生成；
AMCL 初始位姿只用于新世界，不应在机器人移动后重新初始化。

Web Viewer 的连接保持不变：Mac 将本地 18081 经 SSH 转发到服务器 18081，
浏览器打开 `http://localhost:18081`。详见 [桥接说明](mujoco-bridge.md)。
网页只是现场查看，ROS 负责物理步进和运动控制，无需点击 Run。

## 运行巡检

另开服务器终端，在同一运行中的容器内执行：

```bash
cd ~/workspace/RoboPilot
bash scripts/container.sh exec python -m robopilot run \
  --places src/robopilot/config/places.home.yaml \
  --plan src/robopilot/examples/home_inspection.json \
  --backend ros --startup-timeout 60 \
  --output runs/mujoco-home-missions
```

路线为客厅→拍照检查红色区域→卧室→拍照检查→返回任务开始位姿。
不调用云端 API。房间内没有红色目标时 `not_detected` 是有效检查，不能描述为发现目标。
任务执行成功与检查对象是否存在分别记录；报告和证据保存在项目 `runs/`。
终端 Ctrl+C 会通过既有执行器取消导航。

需要确认当前状态时：

```bash
bash scripts/container.sh exec python -m robopilot doctor --timeout 30
```

运行中的导航栈会发布速度指令，不应同时运行手动 `/cmd_vel` 发布器。
同一个执行器使用 `--planner llm` 的 mission 和 agent 入口仍可使用；需先在
`container.sh exec` 进入的 shell 中加载本机模型配置，且调用会产生 API 用量。
云端语义视觉在新渲染下尚未验收，不能沿用 Gazebo 的识别成绩。

## 场景和定位来源

`mujoco_scene.py` 调用原 `home_scene.build_home`，从同一组墙体、家具与目标几何
生成 MJCF，并复用原同源占据地图。支持现有箱体、球、圆柱、椭球和本地生成纹理。
碰撞几何与纯视觉几何分开；视觉细节不改变原碰撞轮廓。
机器人采用简化平面差速动力学，保留原观察点和服务机器人相机的高度、俯角、视场角。
它不是原机器人完整 URDF 的动力学等价转换，也没有模拟传感器噪声或真实轮式里程计误差。

桥接仅发布仿真真值 odom→base_link，AMCL 根据激光和地图发布 map→odom。
Nav2 的速度链为 controller/behavior→cmd_vel_nav→velocity_smoother→cmd_vel_smoothed
→collision_monitor→cmd_vel→MuJoCo 轮子执行器。保留碰撞监控，不直接改坐标到点。
这仍是同地图仿真验收，不代表真机能力。

## 小场景与回归

停止家居仿真后，可以用最小场景定位问题：

```bash
bash scripts/container.sh sim --scene demo
```

小场景必须使用对应地图的任务点：

```bash
bash scripts/container.sh exec python -m robopilot run \
  --places src/robopilot/config/places.mujoco-demo.yaml \
  --plan src/robopilot/examples/inspection.mujoco-demo.json \
  --backend ros --output runs/mujoco-demo-missions
```

生成几何、地图和桥接单元/集成测试：

```bash
bash scripts/container.sh run python -m pytest -q
```

上面测试不执行完整 Nav2 路线；真实到点与返航由启动后的 ROS 任务验收。
