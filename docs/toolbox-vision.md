<!-- 用途：说明工具箱VLM类别识别、云端图像处理、运行方法与有限验收结果。 -->
# 工具箱语义检查

更新时间：2026-10-31。续作补齐配置/预算边界，并修正低处目标的相机观察俯角。

当前同时支持两种目标：red_marker 使用本地 OpenCV 颜色区域检测；toolbox 使用云端 VLM 判断工具箱类别。二者分别存储观测，不会因为画面里有红色就判定工具箱存在。

## 模型与数据

本版复用已配置的 deepseek-flash；官方接口已支持用户消息中的图像输入，见 [DeepSeek Vision](https://api-docs.deepseek.com/guides/vision/)。没有安装 Torch/Transformers 或第二套 SDK，继续复用项目 HTTP 客户端。

显式选择 toolbox 会将本次相机图像发送到本机密钥所配置的 DeepSeek 服务，产生 API 用量；red_marker 不上传图像。开发验收只发送了 Gazebo 图像，没有上传桌面截图或个人文件。原始 base64、密钥与模型内部推理不会写入任务日志。

图像先做尺寸、编码和过暗检查；最长边最多1024像素，PNG不超过2 MiB。VLM返回 view_clear、status、reason、visual_cues：画面受阻强制 unknown；detected 需至少两类可见特征，其中包含提手或锁扣。特征由模型报告，不是独立标注，也不是校准概率。没有精确检测框、对象身份追踪、深度定位或房间全域缺失推断。

API/协议失败、缺少配置、过暗或证据不足均为 unknown，不回退颜色检测。首版只启用已核实的 deepseek-flash；其他服务需额外验证。

## 运行

先停止旧仿真，在项目根目录的 Linux 桌面终端启动：

```bash
./robopilot sim-lite
```

等 ready=true，另一个项目终端：

```bash
./robopilot search-toolbox bedroom living_room
```

命令会自动加载 robopilot.local.env。搜索契约是按顺序尝试，发现工具箱后停止搜索并返回本次实际起点。不是任意自然语言工具循环；task 入口仍只开放原静态规划能力，不宣称其已理解工具箱任务。

等价 agent 参数为：

```bash
ros2 run robopilot robopilot agent \
  --places src/robopilot/config/places.home.yaml \
  --search-places bedroom living_room --target toolbox \
  --backend ros --output runs/home-agent-search
```

手动命令需要自行 source ROS、工作区和密钥配置。该示例不会自动启动仿真。

报告标注 target、method、模型、模型声称的视觉特征、时间与机器人位姿；图像证据与每轮工具反馈保留。记忆位姿指机器人拍摄位置，不是工具箱精确世界坐标。

## 场景变化

每次只启动一个世界；停止旧世界再切换：

```bash
./robopilot sim-lite toolbox_state:=present
# 或 toolbox_state:=absent / distractor / occluded
```

- present：带提手与箱盖的工具箱。
- absent：移走工具箱及其部件。
- distractor：相同位置的普通红箱，没有提手/盖子/锁扣。
- occluded：工具箱前增加遮挡板，阻挡默认观察位置。

可以使用 search-toolbox living_room 单点检查。not_detected 仍是一次有效检查；unknown 是未确认，若始终没有发现且有未确认地点，任务为 PARTIAL。找到目标并成功返航时任务可成功，即使此前另一个地点未确认。报告保留每一步，不掩盖 unknown。

## 本轮验收

| 固定Gazebo图片 | 初版 | 增加视野判断后 |
|---|---|---|
| 工具箱在位 | detected | detected |
| 工具箱移除 | not_detected | not_detected |
| 普通红箱 | unknown | not_detected |
| 遮挡 | not_detected（失败） | unknown |

**这是同4张图上调整提示词后的复核，不是独立测试集准确率。** 保留初版失败与当前结果：runs/toolbox-validation/report.md、summary.json、各场景图片和 *.initial.result.json。

另做真实 DeepSeek+Nav2+VLM+记忆+返航任务：6轮工具调用，卧室 unknown→客厅 detected→返回本次实际起点→finish，SUCCEEDED。卧室视野被床/前景遮挡，未获得可靠阴性结论。原始报告：runs/toolbox-agent/20261030T100328Z_918abb85f9f4/report.md。

规划服务报告5782 tokens，视觉服务报告1095 tokens；四张修正后图片合计2212 tokens，单次视觉调用约1秒，仅为本轮观测，不是延迟保证。总体仍需独立视角、多物体、不同颜色、工具箱与手提箱/收纳盒的混淆评测。当前简单几何模型不等于真实家居泛化。

完整回归154项通过，1条既有DDS清理警告；新增16项视觉、故障、场景与目标存储测试。未增加新的Agent框架或地图平台。

## 2026-10-31 中断后续作

已确认上次的VLM、四态场景、存储与工具循环代码及完整任务报告均保留，本轮没有重建另一套框架。

补齐边界：缺少密钥配置或未验证的提供方直接返回unknown；预算为零、负数、NaN/无穷时不编码、不请求；图像编码消耗计入总预算，编码后预算耗尽不上传。新增相应回归测试。

首次从新观察姿态 (-2.35,1.35,0.22) 采图：在位工具箱误判not_detected，普通红箱返回unknown。目视发现约20度俯角导致箱体裁切，不能把这两例说成识别通过。原图与失败结果完整保留在 runs/toolbox-recheck-20261031。

将酒店机器人相机俯角由0.35改为0.55弧度（约31.5度），相机位置不变，SDF与URDF固定TF同步；原TurtleBot低位相机不变。修正后重新启动世界采图，提示词v2保持不变。该轮使用失败反馈调整了观察配置，因此属于观察校准，不是独立测试集准确率。结果见 runs/toolbox-recheck-aimed-20261031/summary.json。

旧报告仍是旧相机配置的记录；重启仿真才会采用新外参。未实现主动云台、多视角融合、目标身份追踪或自动识别其他类别。

本次修正后的新图结果：在位detected，普通红箱unknown。后一例未误报，但未达到事先设定的not_detected预期，不能报告“两个案例全部通过”。仍存在类别缺失与不确定性的边界问题；不做规则强制阴性、不把unknown算作正确缺失。前后对照见 runs/toolbox-recheck-aimed-20261031/report.md。

最新完整回归162 passed，包括新增8个配置/预算/相机外参用例。

2026-10-31 最终新相机闭环：SUCCEEDED，卧室unknown→客厅detected→返航→finish，共6轮。报告 runs/toolbox-final-20261031/20261031T030619Z_ef49cdd83ecc/report.md。规划5724 tokens、视觉1099 tokens，均为服务上报；unknown不作阴性成功。
