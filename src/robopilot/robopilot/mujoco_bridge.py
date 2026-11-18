"""MuJoCo differential drive -> ROS sensors. Odometry uses simulator truth, not SLAM.

Run in the ROS container: python -m robopilot.mujoco_bridge
"""

import argparse
import math
from pathlib import Path
import time

import mujoco
import numpy as np
import rclpy
from builtin_interfaces.msg import Time
from geometry_msgs.msg import TransformStamped, Twist, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.clock import Clock as RclClock, ClockType
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image, LaserScan, JointState
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster


def default_model():
    source = Path(__file__).resolve().parents[1] / 'models' / 'bridge_demo.xml'
    if source.exists():
        return source
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory('robopilot')) / 'models' / 'bridge_demo.xml'


class MujocoBridge(Node):
    """Owns simulation and rendering on the single ROS executor thread.

    A wall-clock timer advances 20 ms of simulation per tick. Under load simulation
    slows down; timestamps always follow data.time. No map->odom is fabricated.
    """

    def __init__(self, model_path=None, *, stamped=False, camera=True, context=None, web_port=None,
                 initial_pose=(0., 0., 0.)):
        super().__init__('robopilot_mujoco_bridge', context=context)
        self.renderer = None
        self.viewer = None
        self.model = mujoco.MjModel.from_xml_path(str(model_path or default_model()))
        self.data = mujoco.MjData(self.model)
        if not math.isclose(self.model.opt.timestep, .005):
            raise ValueError('Bridge model must use a 0.005 s timestep')
        self.qpos = [self.model.jnt_qposadr[self.model.joint(n).id]
                     for n in ('base_x', 'base_y', 'base_yaw')]
        self.qvel = [self.model.jnt_dofadr[self.model.joint(n).id]
                     for n in ('base_x', 'base_y', 'base_yaw')]
        if len(initial_pose) != 3 or not all(math.isfinite(v) for v in initial_pose):
            raise ValueError('initial_pose must contain three finite numbers')
        self.data.qpos[self.qpos] = initial_pose
        self.motors = [self.model.actuator(n).id for n in ('left_motor', 'right_motor')]
        self.wheels = [self.model.jnt_qposadr[self.model.joint(n).id]
                       for n in ('left_wheel_joint', 'right_wheel_joint')]
        self.body_id = self.model.body('base_link').id
        self.command = (0., 0.)
        self.last_command = float('-inf')
        self.tick = 0
        mujoco.mj_forward(self.model, self.data)
        if camera:
            self.renderer = mujoco.Renderer(self.model, height=240, width=320)
        self.clock_pub = self.create_publisher(Clock, '/clock', 10)
        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.scan_pub = self.create_publisher(LaserScan, '/scan', qos_profile_sensor_data)
        self.image_pub = self.create_publisher(Image, '/robopilot/camera/image_raw', qos_profile_sensor_data)
        self.info_pub = self.create_publisher(CameraInfo, '/robopilot/camera/camera_info', qos_profile_sensor_data)
        self.joint_pub = self.create_publisher(JointState, '/joint_states', 10)
        self.tf = TransformBroadcaster(self)
        self.static_tf = StaticTransformBroadcaster(self)
        self._static_transforms()
        message_type = TwistStamped if stamped else Twist
        self.subscription = self.create_subscription(message_type, '/cmd_vel', self._command, 10)
        # Never drive the physics timer from the /clock we ourselves publish.
        self.timer = self.create_timer(.02, self.step, clock=RclClock(clock_type=ClockType.STEADY_TIME))
        if web_port is not None:
            from .mujoco_web import LiveViewer
            self.viewer = LiveViewer(self.model, self.data, web_port)
            self.get_logger().info(f'Live Web Viewer on port {web_port}; motion is controlled through ROS /cmd_vel')
        self.get_logger().info('MuJoCo bridge ready: /cmd_vel -> wheels; /clock /odom /tf /scan /robopilot/camera/image_raw')

    def _command(self, msg):
        twist = msg.twist if isinstance(msg, TwistStamped) else msg
        v, w = twist.linear.x, twist.angular.z
        # Invalid commands actively stop instead of propagating NaNs into physics.
        self.command = ((max(-.5, min(.5, v)), max(-1.5, min(1.5, w)))
                        if math.isfinite(v) and math.isfinite(w) else (0., 0.))
        self.last_command = time.monotonic()

    def stamp(self):
        ns = round(float(self.data.time) * 1e9)
        return Time(sec=ns // 10**9, nanosec=ns % 10**9)

    def _static_transforms(self):
        transforms = []
        camera = self.model.camera('inspection').id
        optical = np.empty(4)
        mujoco.mju_mulQuat(optical, self.model.cam_quat[camera], np.array([0., 1., 0., 0.]))
        for child, xyz, quat in (
            ('laser_frame', (0., 0., .09), (0., 0., 0., 1.)),
            ('robopilot_camera_optical_frame', self.model.cam_pos[camera],
             (optical[1], optical[2], optical[3], optical[0])),
        ):
            t = TransformStamped()
            t.header.frame_id, t.child_frame_id = 'base_link', child
            t.transform.translation.x, t.transform.translation.y, t.transform.translation.z = xyz
            t.transform.rotation.x, t.transform.rotation.y, t.transform.rotation.z, t.transform.rotation.w = quat
            transforms.append(t)
        self.static_tf.sendTransform(transforms)

    def step(self):
        v, w = self.command if time.monotonic()-self.last_command <= .5 else (0., 0.)
        # Actual wheel velocity actuators; positions are never teleported.
        self.data.ctrl[self.motors] = [(v-w*.19)/.08, (v+w*.19)/.08]
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        stamp = self.stamp()
        clock = Clock()
        clock.clock = stamp
        self.clock_pub.publish(clock)
        self._odometry(stamp)
        self.tick += 1
        if self.tick % 5 == 0:
            self._scan(stamp)
        if self.renderer is not None and self.tick % 25 == 0:
            self._camera(stamp)
        if self.viewer is not None:
            self.viewer.sync()

    def _odometry(self, stamp):
        x, y, yaw = (float(self.data.qpos[i]) for i in self.qpos)
        dx, dy, dyaw = (float(self.data.qvel[i]) for i in self.qvel)
        odom = Odometry()
        odom.header.stamp, odom.header.frame_id, odom.child_frame_id = stamp, 'odom', 'base_link'
        odom.pose.pose.position.x, odom.pose.pose.position.y = x, y
        odom.pose.pose.position.z = float(self.data.xpos[self.body_id, 2])
        odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = math.sin(yaw/2), math.cos(yaw/2)
        odom.twist.twist.linear.x = math.cos(yaw)*dx + math.sin(yaw)*dy
        odom.twist.twist.linear.y = -math.sin(yaw)*dx + math.cos(yaw)*dy
        odom.twist.twist.angular.z = dyaw
        # Small nominal variances describe simulated truth, not a real estimator.
        for i in (0, 7, 14, 21, 28, 35):
            odom.pose.covariance[i] = odom.twist.covariance[i] = 1e-6
        self.odom_pub.publish(odom)
        t = TransformStamped()
        t.header, t.child_frame_id = odom.header, 'base_link'
        t.transform.translation.x, t.transform.translation.y, t.transform.translation.z = x, y, odom.pose.pose.position.z
        t.transform.rotation = odom.pose.pose.orientation
        self.tf.sendTransform(t)
        joints = JointState()
        joints.header.stamp = stamp
        joints.name = ['left_wheel_joint', 'right_wheel_joint']
        joints.position = [float(self.data.qpos[i]) for i in self.wheels]
        self.joint_pub.publish(joints)

    def _scan(self, stamp):
        scan = LaserScan()
        scan.header.stamp, scan.header.frame_id = stamp, 'laser_frame'
        scan.angle_min, scan.angle_increment = -math.pi, 2*math.pi/360
        scan.angle_max = scan.angle_min + 359*scan.angle_increment
        scan.range_min, scan.range_max, scan.scan_time = .05, 8., .1
        x, y, yaw = (float(self.data.qpos[i]) for i in self.qpos)
        origin = np.array([x, y, float(self.data.xpos[self.body_id, 2])+.09])
        # Group 1 contains the robot. Static world geometry uses group 0.
        groups = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)
        geomid = np.zeros(1, dtype=np.int32)
        ranges = []
        for i in range(360):
            angle = yaw + scan.angle_min + i*scan.angle_increment
            distance = mujoco.mj_ray(self.model, self.data, origin,
                np.array([math.cos(angle), math.sin(angle), 0.]), groups, 1, self.body_id, geomid)
            ranges.append(float(distance) if scan.range_min <= distance <= scan.range_max else float('inf'))
        scan.ranges = ranges
        self.scan_pub.publish(scan)

    def _camera(self, stamp):
        self.renderer.update_scene(self.data, camera='inspection')
        rgb = self.renderer.render()
        msg = Image()
        msg.header.stamp, msg.header.frame_id = stamp, 'robopilot_camera_optical_frame'
        msg.height, msg.width, msg.encoding, msg.step = 240, 320, 'rgb8', 320*3
        msg.data = rgb.tobytes()
        self.image_pub.publish(msg)
        info = CameraInfo()
        info.header, info.height, info.width = msg.header, 240, 320
        fovy = math.radians(float(self.model.cam_fovy[self.model.camera('inspection').id]))
        focal = 120/math.tan(fovy/2)
        info.distortion_model, info.d = 'plumb_bob', [0.]*5
        info.k = [focal, 0., 159.5, 0., focal, 119.5, 0., 0., 1.]
        info.r = [1., 0., 0., 0., 1., 0., 0., 0., 1.]
        info.p = [focal, 0., 159.5, 0., 0., focal, 119.5, 0., 0., 0., 1., 0.]
        self.info_pub.publish(info)

    def destroy_node(self):
        self.timer.cancel()
        self.data.ctrl[self.motors] = 0
        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
        return super().destroy_node()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--stamped', action='store_true', help='Receive TwistStamped instead of Twist on /cmd_vel')
    parser.add_argument('--no-camera', action='store_true', help='Disable rendering for physics-only diagnostics')
    parser.add_argument('--web', action='store_true', help='Show this ROS simulation in a live browser viewer')
    parser.add_argument('--web-port', type=int, default=8080)
    parser.add_argument('--initial-pose', nargs=3, type=float, default=(0., 0., 0.), metavar=('X','Y','YAW'))
    args, ros_args = parser.parse_known_args(argv)
    if not 1 <= args.web_port <= 65535:
        parser.error('--web-port must be between 1 and 65535')
    rclpy.init(args=ros_args)
    node = None
    try:
        node = MujocoBridge(args.model, stamped=args.stamped, camera=not args.no_camera,
                            web_port=args.web_port if args.web else None, initial_pose=args.initial_pose)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
