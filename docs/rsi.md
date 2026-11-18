# RSI：受控视觉 Prompt 改进闭环

当前实现失败案例→候选 Prompt→基线/候选配对评测→非退化门禁→显式激活→回滚。
面向工具箱、背包挂墙、门关闭、果盘有水果的视觉检查；不修改导航控制器或模型权重。
支持人工候选及模型自动提出补充指导。是否激活由独立代码重算门禁，模型不能自行宣告通过。

## 先运行无需模型的完整演示

在服务器项目目录执行，不必启动仿真：

```bash
./robopilot rsi demo --output runs/rsi-demo-01
```

输出目录必须是新目录。演示使用合成图片和固定响应，验证退化候选被拒绝、有效候选激活、
旧任务快照保持原版本、新任务取得新版本、回滚恢复基线。它不调用 API、不移动机器人，
不证明真实 VLM 质量提高。结果保存在 summary.json 和 registry/evaluations/。
也可在已有 Python 环境运行 `PYTHONPATH=src/robopilot .venv/bin/python -m robopilot rsi ...`。

## 生产版本库与人工案例

```bash
./robopilot rsi --registry runs/rsi init
./robopilot rsi --registry runs/rsi status
```

未激活候选时，使用从原代码抽取的内置 Prompt。版本 ID 包含目标、基线策略摘要、补充指导、
父版本、理由和来源的内容哈希，实际文本另有 SHA256。目标 Schema 和必需证据仍由代码校验。
候选整体替换补充指导，固定基线要求保留；不会直接修改 targets.py。

可以从真实 mission.json 中选取一条观测，由人独立看图给出标签：

```bash
./robopilot rsi --registry runs/rsi collect \
  --mission runs/your-mission/your-id/mission.json \
  --observation OBSERVATION_ID --id backpack_failure_001 \
  --expected detected --split development --group scene_session_001 \
  --reviewer your-name --reason '完整挂钩连接和悬空证据可见，旧结果漏检' \
  --failure-type false_negative
```

`collect` 保留任务、观测、旧结果、旧 Prompt 等来源，复制证据图片；不会从模型结果自动生成真值。
导航失败、网络失败和不可见视角应单独归因，避免将所有失败都归因于 Prompt。
证据图片可能是带注释的导出图片，人工复核时需注意，不把它当作独立无标记测试集。

批量导入使用人工编写的 JSON：

```json
{
  "version": 1,
  "cases": [{
    "id": "toolbox_case_001",
    "target": "toolbox",
    "image": "images/case_001.png",
    "expected": "unknown",
    "split": "gate",
    "group_id": "scene_session_001",
    "critical": true,
    "reviewer": "your-name",
    "reason": "目标观察区域被前景遮挡",
    "failure_type": "occlusion_as_absence"
  }]
}
```

```bash
./robopilot rsi --registry runs/rsi import --manifest path/to/reviewed-cases.json
```

返回不可变 dataset ID。图片路径相对 manifest；图片按内容复制到版本库，并在评测、激活时校验。
同图/同目标不能换 ID 重复计分，已有案例不能原地改标；新修订用新 ID 和独立数据集。
同一图片或同一场景 group 不能跨 development、gate、test。相关视角要由人工归入同一 group，
系统不能自动识别所有近重复图片。
多个 collect 返回的小数据集可通过聚合 manifest 注册为一次完整评测集，已存在的相同案例允许复用。

## 提出候选

人工候选，guidance.txt 只写附加判别指导：

```bash
./robopilot rsi --registry runs/rsi candidate \
  --target toolbox --guidance-file guidance.txt --reason '修复普通箱体混淆'
```

模型候选，只有这一步和 live evaluate 会产生模型用量：

```bash
./robopilot rsi --registry runs/rsi propose \
  --target toolbox --dataset DATASET_ID --max-tokens 4000
```

模型仅获得 development 的标签、失败理由和旧结果摘要，不获得 gate/test 案例或图片。
数据作为不可信内容，不是指令。保留请求准入记录、已报告用量、候选或失败原因。
请求超时/丢失用量不自动重试，也不生成可部署候选。单次调用限制输出，
总 Token 依据服务报告判定，可能超出预算后才拒绝，不能作为精确费用上限。

## 配对评测和门禁

```bash
./robopilot rsi --registry runs/rsi evaluate \
  --candidate PROMPT_ID --dataset DATASET_ID \
  --split gate --repeats 3 --max-requests 200 --max-tokens 50000 --timeout 600
```

live evaluate 上传指定数据集图片至当前配置的视觉服务并产生 API 用量，不发送任意项目文件。
支持现有视觉模型配置；记录模型名、供应商和端点摘要，不记录 API 密钥。
相同案例重复运行基线与候选，交替先后顺序。每次请求前持久化准入，结果逐条落盘，
未知用量、协议错误或服务异常将评测置为 INCOMPLETE，不能通过门禁；unknown 不是技术异常的兜底成功。

默认固定门禁：

- 至少 6 个 gate 案例、3 次重复，覆盖 detected / not_detected / unknown，且含关键遮挡反例。
- 基线/候选配对完整，所有请求用量可核对，没有技术异常。
- 候选在标记的 critical 案例上全部正确；整体和每个标签类别均不退化。
- 候选正确次数严格增加；无改进候选不会激活。
- 总 Token 不超过基线的 1.25 倍，平均时延不超过基线的 1.5 倍加 0.25 秒容差。

这些是工程门槛，不是统计显著性保证。固定图片重复次数不是独立样本量。
报告按 failure_type 输出基线/候选失败比例、下降百分点与相对下降比例；基线失败率为零时，
相对下降比例为空。这是固定图片上的复发统计，不是 MuJoCo 端到端故障复发率。
若基线有不可用服务/未知用量，本轮无有效比较，不能借此声称改进。
`--split development` 供开发诊断，`--split test` 供冻结后的最终验收；均不能直接用于激活。
模型不会获得隐藏标签，但人工反复用 gate 选版本仍可能过拟合，需保留独立最终测试集。

## 激活、版本固定和回滚

```bash
./robopilot rsi --registry runs/rsi activate --evaluation EVAL_ID --reason '门禁通过后启用'
./robopilot rsi --registry runs/rsi rollback --target toolbox --reason '新现场出现退化，恢复上一版本'
```

激活时重新核对评测完整性、当前基线、Prompt 哈希、图片内容与评测代码摘要，并重新计算门禁。
版本切换和激活历史在同一 SQLite 事务提交。若模型配置、基线或评测代码改变，需要重新评测。
production 库拒绝 fixture 评测；sandbox 类型创建后不能改成 production。
这些记录是本地审计，不是防恶意修改 SQLite 的数字签名或权限认证系统。

既有 MissionExecutor 和 SearchAgent 在任务开始时固定所有视觉 Prompt，
任务中激活只影响后续任务；观测与报告保存版本 ID 和文本摘要。
已保存的任务快照可继续传给 VLM，避免活动版本漂移；新 workflow 首版仍只允许 red_marker，
尚未接入云端 VLM 总预算，因此本轮没有放宽该限制。

任务读取默认 `runs/rsi`，使用其他生产库时，在容器内配置，或将该变量写入 robopilot.local.env：

```bash
export ROBOPILOT_RSI_DIR=/workspace/RoboPilot/runs/another-rsi
```

快捷命令的模型/版本库环境可写在被忽略的 robopilot.local.env；容器内路径应使用 /workspace/RoboPilot。
rollback 切回该目标上一条切换记录的来源版本，保留全部历史，不改变运行中任务的快照。

## 代码和验证边界

主要文件：prompt_registry.py、rsi_store.py、rsi_proposer.py、rsi_evaluator.py、rsi_gate.py、rsi_cli.py。
`rsi demo` 是可重复的机制验收；真实视觉改进需独立标注图片和真实模型配对评测。
本轮没有宣称 FRR 下降或端到端成功率提高，也不沿用旧 Gazebo 数据为 MuJoCo 指标。
服务别名不能锁定供应商远端权重；真实长程质量需要持续收集新场景并复核。
