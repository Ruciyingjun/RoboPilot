# 家居场景

当前场景由 `home_scene.py` 生成共享几何与同源占据地图，`home_materials.py` 生成本地纹理，
`mujoco_scene.py` 转换成 MuJoCo MJCF。中间 XML 保留 SDF 风格的几何字段，
不需要安装 Gazebo；这些生成器仍被 MuJoCo 和场景测试使用。

```bash
./robopilot sim
```

默认包含客厅、卧室、厨房和玄关。当前采用简化平面差速底盘，相机位于高位桅杆，
不是旧服务机器人完整外形或 URDF 动力学的等价转换。
生成模型、地图和 Nav2 配置位于 `runs/mujoco-sim/`。
观察点使用 `src/robopilot/config/places.home.yaml`。

另一个服务器终端执行 `./robopilot inspect`，在本地网页观察运动。
启动与 SSH 隧道见 [快速开始](quickstart.md)，桥接细节和验收边界见
[MuJoCo 家居导航](mujoco-navigation.md)。

共享场景生成器仍支持目标状态变化，当前 MuJoCo 启动 CLI 尚未开放这些状态参数。
旧的 `robot_body:=...`、`backpack_state:=...` 等 ROS launch 参数已移除，不能传给新入口。
历史实验和旧外观描述见 [开发进度](../PROGRESS.md)，不作为当前渲染的验收结果。
