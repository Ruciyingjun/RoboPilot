"""The HTTP viewer streams the ROS bridge's data without owning the clock."""
import time
import urllib.request

import pytest

pytest.importorskip('rclpy')
pytest.importorskip('mujoco')
import rclpy
from rclpy.context import Context
from geometry_msgs.msg import Twist
from mujoco.studio import messages
from robopilot.mujoco_bridge import MujocoBridge


def test_live_viewer_http_shared_state_and_reset_guard():
    context = Context()
    rclpy.init(context=context)
    node = None
    try:
        node = MujocoBridge(context=context, web_port=8080)
        deadline = time.monotonic()+10
        while True:
            node.step()
            try:
                with urllib.request.urlopen('http://127.0.0.1:8080/', timeout=1) as response:
                    assert response.status == 200
                    assert b'<html' in response.read().lower()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.05)
        handle = node.viewer.handle
        assert handle.model is node.model and handle.data is node.data
        cmd = Twist()
        cmd.linear.x = .2
        for _ in range(100):
            node._command(cmd)
            node.step()
        assert handle.data.qpos[node.qpos[0]] > .2
        previous = float(node.data.time)
        handle.dispatch(messages.ResetEvent())
        assert node.data.time == previous
        node.step()
        assert node.data.time > previous
    finally:
        if node is not None:
            node.destroy_node()
        context.shutdown()
