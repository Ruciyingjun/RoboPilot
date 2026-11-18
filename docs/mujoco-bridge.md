# MuJoCo 与 ROS 2 桥接

在已构建的 ROS/Nav2 容器中运行，无需重新构建镜像：

```bash
cd ~/workspace/RoboPilot
bash scripts/container.sh bridge
```

需要实时网页时，用以下命令替代上面的启动命令（同一机器人只启动一次）：

```bash
bash scripts/container.sh bridge --web
```

服务器本地 18081 转发到该容器的 8080。Mac 本地执行以下命令，临时去掉
SSH 配置中的其他端口转发以避免共享服务器上的 7890 冲突：

```bash
tunnel_config=$(mktemp /tmp/robopilot-ssh.XXXXXX)
ssh -G b309 | awk '$1 !~ /^(localforward|remoteforward|dynamicforward)$/ {print}' > "$tunnel_config"
ssh -F "$tunnel_config" -S none -N \
  -o ClearAllForwardings=no -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18081:127.0.0.1:18081 b309
```

浏览器打开 `http://localhost:18081`。它同步 ROS 桥接当前的模型和状态，
支持旋转、缩放查看。物理由 ROS 定时器持续推进；无需点击 Run。
网页重置、载入模型、修改状态等请求被忽略，以免倒退 ROS 时钟或绕开控制链路。
移动请使用下面的 `/cmd_vel` 命令。此方式不启动第二份仿真。

默认加载 `src/robopilot/models/bridge_demo.xml`：6×6 米围墙、障碍物、
红色方块和差速轮式机器人。这是独立桥接验收场景；完整家居场景请使用 `./robopilot sim`。
底盘限制在平面上，轮子通过 MuJoCo 速度执行器与地面接触推动底盘。
没有瞬移、导航目标服务或自动到点逻辑。

另开服务器终端，在同一个容器中发指令或检查话题（独立 `run` 容器的网络互相隔离）：

```bash
bash scripts/container.sh exec ros2 topic list
bash scripts/container.sh exec ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.2}, angular: {z: 0.0}}'
```

发指令终端按 Ctrl+C 后，桥接在 0.5 秒墙上时间内将轮子目标速度设为零；
物理模型随后减速。桥接终端 Ctrl+C 停止仿真并移除该容器。
不要同时启动多个控制器向此机器人发送速度指令。

| 话题 | 消息 | 频率 / 约定 |
|---|---|---|
| `/cmd_vel` | geometry_msgs/Twist | linear.x / angular.z；限幅 ±0.5 m/s、±1.5 rad/s |
| `/clock` | rosgraph_msgs/Clock | 50 Hz 仿真时间 |
| `/odom` | nav_msgs/Odometry | 50 Hz，odom → base_link，仿真真值 |
| `/tf` | tf2_msgs/TFMessage | odom → base_link |
| `/tf_static` | tf2_msgs/TFMessage | base_link → laser_frame / robopilot_camera_optical_frame |
| `/scan` | sensor_msgs/LaserScan | 10 Hz，360 束，0.05–8 米 |
| `/robopilot/camera/image_raw` | sensor_msgs/Image | 2 Hz，RGB8，320×240 |
| `/robopilot/camera/camera_info` | sensor_msgs/CameraInfo | 相同图片时间戳，针孔内参 |
| `/joint_states` | sensor_msgs/JointState | 50 Hz，左右轮角度 |

频率按仿真时间计。物理步长 5 ms，每次墙上定时器推进 20 ms 仿真；渲染或 CPU
负载过高时仿真变慢，不追赶墙上时间。所有动态 TF 和传感器使用 `data.time`。
激光通过场景碰撞几何射线获得；机器人 geom 使用 group=1，不参加激光射线查询。
当前扫描在同一时刻采样，`time_increment=0`，未模拟滚动扫描与传感器噪声。

默认接收 Jazzy Nav2 使用的 Twist。需要 TwistStamped 时启动：

```bash
bash scripts/container.sh bridge --stamped
```

模型文件可通过 `--model` 指定，必须保持本示例的关节、执行器、相机命名和尺寸约定；
这不是适配任意 MJCF 机器人的通用硬件插件。`--no-camera` 可禁用渲染以诊断纯物理。
支持 ROS 标准 `--ros-args`，例如 `-r /cmd_vel:=/robot/cmd_vel`。

验证：

```bash
bash scripts/container.sh run python -m pytest -q src/robopilot/tests/test_mujoco_bridge.py
```

桥接节点自身不发布 map → odom，也不提供 NavigateToPose Action。
需要自动巡检时使用 `container.sh sim`，它同时启动 AMCL 和 Nav2，
见 [家居导航与巡检](mujoco-navigation.md)。
独立的 `container.sh viewer` 加载同一 XML 仍会启动另一份仿真；查看桥接机器人
应使用 `container.sh bridge --web`。
