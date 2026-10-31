"""用途：防止上游修改共享 launch 参数后错误跳过 Gazebo GUI。"""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip('launch')
from launch import LaunchContext
from launch.actions import ExecuteProcess


@pytest.mark.parametrize('requested,expected', [('False', True), ('True', False)])
def test_gui_condition_survives_upstream_headless_override(requested, expected):
    path = Path(__file__).parents[1] / 'launch/simulation.launch.py'
    spec = importlib.util.spec_from_file_location('robopilot_sim_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = LaunchContext()
    context.launch_configurations.update({
        'headless': requested, 'robot_body': 'service', 'scene': 'demo',
        'initialize_home': 'False', 'initialize_demo': 'False', 'demo_marker': 'True',
    })
    actions = module.simulation(context)
    gui = next(action for action in actions if type(action) is ExecuteProcess)
    assert gui.condition.evaluate(context) is expected
    # IncludeLaunchDescription sets this shared configuration for its own server.
    context.launch_configurations['headless'] = 'True'
    assert gui.condition.evaluate(context) is expected
