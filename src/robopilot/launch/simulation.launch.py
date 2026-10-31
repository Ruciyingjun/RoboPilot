"""用途：包装已安装的 Nav2 TurtleBot3 仿真入口，提供 Gazebo/RViz 显示选项。"""

import atexit
import os
import shutil
import tempfile
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET

from robopilot.home_scene import build_home
from robopilot.service_robot import configure_robot

import xacro
import yaml

from ament_index_python.packages import get_package_share_directory, get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, ExecuteProcess, SetEnvironmentVariable
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def simulation(context):
    """Extend installed assets at launch time; never modify /opt/ros files."""
    sim_dir = Path(get_package_share_directory('nav2_minimal_tb3_sim'))
    directory = Path(tempfile.mkdtemp(prefix='robopilot_sim_'))
    # OnShutdown occurs before child processes exit; keep textures/maps alive until exit.
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    headless = LaunchConfiguration('headless').perform(context)
    robot = ET.fromstring(xacro.process_file(str(sim_dir / 'urdf/gz_waffle.sdf.xacro')).toxml())
    body = LaunchConfiguration('robot_body').perform(context)
    if body not in ('service', 'turtlebot'):
        raise ValueError('robot_body 必须为 service 或 turtlebot')
    urdf = (sim_dir / 'urdf/turtlebot3_waffle.urdf').read_text()
    robot_description = configure_robot(robot, urdf, service=body == 'service')
    ET.ElementTree(robot).write(directory / 'robot.sdf', encoding='unicode')
    world = ET.fromstring(xacro.process_file(str(sim_dir / 'worlds/tb3_sandbox.sdf.xacro'),
                                            mappings={'headless': headless}).toxml())
    scene = LaunchConfiguration('scene').perform(context)
    if scene not in ('demo', 'home'):
        raise ValueError('scene 必须是 demo 或 home')
    if scene == 'home' and LaunchConfiguration('initialize_demo').perform(context).lower() == 'true':
        raise ValueError('家居场景不能使用 initialize_demo；请在 RViz 设置实际初始位姿')
    if scene != 'home' and LaunchConfiguration('initialize_home').perform(context).lower() == 'true':
        raise ValueError('initialize_home 仅适用于全新家居场景')
    extra_arguments = {}
    if scene == 'home':
        extra_arguments = {'map': build_home(world.find('world'), directory, LaunchConfiguration('toolbox_state').perform(context),
                           LaunchConfiguration('backpack_state').perform(context),
                           LaunchConfiguration('door_state').perform(context),
                           LaunchConfiguration('fruit_state').perform(context)),
                           'x_pose': '2.7', 'y_pose': '-2.1', 'yaw': '1.5708'}
    if scene == 'demo' and LaunchConfiguration('demo_marker').perform(context).lower() == 'true':
        world.find('world').append(ET.fromstring('''<model name="red_marker"><static>true</static>
          <pose>-0.7 -0.5 0.15 0 0 0</pose><link name="marker">
          <collision name="collision"><geometry><box><size>0.16 0.24 0.3</size></box></geometry></collision>
          <visual name="visual"><geometry><box><size>0.16 0.24 0.3</size></box></geometry>
          <material><ambient>1 0 0 1</ambient><diffuse>1 0 0 1</diffuse></material></visual>
          </link></model>'''))
    ET.ElementTree(world).write(directory / 'world.sdf', encoding='unicode')
    # Default 20 ms action handshake is too short under VM software rendering load.
    params = yaml.safe_load((Path(get_package_share_directory('nav2_bringup')) /
                             'params/nav2_params.yaml').read_text())
    params['bt_navigator']['ros__parameters'].update(
        default_server_timeout=2000, wait_for_service_timeout=5000, bt_loop_duration=20)
    params_path = directory / 'nav2.yaml'
    params_path.write_text('# 用途：虚拟机Nav2行为树内部等待配置，其余参数沿用上游。\n' +
                           yaml.safe_dump(params))
    upstream = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('nav2_bringup'), 'launch', 'tb3_simulation_launch.py')),
        launch_arguments={'headless': 'True', 'use_rviz': LaunchConfiguration('use_rviz'),
                          'world': str(directory / 'world.sdf'),
                          'robot_sdf': str(directory / 'robot.sdf'), 'use_sim_time': 'True',
                          'use_robot_state_pub': 'False', 'params_file': str(params_path),
                          'use_composition': LaunchConfiguration('use_composition'),
                          **extra_arguments}.items())
    return [Node(package='robot_state_publisher', executable='robot_state_publisher',
                 parameters=[{'robot_description': robot_description, 'use_sim_time': True}],
                 output='screen'),
            upstream,
            ExecuteProcess(cmd=['/usr/bin/python3', '-m', 'robopilot.gazebo_gui'],
                           # Freeze the user's value before upstream include sets headless=True.
                           condition=UnlessCondition(headless),
                           output='screen'),
            Node(package='ros_gz_image', executable='image_bridge',
                 arguments=['/robopilot/camera/image_raw'], output='screen')]


def generate_launch_description():
    return LaunchDescription([
        # 每次启动隔离 Gazebo Transport，防止 GUI/生成服务连到其他正在运行的世界。
        SetEnvironmentVariable('GZ_PARTITION', 'robopilot_' + uuid.uuid4().hex),
        DeclareLaunchArgument('backpack_state', default_value='hanging', description='hanging/floor/absent/occluded'),
        DeclareLaunchArgument('door_state', default_value='closed', description='closed/open/ajar'),
        DeclareLaunchArgument('fruit_state', default_value='present', description='present/empty/absent'),
        DeclareLaunchArgument('toolbox_state', default_value='present',
                             description='家居工具箱 present/absent/distractor/occluded'),
        DeclareLaunchArgument('robot_body', default_value='service',
                              description='service 酒店服务外观或 turtlebot 原底盘'),
        DeclareLaunchArgument('scene', default_value='demo', description='demo 或 home 家居预览'),
        DeclareLaunchArgument('headless', default_value='True'),
        DeclareLaunchArgument('use_composition', default_value='False',
                              description='默认独立 Nav2 进程，规避组件容器并发关闭风险'),
        DeclareLaunchArgument('use_rviz', default_value='True'),
        DeclareLaunchArgument('demo_marker', default_value='True'),
        DeclareLaunchArgument('initialize_home', default_value='False',
                             description='仅全新家居场景：设置玄关出生位姿并检查导航'),
        DeclareLaunchArgument('initialize_demo', default_value='False',
                             description='Explicitly initialize the fresh default demo and run doctor'),
        OpaqueFunction(function=simulation),
        ExecuteProcess(cmd=[os.path.join(get_package_prefix('robopilot'), 'lib', 'robopilot', 'robopilot'),
                            'doctor', '--initialize-demo', '--timeout', '60'],
             condition=IfCondition(LaunchConfiguration('initialize_demo')), output='screen'),
        ExecuteProcess(cmd=[os.path.join(get_package_prefix('robopilot'), 'lib', 'robopilot', 'robopilot'),
                            'doctor', '--initialize-home', '--timeout', '90'],
             condition=IfCondition(LaunchConfiguration('initialize_home')), output='screen'),
    ])
