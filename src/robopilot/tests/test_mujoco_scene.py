"""Map provenance, compiled home geometry and launch parameter compatibility."""
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
pytest.importorskip('rclpy')
mujoco = pytest.importorskip('mujoco')
import yaml
import numpy as np

from robopilot.home_scene import build_home
from robopilot.mujoco_scene import build_scene
from robopilot.mujoco_sim import parameters


def test_home_map_and_geometry_are_from_existing_source(tmp_path):
    model, map_path, start = build_scene(tmp_path/'converted')
    original = tmp_path/'original'
    original.mkdir()
    source_world = ET.Element('world')
    build_home(source_world, original)
    assert (map_path.parent/'home.pgm').read_bytes() == (original/'home.pgm').read_bytes()
    compiled = mujoco.MjModel.from_xml_path(str(model))
    assert compiled.ngeom > 150
    assert start[:2] == (2.7, -2.1)
    # Colliders participate in physical contacts/rays, decorative shapes do not.
    collider = compiled.geom('entry_door_leaf_collision_0')
    visual = compiled.geom('backpack_body_visual_0')
    assert collider.group == 0 and collider.contype != 0
    assert visual.group == 2 and visual.contype == 0 and visual.conaffinity == 0
    assert compiled.cam_pos[compiled.camera('inspection').id][2] == pytest.approx(.915)
    data = mujoco.MjData(compiled)
    mujoco.mj_forward(compiled, data)
    hit = np.zeros(1, dtype=np.int32)
    distance = mujoco.mj_ray(compiled, data, np.array([2.7,-2.1,.25]),
        np.array([1.,0.,0.]), np.array([1,0,0,0,0,0],dtype=np.uint8), 1, -1, hit)
    assert distance == pytest.approx(1.5)  # Entry shoe cabinet's collision face.


def test_nav2_params_have_no_aliases_and_keep_collision_monitor(tmp_path):
    model, map_path, start = build_scene(tmp_path, 'demo')
    mujoco.MjModel.from_xml_path(str(model))
    params = parameters(map_path, start)
    serialized = yaml.safe_dump(params)
    assert '*id' not in serialized and '&id' not in serialized
    assert params['amcl']['ros__parameters']['base_frame_id'] == 'base_link'
    assert params['amcl']['ros__parameters']['set_initial_pose']
    monitor = params['collision_monitor']['ros__parameters']
    assert monitor['cmd_vel_in_topic'] == 'cmd_vel_smoothed'
    assert monitor['cmd_vel_out_topic'] == 'cmd_vel'
    for name in ('controller_server','behavior_server','velocity_smoother','collision_monitor'):
        assert params[name]['ros__parameters']['use_sim_time']
        assert params[name]['ros__parameters']['enable_stamped_cmd_vel'] is False
