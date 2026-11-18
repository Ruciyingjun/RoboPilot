# 无头服务器的 ROS 2 / Nav2 / MuJoCo 环境

使用 Ubuntu 24.04 / ROS 2 Jazzy 基础镜像；apt 与 pip 安装均发生在镜像内。
宿主机无需安装 ROS、Nav2 或 Gazebo。镜像保存在 Docker 的共享存储中，并非个人目录；
只有项目源码、配置在本项目目录。构建会占用共享磁盘与网络。

```bash
bash scripts/container.sh build
bash scripts/container.sh shell
```

容器使用与当前账号相同的 UID/GID 写入项目，不使用特权模式或宿主机网络。
运行限制为 4 CPU、6 GiB 内存，ROS 仅在容器本地通信。
退出后删除容器，项目文件保留；容器内临时安装不会保存，应修改 Dockerfile 后重新构建。
不加载宿主机的 `.venv`、`install/setup.bash` 或 ROS 配置。

检查环境和执行测试：

```bash
bash scripts/container.sh run python -c 'import rclpy, mujoco, cv2; from nav2_msgs.action import NavigateToPose; print(mujoco.__version__)'
bash scripts/container.sh run python -m pytest -q
```

模型配置按需在容器 shell 中加载（文件不会复制进镜像）：

```bash
unset ROBOPILOT_LLM_API_KEY
set -a
source robopilot.local.env
set +a
```

查看项目目录中的 MJCF 模型：

```bash
bash scripts/container.sh viewer /workspace/RoboPilot/path/to/model.xml
```

在本地电脑建立 SSH 隧道，将本地 18081 转发到服务器 18081，然后用浏览器打开
`http://localhost:18081`。如 SSH 配置包含冲突的 RemoteForward，沿用已验证的临时配置方法。
18081 只绑定服务器回环地址。退出查看器会自动删除容器及端口映射。

项目已移除旧 Gazebo 启动链，默认使用 MuJoCo。
速度指令、传感器、TF、时钟桥接已提供，见 [桥接说明](mujoco-bridge.md)。
AMCL/Nav2 启动及巡检操作见 [MuJoCo 家居导航](mujoco-navigation.md)。

如 Docker Hub 无法访问，可尝试官方镜像的公共分发地址：

```bash
ROS_BASE_IMAGE=public.ecr.aws/docker/library/ros:jazzy-ros-base bash scripts/container.sh build
```

如果服务器不能访问镜像仓库，可在能联网的 Linux x86_64 Docker 环境中构建相同
UID/GID 的完整镜像，再使用 `docker save` 导出、传输到服务器并 `docker load` 导入。
只导入基础镜像仍需访问 apt 和 pip 源，导入完整镜像才能避免服务器上的安装下载。
