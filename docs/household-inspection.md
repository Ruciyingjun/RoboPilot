<!-- 用途：说明背包挂墙、门关闭、厨房果盘的目标定义、仿真变体和测评方法。 -->
# 家居多目标检查

新增三类检查，复用原 Nav2、相机、云端视觉、SQLite、报告与工具循环；没有复制三个模型客户端。

| target | 检查要求 | 必须有的视觉证据 | 专用观察点 |
|---|---|---|---|
| backpack_hanging | 背包挂在墙钩上 | 背包、墙钩连接、悬空关系；仅靠近墙不算 | backpack_check |
| door_closed | 指定外门关闭 | 门扇、门框、对齐、没有明显开口；不是“看见门”即可 | door_check |
| fruit_bowl | 厨房果盘中有水果 | 盘/碗、水果、水果在盘内；空盘不算 | fruit_check |

厨房位置来自配置的专用检查点，不让模型凭图片猜房间。首版三类关系目标只允许在各自专用点检查，其他位置返回 unknown。几何背包使用适合低位相机的低墙钩；门是外墙开口上的静态门扇，开闭变体不是门控执行或动态铰链；果盘移到厨房低推车台面以适配固定头部相机。

## 操作

停止旧仿真，在 Linux 桌面项目终端：

```bash
./robopilot sim-lite
```

等待 ready=true，在另一项目终端：

```bash
./robopilot household
```

顺序为背包检查、门关闭检查、厨房果盘检查、返回任务起点。图像会发送至已配置 DeepSeek 服务，产生API用量；自动加载本机密钥，不上传个人文档。

反例场景：

```bash
./robopilot sim-lite backpack_state:=floor door_state:=open fruit_state:=empty
```

每次切换需要关闭原世界再启动，不要同域重复开启两套 Nav2。

| 参数 | 可选值 |
|---|---|
| backpack_state | hanging / floor / absent / occluded |
| door_state | closed / open / ajar |
| fruit_state | present / empty / absent |

原 toolbox_state 保留。新增物品默认存在；没有新增分类器训练、主动抓取、自动开关门或多视角融合。

## 状态语义

- detected / condition_satisfied=true：完整检查条件满足。
- not_detected / false：有效视野中条件不满足，例如开门、空盘或落地背包；不等于物品一定不存在。
- unknown / null：遮挡、裁切、证据不足或服务异常，不能当作正常阴性。

报告分别展示执行状态和条件结果。检查得到明确“不满足”可以是执行成功；因此不能把任务SUCCEEDED理解为所有物品与状态都符合要求。失败与unknown仍保留。

## 定义与样本

目标定义集中在 targets.py，现有 toolbox_vision.py 扩展为共享视觉实现以兼容原调用；静态计划与agent均支持新target，原自然语言task能力边界保持，尚未开放任意新对象指令。

- examples/household_inspection.json：三项固定巡检任务。
- examples/household_cases.json：10条人工预期（正例、落地、移除、遮挡、开门、半开门、空盘）。image=null 表示尚未采集，不能计入测评数量。
- runs/household-samples：已采集真实Gazebo图片、VLM原始结果及预期对照。使用已知仿真位姿直接放置机器人，隔离定位误差，仅验证相机视野和识别，不是导航成功证据。

样本用于场景/视角校准，不作为独立测试集准确率。模型提供的visual_cues不是独立标注；还需要不同背包、不同门型、碗盘和光照的独立验证。

## 本轮实际校准

- 已采集7张真实Gazebo图片（3个正例、3个反例及1个开门后移复核），6张结果符合预期。开门近视角返回unknown，保留原失败；后移后返回not_detected。不能用6/7宣称独立测试集准确率。
- 挂墙背包/关闭的门/装水果的果盘均detected；落地背包/空果盘为not_detected。背包移除、遮挡、半开门和果盘移除4种状态已实现且有几何/规则测试，尚未采集真实VLM样本，cases清单对应image仍为空。
- 初轮真实巡检：背包观察裁切unknown，门/果盘detected，返航阶段由开发者主动取消，整体CANCELED。报告保留 runs/household-inspection/20261031T054323Z_6e6d43a06c69/report.md，不记作全部通过。
- 背包观察点调整为(2.0,2.2,1.79)，门点后移为(1.1,-1.9,-pi/2)；调整后全流程已单次SUCCEEDED：背包/门/果盘均detected并完成返航。报告 runs/household-inspection/20261031T055130Z_cc3afcc8f34d/report.md。校准不等于多场景泛化。

图片与逐项结果：[校准样本](../runs/household-samples/report.md)。

构建通过，最新完整回归183 passed、1条既有DDS清理警告。本轮只发送Gazebo相机图片，未使用个人文件；各独立验证世界已停止，不影响用户其他仿真。

## 背包误判与返航中止修复（2026-10-31）

用户报告 runs/user-inspection/20261031T060806Z_d6c131476563 的PARTIAL来自返航FAILED；背包检查执行成功但模型误判not_detected。原bt_navigator日志确认等待compute_path_to_pose目标确认超时，随后Action被中止，不是“检测阴性阻止返航”。原始关键日志保留log/verification/backpack-original-failure.txt。

默认Nav2参数的内部确认等待为20毫秒，见 [Nav2 Jazzy文档](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/configuring_bt_navigator/)。启动时复制上游配置至本次临时目录，将default_server_timeout设为2000毫秒、wait_for_service_timeout设为5000毫秒、bt_loop_duration设为20毫秒；导航总墙上时间不增加，不修改/opt/ros。

背包模型改为圆润袋体、立体前袋、拉链和肩带轮廓，减少方盒/信箱特征。交互入口在PARTIAL时直接打印未完成步骤、错误码和原因，避免用户只看到总状态。

独立域79相同编号2连续三轮执行与返航均成功，未复现原确认超时；背包识别结果detected/not_detected/detected，即三张在位图有一张仍误判。不能宣称视觉已可靠修复，也不能把任务成功等同于识别正确。报告见runs/backpack-fix，汇总log/verification/backpack-fix-summary.json。

重启全新仿真才应用新参数和模型：./robopilot sim-lite，另一个终端 ./robopilot check 选择2。下一步需独立视觉评测或更真实资产，不靠强制模型返回阳性来掩盖错误。
