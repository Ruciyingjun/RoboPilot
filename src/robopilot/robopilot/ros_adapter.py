"""用途：通过 ROS 2 Action 调用 Nav2，检查定位就绪，处理反馈、超时和取消确认。"""

import math
import time

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.signals import SignalHandlerOptions
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener

from .backends import NavigationResult
from .schemas import Pose


class RosNavigationBackend:
    name = 'ros'

    def __init__(self, use_sim_time=True, base_frame='base_link', cancel_timeout=5.0):
        self.context = Context()
        rclpy.init(context=self.context, signal_handler_options=SignalHandlerOptions.NO)
        self.node = Node('robopilot_executor', context=self.context, parameter_overrides=[
            Parameter('use_sim_time', value=use_sim_time)])
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.client = ActionClient(self.node, NavigateToPose, '/navigate_to_pose')
        self.lifecycle = self.node.create_client(GetState, '/bt_navigator/get_state')
        self.tf_buffer = Buffer(node=self.node)
        self.tf_listener = TransformListener(self.tf_buffer, self.node)
        self.base_frame = base_frame
        self.use_sim_time = use_sim_time
        self.cancel_timeout = cancel_timeout
        self.goal_handle = None
        self.send_future = None
        self.result_future = None
        self.last_feedback = {}

    def _spin(self, duration=0.05):
        if not self.context.ok():
            raise RuntimeError('ROS context stopped')
        self.executor.spin_once(timeout_sec=max(0.0, duration))

    def _wait(self, future, timeout_s):
        deadline = time.monotonic() + timeout_s
        while not future.done():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('ROS operation exceeded its wall-clock deadline')
            self._spin(min(0.05, remaining))
        return future.result()

    def prepare(self, timeout_s):
        """Bound both startup and individual lifecycle queries; never guess origin."""
        deadline = time.monotonic() + timeout_s
        state_future = None
        state_sent = 0.0
        active = False
        reason = '等待导航服务发现'
        try:
            while time.monotonic() < deadline:
                self._spin(min(0.05, max(0, deadline-time.monotonic())))
                if state_future is not None and not state_future.done() and time.monotonic()-state_sent >= 1:
                    self.lifecycle.remove_pending_request(state_future)
                    state_future.cancel()
                    state_future = None
                    reason = '生命周期查询超过 1 秒，正在重试'
                if not self.client.server_is_ready():
                    reason = '/navigate_to_pose 尚不可用'
                    continue
                if not active:
                    if not self.lifecycle.service_is_ready():
                        reason = '/bt_navigator/get_state 尚不可用'
                        continue
                    if state_future is None:
                        state_future = self.lifecycle.call_async(GetState.Request())
                        state_sent = time.monotonic()
                    elif state_future.done():
                        response = state_future.result()
                        active = response is not None and response.current_state.id == 3
                        state_future = None
                        if not active:
                            reason = 'bt_navigator 尚未 active'
                    if not active:
                        continue
                now = self.node.get_clock().now()
                if self.use_sim_time and now.nanoseconds == 0:
                    reason = '尚未收到有效仿真时钟'
                    continue
                try:
                    transform = self.tf_buffer.lookup_transform('map', self.base_frame, Time())
                except TransformException:
                    reason = 'map→base_link TF 尚不可用'
                    continue
                age = (now.nanoseconds - Time.from_msg(transform.header.stamp).nanoseconds) / 1e9
                if not -0.1 <= age <= 2.0:
                    reason = f'TF 时间差不在有效范围，age={age:.3f}s'
                    continue
                t, q = transform.transform.translation, transform.transform.rotation
                yaw = math.atan2(2 * (q.w * q.z + q.x * q.y),
                                 1 - 2 * (q.y * q.y + q.z * q.z))
                return Pose(t.x, t.y, yaw)
            raise TimeoutError('Nav2 未就绪：' + reason + '；检查时钟、生命周期及定位，必要时在 RViz 设置初始位姿。')
        finally:
            if state_future is not None and not state_future.done():
                self.lifecycle.remove_pending_request(state_future)
                state_future.cancel()

    def _feedback(self, message):
        feedback = message.feedback
        self.last_feedback = {
            'distance_remaining_m': float(feedback.distance_remaining),
            'number_of_recoveries': int(feedback.number_of_recoveries),
        }

    def capture_image(self, timeout_s):
        from dataclasses import asdict
        from cv_bridge import CvBridge
        from sensor_msgs.msg import Image
        from rclpy.qos import qos_profile_sensor_data
        from .perception import CameraFrame
        trigger_ns = self.node.get_clock().now().nanoseconds
        frames = []

        def receive(message):
            stamp = Time.from_msg(message.header.stamp).nanoseconds
            age = (self.node.get_clock().now().nanoseconds - stamp) / 1e9
            if stamp > trigger_ns and 0 <= age <= 2:
                frames.append(message)

        sub = self.node.create_subscription(Image, '/robopilot/camera/image_raw', receive,
                                             qos_profile_sensor_data)
        try:
            deadline = time.monotonic() + timeout_s
            while not frames and time.monotonic() < deadline:
                self._spin(min(0.05, max(0, deadline - time.monotonic())))
            if not frames:
                raise TimeoutError('未收到巡检开始后的新鲜相机图像')
            msg = frames[-1]
            while True:
                try:
                    transform = self.tf_buffer.lookup_transform('map', self.base_frame,
                                                               Time.from_msg(msg.header.stamp))
                    break
                except TransformException:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('相机时间戳对应的机器人位姿不可用')
                    self._spin(0.05)
            t, q = transform.transform.translation, transform.transform.rotation
            pose = Pose(t.x, t.y, math.atan2(2 * (q.w*q.z + q.x*q.y),
                                            1 - 2*(q.y*q.y + q.z*q.z)))
            return CameraFrame(CvBridge().imgmsg_to_cv2(msg, 'bgr8'),
                               Time.from_msg(msg.header.stamp).nanoseconds,
                               msg.header.frame_id, asdict(pose))
        finally:
            self.node.destroy_subscription(sub)

    def navigate(self, pose, timeout_s):
        if self.send_future is not None or self.goal_handle is not None:
            raise RuntimeError('A previous navigation request is still outstanding')
        self.last_feedback = {}
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = pose.frame_id
        goal.pose.header.stamp = self.node.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(pose.x)
        goal.pose.pose.position.y = float(pose.y)
        goal.pose.pose.orientation.z = math.sin(pose.yaw / 2)
        goal.pose.pose.orientation.w = math.cos(pose.yaw / 2)
        deadline = time.monotonic() + timeout_s
        self.send_future = self.client.send_goal_async(goal, feedback_callback=self._feedback)
        try:
            self.goal_handle = self._wait(self.send_future, max(0, deadline - time.monotonic()))
            self.send_future = None
            if not self.goal_handle.accepted:
                self.goal_handle = None
                return NavigationResult('FAILED', 'GOAL_REJECTED', 'Nav2 拒绝导航目标')
            self.result_future = self.goal_handle.get_result_async()
            response = self._wait(self.result_future, max(0, deadline - time.monotonic()))
        except TimeoutError:
            confirmed = self.cancel()
            return NavigationResult('TIMED_OUT', 'NAVIGATION_TIMEOUT',
                                    '导航超过墙上时间上限；' + ('已确认终止' if confirmed else '取消未确认'),
                                    confirmed, self.last_feedback.copy())
        status, result = response.status, response.result
        terminal = status in (GoalStatus.STATUS_SUCCEEDED, GoalStatus.STATUS_ABORTED,
                              GoalStatus.STATUS_CANCELED)
        if terminal:
            self._clear_goal()
        if status == GoalStatus.STATUS_SUCCEEDED and result.error_code == 0:
            return NavigationResult('SUCCEEDED', feedback=self.last_feedback.copy())
        return NavigationResult(
            'CANCELED' if status == GoalStatus.STATUS_CANCELED else 'FAILED',
            f'NAV2_{result.error_code}_STATUS_{status}', result.error_msg or ('Nav2中止导航且未返回具体原因，请检查bt_navigator/planner_server日志'
                                   if status == GoalStatus.STATUS_ABORTED else '导航未成功'),
            terminal, self.last_feedback.copy())

    def _clear_goal(self):
        self.send_future = self.goal_handle = self.result_future = None

    def cancel(self):
        """A cancel acknowledgement alone is insufficient: wait for a terminal result."""
        deadline = time.monotonic() + self.cancel_timeout
        try:
            if self.send_future is not None:
                self.goal_handle = self._wait(self.send_future, max(0, deadline - time.monotonic()))
                self.send_future = None
            if self.goal_handle is None:
                return True
            if not self.goal_handle.accepted:
                self._clear_goal()
                return True
            if self.result_future is None:
                self.result_future = self.goal_handle.get_result_async()
            if not self.result_future.done():
                future = self.goal_handle.cancel_goal_async()
                self._wait(future, max(0, deadline - time.monotonic()))
            response = self._wait(self.result_future, max(0, deadline - time.monotonic()))
            if response.status not in (GoalStatus.STATUS_SUCCEEDED, GoalStatus.STATUS_ABORTED,
                                       GoalStatus.STATUS_CANCELED):
                return False
            self._clear_goal()
            return True
        except Exception:
            return False

    def close(self):
        try:
            if not self.cancel():
                self.node.get_logger().error('无法确认 Nav2 目标已停止，请检查机器人状态。')
        finally:
            self.executor.shutdown()
            self.client.destroy()
            self.node.destroy_node()
            self.context.try_shutdown()
