<!-- 用途：说明固定规划评测集、完整性约束、指标口径、真实模型结果及代表性 Gazebo 验证。 -->
# v0.5 固定指令评测与完整性检查

> 清理说明（2026-10-30）：早期运行产物和测试日志已清理；历史路径不保证仍存在。最新保留范围见项目 PROGRESS 与清理清单。

日期：2026-10-29。规划评测不执行机器人；真实服务为用户配置的 DeepSeek deepseek-flash，JSON 模式，思考 enabled/high。

## 1. 评测集与人工预期

[planner_benchmark.json](../src/robopilot/examples/planner_benchmark.json) 包含 26 条人工标注：16 条支持任务、10 条应拒绝/澄清任务。

- 支持任务：单地点、双地点、反向顺序、仅导航、仅返航、不返航、分句检查、再次访问、历史 A/B 地点、历史发现后的未检测到、禁止某地点、明确不返航。
- 拒绝/澄清：未知 C 点、门操作、工具箱语义、抓取、条件分支、直到发现的循环、含糊地点、缺失记忆、矛盾要求及混合否定。
- 历史为代码构造的 none/seen_a/seen_b/seen_a_then_missing 夹具。不会读取真实观测库、图片或个人文件，也不会把夹具写入机器人记忆。
- 人工预期是独立写入的动作、地点、目标列表，不由意图提取代码生成。比较时忽略步骤 ID 与重试设置，但不忽略动作、顺序或目标。

这是公开的有限语法回归集，不是独立隐藏测试集或通用机器人语言基准。

## 2. 新的完整性边界

intent.py 对有限中文表达提取地点、检查、返航、简单否定与历史地点约束。模型会收到这些约束，然后系统比较最终动作序列：漏检查、漏地点、顺序错误、多余步骤、进入禁止地点或违背不返航要求都不能放行。

模型首次候选会保留在审计 attempts 中，分别标记 protocol_valid 和 intent_valid；最多一次修复。明确模型 refusal 仍直接结束。条件、循环、歧义、冲突和无法识别的独立片段要求澄清。

约束并非任意自然语言的完整语义理解，嵌套句式、复杂否定、条件和未覆盖的改写仍需扩展。JSON 手写 run 仍按结构校验；新自然语言检查适用于新生成的 plan/mission，旧计划应重新生成才包含这些记录。

## 3. 本机真实结果（单次运行）

| 指标 | 当前规则路径 | DeepSeek + 同一应用管线 |
|---|---:|---:|
| 全部案例通过 | 17/26（65.4%） | 26/26（100%） |
| 16 条支持任务完整 | 7/16（43.8%） | 16/16（100%） |
| 10 条拒绝/澄清符合预期 | 10/10 | 10/10 |
| 实际尝试模型请求 | 0 | 16 |
| 模型明确拒绝 | 0 | 0 |
| 应用前置拒绝 | 10 | 10 |
| 首轮模型计划 schema 通过 | 不适用 | 16/16 |
| 首轮模型计划符合人工动作预期 | 不适用 | 16/16 |

**10 条拒绝全部来自应用前检，不是模型判断能力。模型已得到提取后的约束，26/26 是受约束系统管线在固定小样本上的结果，不是裸模型成功率或泛化结论。**

规则路径只识别固定句式，9 个失败主要是改写、否定及不同历史表述无法解析。它们完整保留为 plan_validation 错误，没有丢弃、当作正确拒绝或改标注。该对比反映当前两条实现路径的覆盖差异，不是公平的通用模型能力比较。

DeepSeek 16 个模型案例平均规划墙上时间 2.299 秒，中位 2.202 秒，最大 3.498 秒；服务报告 prompt_tokens=11945、completion_tokens=4759、total_tokens=16704。耗时是包含应用处理和可能修复的单案例总时间；本次没有修复。没有估算货币成本。

原始本机结果：

- [规则报告](../runs/planner-benchmark-rules-final/20261029T060124Z_a0fde3ff/report.md) / [完整 JSON](../runs/planner-benchmark-rules-final/20261029T060124Z_a0fde3ff/summary.json)。
- [DeepSeek 报告](../runs/planner-benchmark-deepseek/20261029T055346Z_48c129c4/report.md) / [完整 JSON](../runs/planner-benchmark-deepseek/20261029T055346Z_48c129c4/summary.json)。
- cases/ 保存每条指令的预期、首次候选、每次校验、token 用量；接受案例另外保存可执行计划和审计。

## 4. 代表性 Gazebo 执行

| 任务 | 实际结果 | 本机证据 |
|---|---|---|
| 首次反向任务启动 | 准备阶段超时，没有发送导航目标，全部 SKIPPED；保留失败 | 失败报告（旧运行产物已清理） |
| 不要去 B，只检查 A 后返航 | 仅导航 A、检查 A（detected）、返航，SUCCEEDED | 报告（旧运行产物已清理） |
| 反向 B→A 巡检重试 | B not_detected、A detected、返航，SUCCEEDED | 报告（旧运行产物已清理） |

两条代表计划最终通过，但总计 3 次执行尝试，不能写成 2/2 首次成功。首次准备失败的根因未独立确认，不能归因于模型。就绪查询另补单次 1 秒重试，保留整体等待期限，并输出具体未就绪环节；延迟响应故障注入测试已通过，但不据此声称解决所有启动超时。

仅选取无历史夹具的两条计划执行，未把合成历史伪装成真实空间记忆。[环境诊断](../log/verification/benchmark-doctor.json)、[仿真日志](../log/verification/benchmark-simulation.log)。本轮独立 ROS 域 44，结束后关闭仿真。

## 5. 如何重复运行

构建并 source 安装环境后，先运行无需模型的基线：

```bash
ros2 run robopilot robopilot benchmark-plan \
  --places src/robopilot/config/places.demo.yaml \
  --aliases src/robopilot/config/aliases.demo.yaml \
  --cases src/robopilot/examples/planner_benchmark.json \
  --planner rules --output runs/planner-benchmark-rules
```

在同一终端加载本机模型配置后运行真实模型：

```bash
unset ROBOPILOT_LLM_API_KEY
set -a
source robopilot.local.env
set +a
ros2 run robopilot robopilot benchmark-plan \
  --places src/robopilot/config/places.demo.yaml \
  --aliases src/robopilot/config/aliases.demo.yaml \
  --cases src/robopilot/examples/planner_benchmark.json \
  --planner llm --llm-format json --output runs/planner-benchmark-deepseek
```

可重复 --case simple_a --case forbid_b 选择样本，用 --repeats 2 重复运行；默认 1 次，最多 5 次。模型调用量随重复次数增加。命令永不自动创建 ROS 后端或移动机器人。

每次运行新建唯一目录，逐条保存 summary.json、report.md 与 cases/。Ctrl+C 返回 130 并保留已完成样本，不自动恢复；重新运行会生成新目录。技术错误会中止剩余样本并报告覆盖率，不能算正确拒绝；单个模型计划格式错误记录失败后继续其余样本。

全部案例符合人工预期时退出 0，存在未通过案例或技术中止时退出 1，数据集或配置输入错误退出 2。规则基线退出 1 是此次 9 个未通过案例的正常结果。

## 6. 软件回归与后续

当前 124 项自动测试通过；有 1 条 DDS 响应清理警告。此前一次回归曾出现就绪准备超时，随后补充有界生命周期重试与故障注入；仍需后续长期稳定性验证。

[最终测试 XML](../log/verification/pytest-benchmark-final.xml)。这些测试数与 26 条真实规划样本数不同，也不能当作机器人成功率。

下一步扩大独立指令集及扰动重复评测，再升级视觉语义识别。当前相机仍是红色区域检测。
