<!-- 用途：记录家居巡检重复运行、关闭异常缓解及 GUI 性能边界。 -->
# 家居运行稳定性

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

更新时间：2026-10-30。

本轮不改变家具、巡检点和感知算法，使用酒店服务机器人与家居地图，验证固定客厅→检查→卧室→检查→起点任务。重复任务共用同一仿真，起点由每次任务实际定位捕获，不重新重置机器人。

## 改动

- 根目录 robopilot 脚本与 ROS 包同名，ROS launch 会把现有文件误当作启动文件。便捷入口改为使用绝对 launch 文件路径，避免根目录运行时的 malformed launch argument 错误。
- 生成地图和贴图不再在 OnShutdown（子进程仍运行）时删除，而在启动解释器退出后清理。强制 SIGKILL 无法保证清理。
- Nav2 默认 use_composition:=False，使用独立进程以降低原共享组件容器并发关闭风险。可显式启用 True 比较，但不能据此宣称已证明原 SIGSEGV 的底层根因。

## 推荐操作

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
./robopilot sim-lite
# 等待 ready=true；另开项目终端执行
./robopilot inspect
```

sim-lite 仍显示 Gazebo，省略 RViz；不要同一 ROS 域同时开启两套 Nav2。仅全新世界自动设置出生位姿；运行中的机器人不要重复初始化。停止时在启动终端 Ctrl+C，等待退出后再启动。

如需原始命令，使用明确文件路径：

```bash
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 launch "$PWD/install/robopilot/share/robopilot/launch/simulation.launch.py" scene:=home robot_body:=service headless:=False use_rviz:=False initialize_home:=True
```

## GUI 边界

本机 glxinfo 显示 llvmpipe、Accelerated: no，实际为 CPU 软件渲染。无 GUI 的巡检成功不能证明 Gazebo+RViz 的 GUI 流畅；关闭 RViz可减少一个渲染客户端。当前未更改虚拟机硬件配置，也不把换机器人外观视为卡顿修复。

验证记录存于 log/verification/home-stability-*.log/json；根目录便捷脚本仅在 task/plan 时加载密钥，本轮固定计划不调用外部模型。

## 实测结果

- 独立 ROS 域 66、同一世界连续 3 轮固定巡检，3/3 SUCCEEDED；耗时 53.871、49.902、52.867 秒，均为客厅 detected、卧室 not_detected，各轮返航成功。
- 正常 SIGINT 后 launch 退出 0，各 Nav2 独立进程正常退出；本次日志未出现原 Magick/SIGSEGV，临时资源目录退出后不存在。两项改动同时应用，不足以证明哪项是原故障根因，也不代表所有关闭条件都已覆盖。
- 124 项自动测试通过，保留 1 条 DDS 清理警告；构建及便捷入口参数解析通过。
- 固定任务不调用 LLM，不包含新起点/障碍变化、真机、语义工具箱识别或感知准确率评测。

任务报告：

- [20261030T032213Z_c39ca98e4462](../runs/home-stability/20261030T032213Z_c39ca98e4462/report.md)

- [20261030T032307Z_0b8568b7e51a](../runs/home-stability/20261030T032307Z_0b8568b7e51a/report.md)

- [20261030T032357Z_4647d4a99569](../runs/home-stability/20261030T032357Z_4647d4a99569/report.md)

## GUI 子进程关闭修正

首轮 GUI 冒烟启动成功创建窗口，但上游 shell/ruby 包装关闭后留下 GUI 子进程，launch 退出 0 并不等于无残留。该失败保留 home-gui-smoke.log/json，残留仅按本次域 67 身份核对后清理。

新增 gazebo_gui.py：自行创建独立进程组，收到关闭信号后对本组逐级发送 SIGINT/SIGTERM/SIGKILL，在有限期限内等待并清理；不扫描或终止其他世界。上游仅负责 server，本入口独立管理 GUI，仍共享本次 GZ_PARTITION。

修正后独立域 68 GUI 启动 15 秒存活、doctor ready=true；关闭 launch 退出 0，进程检查无本次 Gazebo/包装残留，日志未出现原清理崩溃。记录 home-gui-managed.log/json。窗口创建、进程存活和短时关闭不代表 GUI 帧率或交互响应已测量。

新增两个进程故障注入用例，检查自然退出码及忽略 INT/TERM 后的有界清理。最终完整回归 **126 passed**，本次最终运行无警告；此前 124 项运行出现 1 条 DDS 警告，保留历史口径。

## 修正 ready=true 但没有窗口

用户复现后确认：自管 GUI 条件被上游共享 headless=True 覆盖，导致 GUI 启动动作被跳过。本轮改为使用进入上游之前捕获的用户值，新增 True/False 两个回归用例。此前 managed GUI 的存活检查不足以证明窗口创建，不能据此声称实际显示通过。本轮补充独立域窗口存在检查，见 gui-condition-fixed.log/json。

更新后需在原仿真终端 Ctrl+C，等待退出，再执行 ./robopilot sim-lite；无需再次重启虚拟机。ready=true 仍表示导航/相机，不代表 GUI 检查结果。

本轮独立域 69 实测 gui_window_present=true，关闭 launch 退出 0；完整回归 128 passed、1 条 DDS 警告。用户原域仿真未被停止。
