"""用途：管理本次 Gazebo GUI 的独立进程组，正常关闭并有界清理残留子进程。"""

import os
import signal
import subprocess
import time


def main():
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    process = subprocess.Popen(['gz', 'sim', '-g', '-v', '3'], start_new_session=True)

    def alive():
        process.poll()  # Reap the leader even if other group members remain.
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False

    def send(sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    try:
        while not stopped and process.poll() is None:
            time.sleep(.1)
    finally:
        # Only the newly created process group is signalled, never other worlds.
        for sig, grace in [(signal.SIGINT, 1.5), (signal.SIGTERM, 1), (signal.SIGKILL, .2)]:
            if not alive():
                break
            send(sig)
            deadline = time.monotonic() + grace
            while alive() and time.monotonic() < deadline:
                time.sleep(.05)
        process.wait(timeout=1)
    return 0 if stopped else process.returncode


if __name__ == '__main__':
    raise SystemExit(main())
