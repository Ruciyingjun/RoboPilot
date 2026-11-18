# 安装与运行

当前使用 Ubuntu 24.04 x86_64 无头服务器、ROS 2 Jazzy、Nav2、MuJoCo 4.0.1。
依赖安装在项目 Docker 镜像内，不向宿主机安装 ROS 或仿真组件。

## 准备容器

服务器项目目录执行（已有镜像可跳过）：

```bash
./robopilot build
```

安装细节与离线镜像导入见 [容器环境](container.md)。模型客户端使用标准库 HTTP，无需 OpenAI SDK。

## 启动与实时画面

服务器终端 1：

```bash
cd ~/workspace/RoboPilot
./robopilot sim
```

等待 `"ready": true`。新世界自动初始化定位；机器人移动后不要重复初始化。
Mac 本地终端保持 SSH 隧道运行：

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18081:127.0.0.1:18081 b309
```

浏览器打开 `http://localhost:18081`，无需点击 Run。若 SSH 配置中的 RemoteForward 冲突，
使用 [桥接说明](mujoco-bridge.md) 中已验证的临时配置方法。
`./robopilot sim-lite` 关闭网页查看器，保留仿真、相机与导航。

服务器终端 2：

```bash
./robopilot doctor
./robopilot inspect
```

快捷任务命令进入同一运行中的容器。路线为客厅→红色检查→卧室→红色检查→返航，
不需要 API 密钥。不要同时运行多个任务或手动速度发布器。Ctrl+C 取消当前任务；
仿真终端 Ctrl+C 停止整套栈。完整底层命令见 [MuJoCo 家居导航](mujoco-navigation.md)。

## 模型配置与可选任务

已有配置无需覆盖。首次配置：

```bash
cp src/robopilot/config/deepseek.env.example robopilot.local.env
chmod 600 robopilot.local.env
```

用编辑器填写 `DEEPSEEK_API_KEY`，快捷命令按需加载；文件已被 Git 忽略。
不要将密钥写入源码或提交记录。模型调用产生 API 用量，语义视觉会上传仿真相机图片。

```bash
./robopilot tasks
./robopilot check --instruction '2,3,4' --preview
./robopilot check
./robopilot search bedroom living_room
./robopilot task '先去卧室检查红色标记，再去客厅检查红色标记，最后返回起点。'
```

云端背包、门、果盘和工具箱检查在 MuJoCo 渲染下尚未重新验收，不沿用历史识别成绩。

## 报告与测试

报告在项目 `runs/` 下，包含 `report.md`、`mission.json` 和相机证据。
仿真已停止时，可独立运行容器测试（无需重建镜像）：

```bash
bash scripts/container.sh run python -m pytest -q
```

无需 ROS 或仿真也可以运行 mock 示例：

```bash
PYTHONPATH=src/robopilot .venv/bin/python -m robopilot run \
  --places src/robopilot/config/places.demo.yaml \
  --plan src/robopilot/examples/inspection.json \
  --backend mock --mock-images red,empty
```

`places.demo.yaml` 是旧离线示例坐标，不能用于当前 MuJoCo 家居导航。
小型 MuJoCo 场景使用 `places.mujoco-demo.yaml`，详见导航指南。

带 checkpoint 恢复和模型工具循环的新入口见 [Agent Runtime](agent-runtime.md)。
视觉 Prompt 的案例收集、改进、门禁与版本切换见 [RSI 指南](rsi.md)。
