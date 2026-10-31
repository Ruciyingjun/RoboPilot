"""用途：验证图像检查、证据落盘、观测历史、后端隔离和自然语言计划的执行边界。"""

import io
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from robopilot.backends import MockBackend
from robopilot.cli import main
from robopilot.executor import MissionExecutor
from robopilot.perception import detect_red_marker
from robopilot.planner import plan_instruction, plan_with_llm
from robopilot.schemas import Pose, ValidationError, parse_plan
from robopilot.storage import MissionStore

PLACES = {'checkpoint_a': Pose(1., 0., 0.), 'checkpoint_b': Pose(1., 1., 1.57)}


def inspection_plan():
    return plan_instruction('去checkpoint_a检查红色标记；返回起点', PLACES)


@pytest.mark.parametrize('image_mode,status,mission_status', [
    ('red', 'detected', 'SUCCEEDED'), ('empty', 'not_detected', 'SUCCEEDED'),
    ('dark', 'unknown', 'PARTIAL'), ('missing', 'unknown', 'PARTIAL'),
])
def test_inspection_records_evidence_and_observation(tmp_path, image_mode, status, mission_status):
    store = MissionStore(tmp_path)
    try:
        mission = MissionExecutor(MockBackend(images=[image_mode]), store).run(inspection_plan(), PLACES)
        assert mission['status'] == mission_status
        obs = mission['observations'][0]
        assert obs['status'] == status
        assert len(store.history('red_marker', 'mock')) == 1
        assert store.history('red_marker', 'ros') == []
        if image_mode != 'missing':
            evidence = tmp_path / mission['id'] / obs['evidence_path']
            assert cv2.imread(str(evidence)).shape == (240, 320, 3)
            assert obs['stamp_ns'] > 0 and obs['pose']['x'] == 1.
            assert obs['evidence_path'] in (tmp_path / mission['id'] / 'report.md').read_text()
        else:
            assert obs['evidence_path'] is None
    finally:
        store.close()


def test_failed_navigation_skips_inspection_and_records_no_observation(tmp_path):
    store = MissionStore(tmp_path)
    try:
        mission = MissionExecutor(MockBackend(['failed']), store).run(inspection_plan(), PLACES)
        assert mission['steps'][1]['status'] == 'SKIPPED'
        assert not mission['observations']
        assert not store.history('red_marker', 'mock')
    finally:
        store.close()


def test_memory_survives_restart_and_missing_detection_does_not_erase_last_seen(tmp_path):
    store = MissionStore(tmp_path)
    first = MissionExecutor(MockBackend(images=['red']), store).run(inspection_plan(), PLACES)
    MissionExecutor(MockBackend(images=['empty']), store).run(inspection_plan(), PLACES)
    store.close()
    store = MissionStore(tmp_path)
    try:
        assert len(store.history('red_marker', 'mock')) == 2
        assert store.last_seen('red_marker', 'mock')['mission_id'] == first['id']
        plan = plan_instruction('去上次发现红色标记的地方检查红色标记；返回起点',
                                PLACES, store, 'mock')
        assert plan.steps[0].place == 'checkpoint_a'
        with pytest.raises(ValidationError, match='历史观测'):
            plan_instruction('去上次发现红色标记的地方检查红色标记', PLACES, store, 'ros')
    finally:
        store.close()


@pytest.mark.parametrize('clause', ['去unknown检查红色标记', '随便探索', '去checkpoint_a检查工具箱'])
def test_rules_do_not_guess_unsupported_places_or_tasks(clause):
    with pytest.raises(ValidationError):
        plan_instruction(clause, PLACES)


def test_inspection_must_depend_on_the_latest_movement():
    with pytest.raises(ValidationError, match='latest navigation'):
        parse_plan({'version': 1, 'name': 'bad', 'steps': [
            {'id': 'a', 'action': 'navigate', 'place': 'checkpoint_a'},
            {'id': 'b', 'action': 'navigate', 'place': 'checkpoint_b'},
            {'id': 'inspect', 'action': 'inspect', 'place': 'checkpoint_a',
             'target': 'red_marker', 'depends_on': ['a']}]}, PLACES)


def test_small_red_noise_is_not_a_detection():
    image = np.full((240, 320, 3), 100, np.uint8)
    image[20:22, 30:32] = (0, 0, 255)
    assert detect_red_marker(image)['status'] == 'not_detected'


def test_llm_output_is_validated_before_execution(monkeypatch):
    plan = inspection_plan()
    def reply(request, timeout):
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(plan.to_dict())}}]}).encode())
    monkeypatch.setattr('urllib.request.urlopen', reply)
    assert plan_with_llm('巡检', PLACES, 'https://example.invalid/chat/completions', 'test', 'test') == plan
    def bad_reply(request, timeout):
        data = plan.to_dict()
        data['steps'][0]['place'] = 'invented'
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(data)}}]}).encode())
    monkeypatch.setattr('urllib.request.urlopen', bad_reply)
    with pytest.raises(ValidationError, match='unknown place'):
        plan_with_llm('巡检', PLACES, 'https://example.invalid/chat/completions', 'test', 'test')


def test_planning_cli_generates_a_runnable_plan_without_moving_robot(tmp_path):
    places = Path(__file__).parents[1] / 'config/places.example.yaml'
    output = tmp_path / 'plan.json'
    assert main(['plan', '--places', str(places), '--instruction',
                 '先去checkpoint_a检查红色标记，再去checkpoint_b检查红色标记，最后返回起点',
                 '--output', str(output), '--memory', str(tmp_path / 'runs')]) == 0
    assert len(json.loads(output.read_text())['steps']) == 5
    assert main(['run', '--places', str(places), '--plan', str(output),
                 '--output', str(tmp_path / 'runs'), '--mock-images', 'red,empty']) == 0


def test_evaluation_separates_mock_and_does_not_claim_visual_accuracy(tmp_path):
    from robopilot.evaluation import evaluate
    store = MissionStore(tmp_path)
    try:
        MissionExecutor(MockBackend(images=['empty']), store).run(inspection_plan(), PLACES)
    finally:
        store.close()
    result = evaluate(tmp_path, 'mock')
    assert result['finished_missions'] == 1
    assert result['mission_success_rate'] == 1.0
    assert result['inspection_results'] == {'not_detected': 1}
    assert 'visual_accuracy' not in result
    assert evaluate(tmp_path, 'ros')['finished_missions'] == 0
