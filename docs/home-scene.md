<!-- 用途：说明家居场景第一版的布局、启动方式和验证边界。 -->
# 家居场景预览

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

2026-10-29：第一版为约 10×8 米的无屋顶公寓，客厅、卧室、厨房、玄关通过中央通道相连。使用本地几何模型，不依赖在线模型下载。

客厅有沙发、茶几、电视柜、地毯、盆栽及带提手的工具箱；卧室有床、枕头、衣柜和床头柜；厨房有橱柜、灶台、水槽和冰箱；玄关有鞋柜、地垫和充电底座。均为低复杂度几何布景，尚非照片级模型。门洞固定开放，工具箱是静态布景，充电底座没有充电功能。

## 查看效果

先关闭自己之前启动的 Gazebo/Nav2，避免同一域出现两套机器人。在 Linux 桌面终端执行：

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
source /opt/ros/jazzy/setup.bash
colcon build --packages-select robopilot --symlink-install
source install/local_setup.bash
ros2 launch "$PWD/install/robopilot/share/robopilot/launch/simulation.launch.py" scene:=home headless:=False
```

默认仍是旧场景；家居场景必须显式指定 scene:=home。不要增加 initialize_demo:=True，该参数仅适用于旧地图。

Gazebo 中缩小视野并旋转观察整套公寓。RViz 显示的是配套新地图，不是旧 sandbox。
机器人出生位置为 x=2.7、y=-2.1、yaw=1.5708，位于右下方玄关，朝地图 +Y 方向。
若需尝试导航，在 RViz 用 2D Pose Estimate 在该位置向上拖动初始化，再用 Nav2 Goal 发送目标。首次启动未初始化前的 AMCL/TF 警告是预期现象。

恢复旧场景：

```bash
ros2 launch "$PWD/install/robopilot/share/robopilot/launch/simulation.launch.py" scene:=demo headless:=False initialize_demo:=True
```

## 当前验证与限制

- colcon build 通过；独立 ROS 域 61 的短时启动中地图读取成功、机器人创建成功，验证进程已停止。
- 使用 ROS 系统 Python 的回归为 124 passed。首次误用非 ROS Python 时为 111 passed、1 skipped，随后已补跑完整集。
- 地图是从同源碰撞几何生成的保守占据栅格，不是实测 SLAM 地图。家具完整投影可能比激光截面更保守，后续需导航实测校准。
- places.home.yaml 是候选观察点，尚未逐点导航/相机验证；不能复用 places.demo.yaml、旧 inspection.json 或旧规划 sidecar。
- 新场景尚未完成端到端任务验收，也没有开启工具箱语义识别。现有颜色识别能力不变。
- 后续优先检查门洞通行、观察朝向及相机目标可见性；房间别名和新任务示例待验证后补充。
- 新场景任务使用独立输出目录，例如 runs/home-demo，避免混入旧地图记忆。

实现：src/robopilot/robopilot/home_scene.py；启动入口：src/robopilot/launch/simulation.launch.py；候选点：src/robopilot/config/places.home.yaml。启动时生成临时世界和地图，关闭后清理，不修改 /opt/ros。

## Gazebo 显示机械臂或其他世界

若 RViz 是家居地图、Gazebo 却是其他场景，通常是多个 Gazebo 服务共享 Transport 分区，GUI 或生成服务连接到了另一个世界。启动入口现已为每次启动生成独立 GZ_PARTITION，同时作用于服务器、GUI、桥接与生成进程。

修改后需 Ctrl+C 停止本次 RoboPilot 启动，重新构建并启动；正在运行的进程不会自动使用新设置。无需停止其他项目的 Gazebo。ROS 侧仍应避免同一 ROS_DOMAIN_ID 同时运行两套 Nav2。

## 第二版视觉细化（2026-10-29）

新增交错色阶木地板与拼缝、厨房瓷砖缝、地毯边线、沙发分块坐垫和抱枕、茶几桌腿/书/杯子、圆形植物叶簇、窗框/窗台、床头板/床尾毯/床头灯、衣柜与厨房柜门、灶眼/水槽/水龙头、冰箱把手和工具箱锁扣。窗户为不透明装饰面板，灯为布景，不宣称透光玻璃或真实灯光模拟。

仍采用程序化低复杂度材质与几何，不是照片级场景；本轮没有引入下载资产或高分辨率贴图。新增装饰不参与碰撞，家具原保守碰撞轮廓保持。木地板仅为视觉，地图仍由碰撞几何生成。

构建通过，生成世界含 219 个模型、37 个碰撞体，名称唯一，gz sdf -k 检查 Valid。新增几何的实际 GUI 帧率与视觉效果需重启后检查，不能以 SDF 验证代替渲染验收。查看时建议最大化 Gazebo，并关闭右侧 Entity/Component 面板扩大画面。

更新需在原启动终端 Ctrl+C，然后重新 source install/local_setup.bash 并按上面的 scene:=home 命令启动；正在运行的世界不会热更新。

## 第三版材质与软装（2026-10-29）

在本地生成 256×256 的橡木、胡桃木、布料、地毯、灰泥墙面和石材 PNG，通过 PBR albedo_map 设置材质；金属件与织物采用不同的 metalness/roughness。纹理和世界一起生成在临时目录，关闭后清理，无需下载资源。生成算法固定随机种子，便于复现。

新增圆润抱枕、电视柜抽屉、走廊装饰画、厨房果盘。新增装饰没有碰撞，保留原通行与地图布局。实际看起来仍是程序化家居，不是扫描资产或照片级渲染；窗户仍为装饰面板。

构建及 gz sdf -k 通过，142 处纹理引用指向 6 张存在的纹理。新材质依赖 Gazebo 渲染器的 PBR 支持；实际 GUI 效果与帧率需重启查看。若出现贴图缺失，请保留启动日志，不要在运行期间删除临时 robopilot_sim 目录。

## 修正木地板白缝

截图中的白色短线疑似 z=0 的 Gazebo 网格与原地板表面共面、以及拼板间隙造成。已删除 100 块单独拼板，改为连续地板可视表面，表面上移 4 mm，与网格错开；拼缝由 512×512 木地板纹理中的细棕线表现。地板碰撞高度仍保持原值，厨房、地毯等覆盖层仍在其上方，不改导航地图。纹理总数增至 7 张。

构建、生成结构与 SDF 检查通过；需重启当前世界才能看到修改，实际消除白缝的效果待 GUI 复核。

## 酒店服务机器人与顶部相机

默认 robot_body:=service：约 1.2 米高，圆润底座、立柱机身、胸前屏幕、顶部圆形头部和摄像头，无手臂和双腿。原人形方案已替换。屏幕为静态布景，不是交互 UI；底盘仍为 TurtleBot 差速移动，惯性沿用底盘，上身采用简化碰撞包络，不代表真实整机动力学。

相机相对 base_link 位于 (0.17,0,1.075) 米，俯视约 20 度。保持 /robopilot/camera/image_raw、320×240、2 Hz，固定 TF 与 Gazebo/RViz 一致。旧观察点需重新检查目标可见性。

```bash
ros2 launch "$PWD/install/robopilot/share/robopilot/launch/simulation.launch.py" scene:=home robot_body:=service headless:=False use_rviz:=False
```

先关闭本次旧启动再执行。先仅看 Gazebo 可以减少同时渲染负载；需要 RViz 时改为 use_rviz:=True。原低位相机机器人可选 robot_body:=turtlebot。旧 humanoid 参数已取消。

上次 GUI 无响应尚未确定根因；检查时发现两个额外 Gazebo server 占用 CPU，不能断言换造型就解决渲染问题。没有擅自终止其他项目仿真。


## 家居巡检校准与运行（2026-10-29）

客厅、卧室和本次起点返航已在酒店机器人上完成一次真实 Gazebo 闭环。旧场景门洞尺寸有误，客厅和厨房门洞由约 0.3 米扩大到 1.1 米，地图从修改后的几何同步生成。

在 Linux 桌面终端先停止旧仿真，再构建并启动全新家居世界：

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
source /opt/ros/jazzy/setup.bash
colcon build --packages-select robopilot --symlink-install
source install/local_setup.bash
ros2 launch "$PWD/install/robopilot/share/robopilot/launch/simulation.launch.py" scene:=home robot_body:=service headless:=False initialize_home:=True
```

initialize_home 仅用于全新、未移动的默认家居出生点 (2.7,-2.1,pi/2)，会调用 doctor 检查时钟、雷达、定位与相机。机器人移动后不要重复初始化出生位姿。不要使用 initialize_demo。若 GUI 负载高，先添加 use_rviz:=False。

待终端出现 ready=true，在另一 Linux 终端运行：

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
source /opt/ros/jazzy/setup.bash
source install/local_setup.bash
ros2 run robopilot robopilot run --places src/robopilot/config/places.home.yaml --plan src/robopilot/examples/home_inspection.json --backend ros --output runs/my-home-demo
```

预期顺序：前往客厅→检查红色区域→前往卧室→检查红色区域→返回本次任务起点。一次实测为 SUCCEEDED，客厅 detected、卧室 not_detected；已目视检查客厅证据图确实拍到红色工具箱区域。它不是工具箱类别识别，不保证其他视角或不同布置重复成功。

真实报告：runs/home-calibration-v2/20261029T135516Z_0b55658fb1e8/report.md。第一次校准在导航中被主动停止以扩大门洞，结果 PARTIAL，保留 runs/home-calibration/20261029T135406Z_d5b659493fac/report.md；不能算作两次均成功。

别名配置 aliases.home.yaml 支持客厅/卧室/厨房/玄关。自然语言任务仍只能请求当前支持的红色区域检查；不能要求模型识别工具箱语义或操作家具。

本节校准结果取代本文前面“候选点未测试”的历史状态，具体视角仅适用于当前默认布置。实体地图、输出记忆库和规划 sidecar 不可与旧 demo 混用。

厨房→本次起点返航也已单次 SUCCEEDED：runs/home-kitchen-calibration/20261029T135631Z_c0ea642305c7/report.md。厨房此次只验证导航，不包含视觉检查。完整回归 124 passed，colcon build 通过。校准使用独立域 64（首次主动中止）与 65（修正后成功），均不改变用户默认域。

收尾发现：发送 SIGINT 后 Nav2 组件容器在清理阶段出现 Magick/SIGSEGV（最终退出 -6）；发生在两份任务报告成功完成之后，未遗留本次启动进程。该退出异常根因尚未确认，不能将运行成功等同于退出清理无异常，后续需排查。日志 log/verification/home-service-calibration2.log。

## 永久快捷入口（2026-10-30）

项目根目录新增可执行脚本 robopilot，按脚本位置定位项目，无需每个终端手动 source ROS、工作区与密钥。不修改 ~/.bashrc，不把密钥全局导出。脚本持久保存在项目中；进程环境本身仍是每次启动按需加载。

```bash
cd /home/ruciyingjun/Desktop/enbodied_agent
./robopilot sim
```

等待 ready=true，在另一个项目终端执行：

```bash
./robopilot task '先去卧室检查红色标记，再去客厅检查红色标记，最后返回起点。'
```

其他入口：`./robopilot sim-lite` 不开 RViz；`./robopilot inspect` 固定 JSON 巡检；`./robopilot plan '指令'` 只生成计划；`./robopilot doctor` 只诊断、不重置定位；`./robopilot build` 构建。所有入口可追加原 CLI 参数。sim 默认初始化家居出生点，只用于启动新的世界，不要同时启动第二套 Nav2。

task/plan 自动加载根目录 robopilot.local.env，沿用本机配置优先并清除通用密钥覆盖的规则；不要把密钥写进快捷脚本。task 输出 runs/home-llm-demo；inspect 输出 runs/my-home-demo，两者默认记忆库分开。plan 读取 home-llm-demo 历史，并将预览写入 runs/home-llm-preview。预览和实际 task 是两次独立模型请求。

2026-10-30 用户实跑记录确认 LLM 计划为卧室→检查→客厅→检查→返回，状态 SUCCEEDED：runs/home-llm-demo/20261030T021627Z_22fe93054485/report.md。原固定任务先客厅后卧室，因此整段路线顺序不同。局部绕行具体原因没有轨迹对比证据，不能归因于 LLM 直接选路。

## 2026-10-30 稳定性更新

便捷入口现使用明确 launch 文件路径，避免根目录同名 robopilot 文件干扰；默认独立 Nav2 进程、延后临时资源清理，GUI 使用独立受控进程组。固定家居巡检同一世界连续 3/3 成功；短时 GUI 关闭无残留。完整证据与限制见 [稳定性记录](stability.md)。这些结果不包含长期 GUI 流畅性或工具箱语义识别。

## 工具箱语义检查更新

toolbox_state:=present/absent/distractor/occluded 可切换工具箱、移除、红色普通箱和遮挡板。重新启动世界后运行 ./robopilot search-toolbox living_room。工具箱VLM已接入，早期“工具箱仅布景”的说明属于历史状态；方法、图像上传与小样本局限见 docs/toolbox-vision.md。

## 2026-10-31 相机观察校准

酒店机器人头部相机高度仍为1.075米，俯角现为0.55弧度（约31.5度），取代前文约20度参数，SDF/URDF固定TF保持一致。原因是新观察位置下工具箱在旧视角中过度裁切导致漏检。需要关闭并重新启动世界生效；TurtleBot低位相机保持不变。复核见 docs/toolbox-vision.md，不能复用旧报告声称新视角已完成全部任务验收。

## 厨房墙角闭合修正（2026-10-31）

厨房横隔墙与玄关竖墙原有约42cm非设计缺口，已将墙端延伸至竖墙内；外门门框两侧细缝也已封闭。正式厨房入口与外门门洞保留，碰撞和地图同步生成。运行中世界不会热更新，请先Ctrl+C再 ./robopilot sim-lite。
