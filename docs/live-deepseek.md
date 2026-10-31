<!-- 用途：记录真实 DeepSeek 规划、拒绝边界、已发现问题及 Gazebo 闭环的可核对证据。 -->
# v0.4 真实 DeepSeek 验收

日期：2026-10-28。服务：用户配置的 DeepSeek，模型 deepseek-flash、thinking=enabled、reasoning_effort=high。首次实际调用包含的上下文已核对：仅默认仿真检查点、别名和红色标记观测摘要，没有图片或个人文档。密钥未写入报告。

## 正常任务

| 样本 | 模型结果 | Gazebo 结果 |
|---|---|---|
| 「先到A点看看红色标记是否还在，然后到B点也检查一下，最后返回起点」 | JSON，一轮通过；3.564 秒，1466 tokens | A detected、B not_detected、返航成功；报告（旧运行产物已清理） |
| 「去上次发现红色标记的地方重新检查，再返回起点」 | 工具调用，一轮通过；1.884 秒，1750 tokens；依据历史选择 checkpoint_a | A detected、返航成功；报告（旧运行产物已清理） |

原始可执行计划与审计：JSON 计划（旧运行产物已清理）、JSON 审计（旧运行产物已清理）、工具计划（旧运行产物已清理）、工具审计（旧运行产物已清理）。

以上耗时仅为模型规划墙上时间，tokens 来自服务 usage，不含机器人执行。任务数很少，不是泛化成功率统计。

## 异常任务与修正

| 观察 | 处理与证据 |
|---|---|
| 思考工具模式首次 HTTP 400 | 官方 API 不支持在思考模式中强制指定工具，改为 auto 后成功；初次错误审计（旧运行产物已清理） |
| 未知 C 点 | 初始模型输出 error/refusal，最终被校验器拒绝；原流程多调用了一次修复；[原始负例记录](../log/verification/deepseek-negative-probes.json) |
| 「去A点打开门」 | 模型省略开门，仅生成导航和返回。该计划没有执行，人工验收后将审计改为 REJECTED；[修复前证据](../log/verification/deepseek-silent-omission-before-fix.json) |
| 增加前置能力检查 | 门操作、工具箱语义、抓取、未知探索及显式未知检查点在调用前拒绝；两个验收例的 API 次数为 0；[记录](../log/verification/deepseek-capability-guard.json) |
| 明确模型拒绝不修复 | 「去不存在的会议室…」真实模型一轮拒绝，1.174 秒、1037 tokens；审计（旧运行产物已清理） |

应用层拒绝与模型拒绝分别记录。保守能力规则只覆盖已知模式，并不能判断所有改写、否定或条件指令；复杂任务仍须核对计划是否完整。

## 工程验证与限制

92 项自动测试通过，覆盖请求兼容性、明确拒绝不修复、能力预检不触发 API、模型上下文与原有执行行为。[测试 XML](../build/robopilot/pytest.xml)。

[本轮汇总](../log/verification/deepseek-live-summary.json)、[仿真日志](../log/verification/deepseek-simulation.log)。本轮使用独立 ROS 域 43 和 Gazebo partition，不改变默认域；验收结束关闭本次仿真。

仍未实现工具箱语义检测/VLM、门操作、跨地图语义建图、真机和大规模泛化实验。相机仍用红色区域检测，不读取场景真值作识别结论。

复现入口见 [DeepSeek 配置与验证](deepseek.md)，先 plan 并检查，再启动默认新场景并 run。
