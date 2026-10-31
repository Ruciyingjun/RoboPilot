"""用途：验证 GUI 包装的自然退出码和忽略关闭信号时的有界进程清理。"""

import os
import signal
import subprocess
import sys
import time

import pytest


@pytest.mark.parametrize('stubborn', [False, True])
def test_gui_process_exit_and_escalation(tmp_path, stubborn):
    executable = tmp_path / 'gz'
    marker = tmp_path / 'child.pid'
    executable.write_text(
        '#!/usr/bin/python3\n# 用途：替代 Gazebo 的进程生命周期测试夹具。\n'
        'import os, signal, time\n'
        + ('signal.signal(signal.SIGINT, signal.SIG_IGN)\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n' if stubborn else '')
        + f'open({str(marker)!r}, "w").write(str(os.getpid()))\n'
        + ('time.sleep(30)\n' if stubborn else 'raise SystemExit(7)\n'))
    executable.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH']}
    process = subprocess.Popen([sys.executable, '-m', 'robopilot.gazebo_gui'], env=env)
    child = None
    try:
        deadline = time.monotonic()+5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists()
        child = int(marker.read_text())
        if stubborn:
            process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=6) == (0 if stubborn else 7)
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if child:
            try:
                os.killpg(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
