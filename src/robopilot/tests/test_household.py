"""用途：验证家居检查的完整命题证据、反例状态、场景变体和专用地点约束。"""

import json
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from robopilot.targets import VISUAL_TARGETS
from robopilot.toolbox_vision import inspect_toolbox
from robopilot.llm_config import LLMConfig
from robopilot.home_scene import build_home

CONFIG=LLMConfig('deepseek','https://api.deepseek.com/chat/completions','deepseek-flash','test-secret','disabled','high',30)
IMAGE=np.full((240,320,3),100,dtype=np.uint8)


@pytest.mark.parametrize('target', ['backpack_hanging','door_closed','fruit_bowl'])
@pytest.mark.parametrize('complete', [True,False])
def test_positive_requires_complete_condition_evidence(target,complete):
    cues=list(VISUAL_TARGETS[target]['required'])
    if not complete:cues.pop()
    def request(*args,**kwargs):
        return json.dumps({'view_clear':True,'status':'detected','reason':'test evidence','visual_cues':cues})
    result=inspect_toolbox(IMAGE,config=CONFIG,request=request,target=target)
    assert result['status']==('detected' if complete else 'unknown')
    assert result['condition_satisfied'] is (True if complete else None)


@pytest.mark.parametrize('target',['backpack_hanging','door_closed','fruit_bowl'])
def test_clear_negative_is_false_and_blocked_is_unknown(target):
    for clear in [True,False]:
        def request(*args,**kwargs):
            return json.dumps({'view_clear':clear,'status':'not_detected','reason':'test counterexample','visual_cues':[]})
        result=inspect_toolbox(IMAGE,config=CONFIG,request=request,target=target)
        assert result['status']==('not_detected' if clear else 'unknown')
        assert result['condition_satisfied'] is (False if clear else None)


@pytest.mark.parametrize('state',['hanging','floor','absent','occluded'])
def test_backpack_scene_states(tmp_path,state):
    world=ET.Element('world')
    build_home(world,tmp_path,backpack_state=state)
    bag=world.find("model[@name='backpack_body']")
    assert (bag is None)==(state=='absent')
    if bag is not None:
        assert float(bag.findtext('pose').split()[2])==(.23 if state=='floor' else .59)
    assert (world.find("model[@name='backpack_occluder']") is not None)==(state=='occluded')


@pytest.mark.parametrize('state',['closed','open','ajar'])
def test_door_has_real_collision_and_opening(tmp_path,state):
    world=ET.Element('world')
    build_home(world,tmp_path,door_state=state)
    door=world.find("model[@name='entry_door_leaf']")
    assert door.find('link/collision') is not None
    pose=door.findtext('pose').split()
    assert float(pose[1])==(-3.98 if state=='closed' else -3.48 if state=='open' else -3.63)


@pytest.mark.parametrize('state',['present','empty','absent'])
def test_fruit_bowl_counterexamples(tmp_path,state):
    world=ET.Element('world')
    build_home(world,tmp_path,fruit_state=state)
    assert (world.find("model[@name='fruit_bowl']") is not None)==(state!='absent')
    assert (world.find("model[@name='fruit_0']") is not None)==(state=='present')


def test_wrong_room_never_invokes_camera_or_vision(tmp_path):
    from types import SimpleNamespace
    from robopilot.executor import MissionExecutor
    from robopilot.storage import MissionStore
    from robopilot.backends import MockBackend
    class NoCamera(MockBackend):
        def capture_image(self,timeout_s):raise AssertionError('must not inspect wrong room')
    store=MissionStore(tmp_path)
    try:
        mission={'id':'test','observations':[]}
        result=MissionExecutor(NoCamera(),store)._inspect(mission,SimpleNamespace(
            id='test',target='fruit_bowl',place='bedroom',timeout_s=10))
        assert result.status=='FAILED' and mission['observations'][0]['status']=='unknown'
    finally:store.close()


def test_negative_condition_is_reported_separately_from_execution(tmp_path,monkeypatch):
    from robopilot.executor import MissionExecutor
    from robopilot.storage import MissionStore
    from robopilot.backends import MockBackend
    from robopilot.schemas import Pose,parse_plan
    monkeypatch.setattr('robopilot.toolbox_vision.inspect_toolbox',lambda *a,**k:{
        'status':'not_detected','reason':'empty bowl','predicate':'厨房果盘中有水果',
        'condition_satisfied':False,'method':'vlm_predicate_v1'})
    places={'fruit_check':Pose(1,0,0)}
    plan=parse_plan({'version':1,'name':'negative','steps':[
        {'id':'go','action':'navigate','place':'fruit_check'},
        {'id':'look','action':'inspect','place':'fruit_check','target':'fruit_bowl','depends_on':['go']}]},places)
    store=MissionStore(tmp_path)
    try:
        mission=MissionExecutor(MockBackend(),store).run(plan,places)
        assert mission['status']=='SUCCEEDED'
        report=(tmp_path/mission['id']/'report.md').read_text()
        assert '条件满足：否' in report and '不满足 1' in report
    finally:store.close()


def test_kitchen_partition_meets_entry_wall_and_keeps_doorway(tmp_path):
    world=ET.Element('world')
    build_home(world,tmp_path)
    def x_interval(name):
        model=world.find(f"model[@name='{name}']")
        x=float(model.findtext('pose').split()[0])
        sx=float(model.findtext('link/collision/geometry/box/size').split()[0])
        return x-sx/2,x+sx/2
    kitchen=x_interval('kitchen_hall_right')
    entry=x_interval('entry_divider')
    assert kitchen[1]>=entry[0] and kitchen[1]<=entry[1]+1e-6
    assert x_interval('south')[1]>=x_interval('entry_door_jamb_0.55')[0]
    assert x_interval('south_right')[0]<=x_interval('entry_door_jamb_1.65')[1]
    # Same geometry must close the map gap, while retaining the kitchen entrance.
    tokens='\n'.join(l for l in (tmp_path/'home.pgm').read_text().splitlines() if not l.startswith('#')).split()
    width,height=map(int,tokens[1:3]);pixels=list(map(int,tokens[4:]))
    def pixel(x,y):
        col=int((x+5.5)/.05);row=height-1-int((y+4.5)/.05)
        return pixels[row*width+col]
    assert pixel(.1,-1.5)==0
    assert pixel(-2.7,-1.5)==254
