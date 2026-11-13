"""用途：验证任务清单、完整中文解析、拒绝省略未知要求和预览取消不移动机器人。"""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from robopilot.task_catalog import select_tasks,catalog_plan,run_interactive
from robopilot.schemas import ValidationError,load_inputs


@pytest.mark.parametrize('text,expected',[
    ('2,3,4',[1,2,3]),
    ('请帮我检查背包是否挂在墙上、门是否关闭、果盘是否在厨房',[1,2,3]),
    ('先检查门是否关闭，然后检查客厅工具箱是否存在，最后返回起点',[2,0]),
    ('检查客厅红色标记是否存在',[4]),
])
def test_complete_supported_requests(text,expected):
    assert select_tasks(text)==expected


@pytest.mark.parametrize('text',[
    '检查门是否关闭，然后打开门','检查背包是否挂在墙上和猫在不在',
    '如果门开着就检查果盘','不要检查门是否关闭','2,2','6','2,,3','检查厨房工具箱',
])
def test_unknown_or_conflicting_requirement_never_silently_dropped(text):
    with pytest.raises(ValidationError):select_tasks(text)


def test_plan_preserves_selection_order_and_return():
    places,_=load_inputs(Path(__file__).parents[1]/'config/places.home.yaml')
    plan,selected=catalog_plan('4,2',places)
    assert selected==[3,1]
    assert [s.target for s in plan.steps if s.action=='inspect']==['fruit_bowl','backpack_hanging']
    assert plan.steps[-1].action=='return_to_start'


@pytest.mark.parametrize('preview',[True,False])
def test_preview_and_declined_confirmation_never_construct_backend(tmp_path,monkeypatch,preview):
    def forbidden(*a,**k):raise AssertionError('robot must not be constructed')
    monkeypatch.setitem(sys.modules,'robopilot.ros_adapter',SimpleNamespace(RosNavigationBackend=forbidden))
    monkeypatch.setattr('builtins.input',lambda prompt:'n')
    args=SimpleNamespace(list_only=False,instruction='2,3,4',preview=preview,backend='ros',
        places=Path(__file__).parents[1]/'config/places.home.yaml',output=tmp_path/'unused')
    assert run_interactive(args)==0
    assert not args.output.exists()


def test_failed_return_prints_specific_step_and_code(tmp_path,monkeypatch,capsys):
    from robopilot.backends import MockBackend
    backend=MockBackend(outcomes=['succeeded','failed'])
    monkeypatch.setattr('robopilot.backends.MockBackend',lambda:backend)
    monkeypatch.setattr('builtins.input',lambda prompt:'y')
    args=SimpleNamespace(list_only=False,instruction='5',preview=False,backend='mock',
        places=Path(__file__).parents[1]/'config/places.home.yaml',output=tmp_path)
    assert run_interactive(args)==1
    output=capsys.readouterr().out
    assert '未完成步骤：return' in output and 'MOCK_UNREACHABLE' in output
