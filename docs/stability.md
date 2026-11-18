# 仿真启动与排查

当前仅使用 MuJoCo、AMCL 和 Nav2；旧 Gazebo GUI 管理和启动逻辑已移除。

- `./robopilot sim` 启动世界和导航栈，等待 `"ready": true`。
- `./robopilot doctor` 检查当前时钟、激光、定位与相机，不重置机器人。
- 网页运行在服务器回环地址 18081，需要本地 SSH 转发。
- 同一账号只运行一个 `robopilot-bridge-<UID>` 容器；停止自己的旧启动后再启动。
- 任务命令通过 `container.sh exec` 进入同一容器，避免 ROS 域与网络不一致。
- Nav2 使用仿真时钟；网页仅查看，不控制仿真步进。

若网页无法连接，先检查仿真终端是否仍在运行和 SSH 隧道是否成功。
若 SSH 报 7890 RemoteForward 冲突，按 [桥接说明](mujoco-bridge.md) 使用临时配置；
不要终止其他人的转发或修改共享服务。

容器限制 4 CPU、6 GiB 内存；OSMesa 相机由 CPU 离屏渲染。通过 `sim-lite` 可关闭网页，
传感器和导航继续运行。历史 GUI 帧率不适用于当前方案。
