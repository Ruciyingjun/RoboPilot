"""用途：验证工具箱视觉结果校验、服务故障不兜底颜色、目标隔离及场景变体。"""

import json

import numpy as np
import pytest

from robopilot.llm_config import LLMConfig
from robopilot.llm_client import LLMError
from robopilot.toolbox_vision import inspect_toolbox
from robopilot.home_scene import build_home
import xml.etree.ElementTree as ET

CONFIG=LLMConfig('deepseek','https://api.deepseek.com/chat/completions','deepseek-flash','test-secret','enabled','high',30)
IMAGE=np.full((240,320,3),100,dtype=np.uint8)


def fake(result, calls):
    def request(*args,**kwargs):
        calls.append((args,kwargs))
        return json.dumps({'view_clear':True,**result})
    return request


@pytest.mark.parametrize('status,cues,expected',[
    ('detected',['handle','lid'],'detected'),
    ('detected',['rigid_container'],'unknown'),
    ('not_detected',[],'not_detected'),
    ('unknown',[],'unknown')])
def test_shape_evidence_and_image_payload(status,cues,expected):
    calls=[]
    result=inspect_toolbox(IMAGE,config=CONFIG,request=fake(
        {'status':status,'reason':'visible evidence','visual_cues':cues},calls))
    assert result['status']==expected
    blocks=calls[0][0][3][0]['content']
    assert blocks[1]['image_url']['url'].startswith('data:image/png;base64,')
    assert calls[0][1]['thinking']=='disabled'
    assert 'test-secret' not in json.dumps(result)


@pytest.mark.parametrize('raw',[
    {'status':'detected','reason':'x','visual_cues':['handle','lid'],'extra':'bad'},
    {'status':'detected','reason':'x','visual_cues':['red','box']},
    {'status':'fake','reason':'x','visual_cues':[]},
])
def test_malformed_model_output_is_unknown(raw):
    assert inspect_toolbox(IMAGE,config=CONFIG,request=fake(raw,[]))['status']=='unknown'


def test_network_failure_never_becomes_red_detection():
    red=IMAGE.copy();red[50:150,50:200]=(0,0,255)
    def fail(*args,**kwargs):raise LLMError('HTTP failure')
    assert inspect_toolbox(red,config=CONFIG,request=fail)['status']=='unknown'


def test_dark_frame_does_not_make_paid_request():
    calls=[]
    result=inspect_toolbox(np.zeros_like(IMAGE),config=CONFIG,request=fake({},calls))
    assert result['status']=='unknown' and not calls


@pytest.mark.parametrize('state,box_expected,plain_expected',[
    ('present',True,False),('absent',False,False),('distractor',False,True),('occluded',True,False)])
def test_scene_target_variants(tmp_path,state,box_expected,plain_expected):
    world=ET.Element('world',name='default')
    build_home(world,tmp_path,state)
    assert (world.find("model[@name='toolbox_body']") is not None)==box_expected
    assert (world.find("model[@name='plain_red_box']") is not None)==plain_expected
    assert (world.find("model[@name='inspection_occluder']") is not None)==(state=='occluded')
    if not box_expected:
        assert not any(m.get('name','').startswith(('handle_post_','toolbox_')) for m in world.findall('model'))


def test_blocked_view_overrides_model_absence():
    result=inspect_toolbox(IMAGE,config=CONFIG,request=fake(
        {'view_clear':False,'status':'not_detected','reason':'panel blocks view','visual_cues':[]},[]))
    assert result['status']=='unknown'


def test_static_execution_preserves_semantic_target_and_method(tmp_path,monkeypatch):
    from robopilot.schemas import Pose,parse_plan
    from robopilot.backends import MockBackend
    from robopilot.executor import MissionExecutor
    from robopilot.storage import MissionStore
    monkeypatch.setattr('robopilot.toolbox_vision.inspect_toolbox',lambda image,timeout_s,**kwargs:
        {'status':'detected','reason':'test semantic service','method':'vlm_toolbox_v1',
         'model':'test-double','visual_cues':['handle','lid']})
    places={'a':Pose(1,0,0)}
    plan=parse_plan({'version':1,'name':'semantic_test','steps':[
        {'id':'go','action':'navigate','place':'a'},
        {'id':'look','action':'inspect','place':'a','target':'toolbox','depends_on':['go']}]},places)
    store=MissionStore(tmp_path)
    try:
        result=MissionExecutor(MockBackend(images=['empty']),store).run(plan,places)
        assert result['status']=='SUCCEEDED'
        assert result['observations'][0]['target']=='toolbox'
        assert store.last_seen('red_marker','mock') is None
        assert store.last_seen('toolbox','mock')['method']=='vlm_toolbox_v1'
        assert 'test-double' in (tmp_path/result['id']/'report.md').read_text()
    finally:store.close()


def test_missing_vision_config_does_not_fall_back_to_color(tmp_path):
    from robopilot.schemas import Pose,parse_plan
    from robopilot.backends import MockBackend
    from robopilot.executor import MissionExecutor
    from robopilot.storage import MissionStore
    places={'a':Pose(1,0,0)}
    plan=parse_plan({'version':1,'name':'no_config','steps':[
        {'id':'go','action':'navigate','place':'a'},
        {'id':'look','action':'inspect','place':'a','target':'toolbox','depends_on':['go']}]},places)
    store=MissionStore(tmp_path)
    try:
        result=MissionExecutor(MockBackend(images=['red']),store).run(plan,places)
        assert result['observations'][0]['status']=='unknown'
    finally:store.close()


def test_missing_config_directly_returns_unknown():
    calls=[]
    result=inspect_toolbox(IMAGE,request=fake({},calls))
    assert result['status']=='unknown' and not calls


@pytest.mark.parametrize('timeout',[0,-1,float('nan'),float('inf')])
def test_invalid_budget_never_uploads(timeout):
    calls=[]
    assert inspect_toolbox(IMAGE,timeout,config=CONFIG,request=fake({},calls))['status']=='unknown'
    assert not calls


def test_unverified_provider_is_unknown_without_upload():
    calls=[]
    config=LLMConfig('generic','https://example.invalid','text-only','test-secret',None,None,30)
    assert inspect_toolbox(IMAGE,config=config,request=fake({},calls))['status']=='unknown'
    assert not calls


def test_image_processing_time_counts_toward_budget(monkeypatch):
    calls=[]
    ticks=iter([0,2,2])
    monkeypatch.setattr('robopilot.toolbox_vision.time.monotonic',lambda:next(ticks))
    assert inspect_toolbox(IMAGE,1,config=CONFIG,request=fake({},calls))['status']=='unknown'
    assert not calls


def test_head_camera_pitch_matches_sdf_and_tf():
    from robopilot.service_robot import configure_robot
    root=ET.fromstring('<sdf version="1.6"><model name="test"><link name="base_link"/></model></sdf>')
    description=ET.fromstring(configure_robot(root,'<robot name="test"><link name="base_link"/></robot>'))
    pose=root.findtext("model/link/sensor[@name='robopilot_rgb']/pose").split()
    joint=description.find("joint[@name='robopilot_camera_link_joint']/origin")
    assert float(pose[4])==pytest.approx(.55)
    assert joint.get('xyz').split()==pose[:3]
    assert joint.get('rpy').split()==pose[3:]
