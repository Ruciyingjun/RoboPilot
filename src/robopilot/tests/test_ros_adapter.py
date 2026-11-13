"""用途：使用独立 ROS 域的测试服务端验证导航通信与取消边界，不代表 Gazebo 实测。"""

import threading
import time

import pytest

rclpy = pytest.importorskip('rclpy')
from geometry_msgs.msg import TransformStamped
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from tf2_ros import TransformBroadcaster

from robopilot.ros_adapter import RosNavigationBackend
from robopilot.schemas import Pose

pytestmark = pytest.mark.ros


@pytest.fixture
def server(monkeypatch):
    # Keep test endpoints separate from the user's normal ROS domain.
    monkeypatch.setenv('ROS_DOMAIN_ID', '173')
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    node = Node('robopilot_test_nav2', context=context)
    group = ReentrantCallbackGroup()
    state = {'outcome': 'success', 'goals': 0, 'cancels': 0,
             'accept_delay': 0, 'allow_cancel': True, 'active': True,
             'tf_age': 0.0, 'received_poses': [], 'image_age': None,
             'state_calls': 0, 'first_state_delay': 0.0}

    def execute(goal):
        state['goals'] += 1
        state['received_poses'].append(goal.request.pose)
        deadline = time.monotonic() + (2 if state['outcome'] == 'slow' else 0.1)
        while time.monotonic() < deadline:
            if goal.is_cancel_requested:
                state['cancels'] += 1
                goal.canceled()
                return NavigateToPose.Result()
            time.sleep(0.01)
        result = NavigateToPose.Result()
        if state['outcome'] == 'abort':
            result.error_code = 1
            result.error_msg = 'Injected server abort'
            goal.abort()
        else:
            goal.succeed()
        return result

    def accept_goal(request):
        time.sleep(state['accept_delay'])
        return GoalResponse.REJECT if state['outcome'] == 'reject' else GoalResponse.ACCEPT

    action = ActionServer(node, NavigateToPose, '/navigate_to_pose', execute,
                          callback_group=group,
                          goal_callback=accept_goal,
                          cancel_callback=lambda _: (CancelResponse.ACCEPT if state['allow_cancel']
                                                     else CancelResponse.REJECT))

    def get_state(request, response):
        state['state_calls'] += 1
        if state['state_calls']==1 and state['first_state_delay']:
            time.sleep(state['first_state_delay'])
        response.current_state.id = 3 if state['active'] else 2
        response.current_state.label = 'active' if state['active'] else 'inactive'
        return response

    node.create_service(GetState, '/bt_navigator/get_state', get_state, callback_group=group)
    broadcaster = TransformBroadcaster(node)

    def publish_tf():
        tf = TransformStamped()
        stamp = node.get_clock().now() - rclpy.duration.Duration(seconds=state['tf_age'])
        tf.header.stamp = stamp.to_msg()
        tf.header.frame_id = 'map'
        tf.child_frame_id = 'base_link'
        tf.transform.translation.x = 1.25
        tf.transform.rotation.w = 1.0
        broadcaster.sendTransform(tf)

    node.create_timer(0.05, publish_tf, callback_group=group)
    from sensor_msgs.msg import Image
    from rclpy.qos import qos_profile_sensor_data
    image_pub = node.create_publisher(Image, '/robopilot/camera/image_raw', qos_profile_sensor_data)

    def publish_image():
        if state['image_age'] is None:
            return
        import numpy as np
        from cv_bridge import CvBridge
        image = CvBridge().cv2_to_imgmsg(np.full((60, 80, 3), 100, dtype=np.uint8), 'bgr8')
        image.header.frame_id = 'test_camera'
        image.header.stamp = (node.get_clock().now() -
                              rclpy.duration.Duration(seconds=state['image_age'])).to_msg()
        image_pub.publish(image)

    node.create_timer(0.1, publish_image, callback_group=group)
    executor = MultiThreadedExecutor(num_threads=3, context=context)
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        executor.shutdown(timeout_sec=5)
        thread.join(timeout=5)
        action.destroy()
        node.destroy_node()
        context.try_shutdown()


@pytest.mark.parametrize('outcome,expected', [
    ('success', 'SUCCEEDED'), ('abort', 'FAILED'), ('reject', 'FAILED'), ('slow', 'TIMED_OUT'),
])
def test_nav2_action_lifecycle(server, outcome, expected):
    backend = RosNavigationBackend(use_sim_time=False, cancel_timeout=2.0)
    try:
        start = backend.prepare(8)
        assert start.x == pytest.approx(1.25)
        server['outcome'] = outcome
        result = backend.navigate(Pose(2.0, 0.0, 0.0), 0.3 if outcome == 'slow' else 3)
        assert result.status == expected
        assert result.safe_to_continue
        assert backend.goal_handle is None
        if outcome == 'slow':
            assert server['cancels'] == 1
        # A terminal result must free the adapter to send the next goal.
        server['outcome'] = 'success'
        assert backend.navigate(Pose(1.0, 0.0, 0.0), 3).status == 'SUCCEEDED'
    finally:
        backend.close()


def test_delayed_acceptance_is_canceled_after_timeout(server):
    backend = RosNavigationBackend(use_sim_time=False, cancel_timeout=2)
    try:
        backend.prepare(8)
        server.update(outcome='slow', accept_delay=0.3)
        result = backend.navigate(Pose(2.0, 0.0, 0.0), 0.1)
        assert result.status == 'TIMED_OUT'
        assert result.safe_to_continue
        assert server['cancels'] == 1
        assert backend.send_future is None and backend.goal_handle is None
    finally:
        backend.close()


def test_unconfirmed_cancel_blocks_next_navigation(server):
    backend = RosNavigationBackend(use_sim_time=False, cancel_timeout=0.2)
    try:
        backend.prepare(8)
        server.update(outcome='slow', allow_cancel=False)
        result = backend.navigate(Pose(2.0, 0.0, 0.0), 0.2)
        assert result.status == 'TIMED_OUT'
        assert not result.safe_to_continue
        with pytest.raises(RuntimeError, match='outstanding'):
            backend.navigate(Pose(3.0, 0.0, 0.0), 1)
        assert server['goals'] == 1
    finally:
        server['allow_cancel'] = True
        backend.cancel_timeout = 2
        backend.close()


@pytest.mark.parametrize('condition', ['inactive', 'stale_tf', 'missing_clock'])
def test_unready_localization_or_clock_never_sends_goal(server, condition):
    server['active'] = condition != 'inactive'
    server['tf_age'] = 10.0 if condition == 'stale_tf' else 0.0
    backend = RosNavigationBackend(use_sim_time=condition == 'missing_clock')
    try:
        with pytest.raises(TimeoutError):
            backend.prepare(0.5)
        assert server['goals'] == 0
    finally:
        backend.close()


@pytest.mark.parametrize('age', [0.0, 10.0, None])
def test_only_fresh_camera_frames_can_be_inspected(server, age):
    backend = RosNavigationBackend(use_sim_time=False)
    try:
        backend.prepare(8)
        server['image_age'] = age
        if age == 0:
            frame = backend.capture_image(2)
            assert frame.image.shape == (60, 80, 3)
            assert frame.pose['x'] == pytest.approx(1.25)
        else:
            with pytest.raises(TimeoutError):
                backend.capture_image(0.4)
    finally:
        backend.close()


def test_startup_retries_an_unanswered_lifecycle_query(server):
    server['first_state_delay']=1.5
    backend=RosNavigationBackend(use_sim_time=False)
    try:
        assert backend.prepare(6).x == pytest.approx(1.25)
        assert server['state_calls'] >= 2
        assert server['goals']==0
    finally:
        backend.close()
