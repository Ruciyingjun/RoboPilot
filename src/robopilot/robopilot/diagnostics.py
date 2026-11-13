"""用途：检查仿真时钟、激光、定位及相机；可显式初始化默认演示场景的已知出生位姿。"""

import time
import math
from dataclasses import asdict


def diagnose(timeout_s=30, initialize_demo=False, initialize_home=False):
    if initialize_demo and initialize_home:
        raise ValueError('不能同时初始化两个场景')
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from sensor_msgs.msg import LaserScan
    from rosgraph_msgs.msg import Clock
    from rclpy.qos import qos_profile_sensor_data
    from .ros_adapter import RosNavigationBackend
    backend = RosNavigationBackend()
    clock_stamps, scans = [], []
    backend.node.create_subscription(Clock, '/clock',
                                     lambda msg: clock_stamps.append(msg.clock.sec * 10**9 + msg.clock.nanosec), 10)
    backend.node.create_subscription(LaserScan, '/scan', lambda msg: scans.append(len(msg.ranges)),
                                     qos_profile_sensor_data)
    try:
        deadline = time.monotonic() + timeout_s
        if initialize_demo or initialize_home:
            pub = backend.node.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)
            while (not pub.get_subscription_count() or not clock_stamps) and time.monotonic() < deadline:
                backend._spin()
            if not pub.get_subscription_count() or not clock_stamps:
                raise TimeoutError('AMCL 或仿真时钟未就绪，未设置初始位姿')
            msg = PoseWithCovarianceStamped()
            msg.header.frame_id = 'map'
            msg.header.stamp = backend.node.get_clock().now().to_msg()
            x, y, yaw = (2.7, -2.1, math.pi/2) if initialize_home else (-2.0, -0.5, 0.0)
            msg.pose.pose.position.x, msg.pose.pose.position.y = x, y
            msg.pose.pose.orientation.z = math.sin(yaw/2)
            msg.pose.pose.orientation.w = math.cos(yaw/2)
            msg.pose.covariance[0] = msg.pose.covariance[7] = 0.1
            msg.pose.covariance[35] = 0.05
            pub.publish(msg)
        pose = backend.prepare(max(0, deadline-time.monotonic()))
        while (len(clock_stamps) < 2 or not scans) and time.monotonic() < deadline:
            backend._spin()
        clock_ok = len(clock_stamps) > 1 and clock_stamps[-1] > clock_stamps[0]
        result = {'clock_advancing': clock_ok, 'scan_samples': scans[-1] if scans else 0,
                  'localized_pose': asdict(pose), 'demo_initial_pose_set': initialize_demo,
                  'home_initial_pose_set': initialize_home}
        try:
            frame = backend.capture_image(max(0.1, deadline-time.monotonic()))
            result['camera'] = {'available': True, 'shape': list(frame.image.shape),
                                'stamp_ns': frame.stamp_ns}
        except TimeoutError as exc:
            result['camera'] = {'available': False, 'reason': str(exc)}
        result['ready'] = clock_ok and bool(scans) and bool(scans[-1]) and result['camera']['available']
        return result
    finally:
        backend.close()
