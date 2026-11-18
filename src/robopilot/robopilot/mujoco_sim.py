"""Launch the MuJoCo bridge, geometric map, AMCL and Nav2 in one container."""
import argparse
import copy
from pathlib import Path
import sys

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription, LaunchService
from launch.actions import EmitEvent, ExecuteProcess, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch_ros.actions import Node

from .mujoco_scene import build_scene


def parameters(map_path, start):
    upstream = Path(get_package_share_directory('nav2_bringup'))/'params/nav2_params.yaml'
    params = yaml.safe_load(upstream.read_text())
    amcl = params['amcl']['ros__parameters']
    amcl.update(base_frame_id='base_link', laser_max_range=8., min_particles=300,
                max_particles=1000, update_min_d=.05, update_min_a=.05,
                set_initial_pose=True, initial_pose={'x':start[0], 'y':start[1], 'z':0., 'yaw':start[2]},
                alpha1=.02, alpha2=.02, alpha3=.02, alpha4=.02)
    params['map_server'] = {'ros__parameters': {'yaml_filename': str(map_path)}}
    bt = params['bt_navigator']['ros__parameters']
    bt.update(default_server_timeout=2000, wait_for_service_timeout=5000, bt_loop_duration=20)
    controller = params['controller_server']['ros__parameters']
    controller.update(controller_frequency=15., costmap_update_timeout=1.)
    controller['progress_checker'].update(required_movement_radius=.15, movement_time_allowance=20.)
    controller['general_goal_checker'].update(xy_goal_tolerance=.12, yaw_goal_tolerance=.12)
    # Lightweight differential-drive controller for headless CPU simulation.
    controller['FollowPath'] = {
        'plugin':'nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController',
        'desired_linear_vel':.3, 'lookahead_dist':.45, 'min_lookahead_dist':.25,
        'max_lookahead_dist':.6, 'use_velocity_scaled_lookahead_dist':False,
        'rotate_to_heading_angular_vel':.6, 'use_rotate_to_heading':True,
        'rotate_to_heading_min_angle':.5, 'max_angular_accel':1.5,
        'transform_tolerance':.5, 'min_approach_linear_velocity':.05,
        'approach_velocity_scaling_dist':.5, 'max_allowed_time_to_collision_up_to_carrot':1.,
        'use_collision_detection':True, 'use_regulated_linear_velocity_scaling':True,
        'use_cost_regulated_linear_velocity_scaling':False,
        'regulated_linear_scaling_min_radius':.5, 'regulated_linear_scaling_min_speed':.1,
    }
    for name in ('local_costmap','global_costmap'):
        costmap = params[name][name]['ros__parameters']
        costmap.update(robot_radius=.235, transform_tolerance=.5)
        costmap['inflation_layer'].update(inflation_radius=.45, cost_scaling_factor=4.)
    local = params['local_costmap']['local_costmap']['ros__parameters']
    local['plugins'] = ['obstacle_layer','inflation_layer']
    local['obstacle_layer'] = copy.deepcopy(params['global_costmap']['global_costmap']['ros__parameters']['obstacle_layer'])
    params['planner_server']['ros__parameters']['GridBased'].update(tolerance=.1, allow_unknown=False)
    params['behavior_server']['ros__parameters'].update(transform_tolerance=.5,
                                                       max_rotational_vel=.8, min_rotational_vel=.2)
    params['velocity_smoother']['ros__parameters'].update(max_velocity=[.3,0.,.8], min_velocity=[-.2,0.,-.8],
                                                        max_accel=[.5,0.,1.5], max_decel=[-.8,0.,-1.5])
    params['collision_monitor']['ros__parameters'].update(base_frame_id='base_link', transform_tolerance=.5)
    # Configure every node explicitly; the bridge advances /clock independently.
    def sim_time(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'ros__parameters':
                    child['use_sim_time'] = True
                    child['enable_stamped_cmd_vel'] = False
                else:
                    sim_time(child)
    sim_time(params)
    return params


def description(directory, scene='home', web=True):
    model, map_path, start = build_scene(directory, scene)
    params_path = Path(directory).resolve()/'nav2.yaml'
    params_path.write_text(yaml.safe_dump(parameters(map_path, start)))
    command = [sys.executable, '-m', 'robopilot.mujoco_bridge', '--model', str(model),
               '--initial-pose', *(str(v) for v in start)]
    if web:
        command.append('--web')
    processes = [ExecuteProcess(cmd=command, output='screen')]
    localization = []
    navigation = []
    for package, executable, name, remaps in (
        ('nav2_map_server','map_server','map_server',[]),
        ('nav2_amcl','amcl','amcl',[]),
        ('nav2_controller','controller_server','controller_server',[('cmd_vel','cmd_vel_nav')]),
        ('nav2_planner','planner_server','planner_server',[]),
        ('nav2_smoother','smoother_server','smoother_server',[]),
        ('nav2_behaviors','behavior_server','behavior_server',[('cmd_vel','cmd_vel_nav')]),
        ('nav2_bt_navigator','bt_navigator','bt_navigator',[]),
        ('nav2_velocity_smoother','velocity_smoother','velocity_smoother',[('cmd_vel','cmd_vel_nav')]),
        ('nav2_collision_monitor','collision_monitor','collision_monitor',[]),
    ):
        processes.append(Node(package=package, executable=executable, name=name,
            parameters=[str(params_path)], remappings=remaps, output='screen'))
        (localization if name in ('map_server','amcl') else navigation).append(name)
    for suffix, names in (('localization',localization), ('navigation',navigation)):
        processes.append(Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
            name='lifecycle_manager_'+suffix, output='screen', parameters=[{
                'use_sim_time':True, 'autostart':True, 'node_names':names,
                'bond_timeout':10.}]))
    # Do not leave an active navigation stack controlling a dead simulator.
    handlers = [RegisterEventHandler(OnProcessExit(target_action=p,
        on_exit=[EmitEvent(event=Shutdown(reason='A required simulation/navigation process exited'))]))
        for p in processes]
    ready = ExecuteProcess(cmd=[sys.executable, '-u', '-m', 'robopilot', 'doctor', '--timeout', '90'],
                           output='screen')
    def check_ready(event, context):
        if event.returncode != 0:
            return [EmitEvent(event=Shutdown(reason='Simulation readiness check failed'))]
        return []
    handlers.append(RegisterEventHandler(OnProcessExit(target_action=ready, on_exit=check_ready)))
    return LaunchDescription(handlers+processes+[ready])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', choices=('home','demo'), default='home')
    parser.add_argument('--directory', type=Path, default=Path('runs/mujoco-sim'))
    parser.add_argument('--no-web', action='store_true')
    args = parser.parse_args()
    service = LaunchService()
    service.include_launch_description(description(args.directory, args.scene, not args.no_web))
    return service.run()


if __name__ == '__main__':
    raise SystemExit(main())
