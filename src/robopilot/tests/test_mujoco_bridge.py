"""Real MuJoCo physics, rendered sensor evidence and ROS DDS bridge checks."""
import math
import time

import pytest

pytest.importorskip('mujoco')
pytest.importorskip('rclpy')
import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Image, LaserScan, CameraInfo
from cv_bridge import CvBridge
from tf2_ros import Buffer, TransformListener
from rclpy.time import Time

from robopilot.mujoco_bridge import MujocoBridge
from robopilot.perception import detect_red_marker


@pytest.fixture
def bridge():
    context = Context()
    rclpy.init(context=context)
    node = MujocoBridge(context=context)
    try:
        yield node
    finally:
        node.destroy_node()
        context.shutdown()


def command(v=0., w=0.):
    msg = Twist()
    msg.linear.x, msg.angular.z = float(v), float(w)
    return msg


def test_wheel_motion_turn_watchdog_and_invalid_command(bridge):
    bridge._command(command(.2))
    for _ in range(100):
        bridge._command(command(.2))
        bridge.step()
    assert .2 < bridge.data.qpos[bridge.qpos[0]] < .5
    bridge._command(command(.2))
    bridge.last_command -= 1
    bridge.step()
    assert list(bridge.data.ctrl) == [0., 0.]
    for _ in range(100):
        bridge._command(command(0., .6))
        bridge.step()
    assert bridge.data.qpos[bridge.qpos[2]] > .6
    bridge._command(command(float('nan')))
    bridge.step()
    assert list(bridge.data.ctrl) == [0., 0.]
    bridge._command(command(100., 100.))
    assert bridge.command == (.5, 1.5)


def test_collision_blocks_forward_motion(bridge):
    for _ in range(650):
        bridge._command(command(.5))
        bridge.step()
    # Box starts at x=1.85; chassis extends 0.18 m in front of its center.
    assert 1.4 < bridge.data.qpos[bridge.qpos[0]] < 1.7


def test_ros_topics_camera_timestamps_and_sensor_tf(bridge):
    client = Node('bridge_test_client', context=bridge.context)
    executor = SingleThreadedExecutor(context=bridge.context)
    executor.add_node(bridge)
    executor.add_node(client)
    received = {name: [] for name in ('clock', 'odom', 'scan', 'image', 'info')}
    subscriptions = []
    for name, message_type, topic in (
        ('clock', Clock, '/clock'), ('odom', Odometry, '/odom'),
        ('scan', LaserScan, '/scan'), ('image', Image, '/robopilot/camera/image_raw'),
        ('info', CameraInfo, '/robopilot/camera/camera_info'),
    ):
        subscriptions.append(client.create_subscription(message_type, topic,
            lambda msg, name=name: received[name].append(msg), qos_profile_sensor_data))
    buffer = Buffer(node=client)
    listener = TransformListener(buffer, client)
    pub = client.create_publisher(Twist, '/cmd_vel', 10)
    try:
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.01)
            if all(received.values()) and pub.get_subscription_count():
                break
        assert all(received.values()), {k: len(v) for k, v in received.items()}
        image, info, scan = received['image'][-1], received['info'][-1], received['scan'][-1]
        assert image.header == info.header
        assert image.height == 240 and image.width == 320 and image.encoding == 'rgb8'
        assert detect_red_marker(CvBridge().imgmsg_to_cv2(image, 'bgr8'))['status'] == 'detected'
        assert len(scan.ranges) == 360
        assert scan.ranges[180] == pytest.approx(1.85, abs=.03)
        assert scan.ranges[0] == pytest.approx(2.9, abs=.03)
        assert info.k[0] > 0 and info.k[4] > 0
        deadline = time.monotonic()+3
        while not buffer.can_transform('odom', image.header.frame_id, Time.from_msg(image.header.stamp)) and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.01)
        assert buffer.can_transform('odom', image.header.frame_id, Time.from_msg(image.header.stamp))
        assert not buffer.can_transform('map', 'odom', Time())
        start_x = received['odom'][-1].pose.pose.position.x
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            pub.publish(command(.2))
            executor.spin_once(timeout_sec=.01)
        assert received['odom'][-1].pose.pose.position.x > start_x+.1
        stamps = [msg.clock.sec*10**9+msg.clock.nanosec for msg in received['clock']]
        assert all(b > a for a, b in zip(stamps, stamps[1:]))
        assert math.isfinite(received['odom'][-1].twist.twist.linear.x)
    finally:
        executor.remove_node(client)
        executor.remove_node(bridge)
        executor.shutdown()
        client.destroy_node()
