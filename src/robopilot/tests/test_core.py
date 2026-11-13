"""用途：验证输入校验、任务执行、重试取消、依赖传播及持久记录，无需 Gazebo。"""

import json
import sqlite3

import pytest

from robopilot.backends import MockBackend, NavigationResult
from robopilot.cli import main
from robopilot.executor import MissionExecutor
from robopilot.schemas import Pose, ValidationError, load_inputs, parse_plan, parse_places
from robopilot.storage import MissionStore


PLACES = {'a': Pose(1.0, 2.0, 0.0), 'b': Pose(3.0, 4.0, 1.0)}


def plan_of(*steps):
    return parse_plan({'version': 1, 'name': 'test', 'steps': list(steps)}, PLACES)


def run_plan(tmp_path, plan, backend):
    store = MissionStore(tmp_path)
    try:
        mission = MissionExecutor(backend, store).run(plan, PLACES)
    finally:
        store.close()
    return mission


def test_return_uses_captured_pose_and_persists_evidence_type(tmp_path):
    start = Pose(8.0, 9.0, 1.2)
    backend = MockBackend(start=start)
    mission = run_plan(tmp_path, plan_of(
        {'id': 'a', 'action': 'navigate', 'place': 'a'},
        {'id': 'home', 'action': 'return_to_start'}), backend)
    assert backend.visited == [PLACES['a'], start]
    assert mission['status'] == 'SUCCEEDED'
    saved = json.loads((tmp_path / mission['id'] / 'mission.json').read_text())
    assert saved == mission
    with sqlite3.connect(tmp_path / 'robopilot.sqlite3') as db:
        assert db.execute('SELECT status FROM missions').fetchone() == ('SUCCEEDED',)
        assert db.execute('SELECT COUNT(*) FROM steps').fetchone() == (2,)
    report = (tmp_path / mission['id'] / 'report.md').read_text()
    assert 'MOCK' in report and '未进行视觉检查' in report


def test_retry_budget_then_continue(tmp_path):
    backend = MockBackend(['failed', 'timeout', 'succeeded'])
    mission = run_plan(tmp_path, plan_of(
        {'id': 'a', 'action': 'navigate', 'place': 'a', 'max_retries': 1},
        {'id': 'b', 'action': 'navigate', 'place': 'b'}), backend)
    assert mission['status'] == 'PARTIAL'
    assert len(mission['steps'][0]['attempts']) == 2
    assert backend.visited == [PLACES['a'], PLACES['a'], PLACES['b']]


def test_dependency_failure_skips_only_dependent_steps(tmp_path):
    backend = MockBackend(['failed'])
    mission = run_plan(tmp_path, plan_of(
        {'id': 'a', 'action': 'navigate', 'place': 'a'},
        {'id': 'b', 'action': 'navigate', 'place': 'b', 'depends_on': ['a']},
        {'id': 'home', 'action': 'return_to_start'}), backend)
    assert [s['status'] for s in mission['steps']] == ['FAILED', 'SKIPPED', 'SUCCEEDED']
    assert len(backend.visited) == 2


@pytest.mark.parametrize('outcome,policy', [('failed', 'abort'), ('unsafe', 'continue')])
def test_abort_and_unconfirmed_cancel_stop_future_goals(tmp_path, outcome, policy):
    backend = MockBackend([outcome])
    mission = run_plan(tmp_path, plan_of(
        {'id': 'a', 'action': 'navigate', 'place': 'a', 'on_failure': policy},
        {'id': 'b', 'action': 'navigate', 'place': 'b'}), backend)
    assert mission['status'] == 'FAILED'
    assert mission['steps'][1]['status'] == 'SKIPPED'
    assert len(backend.visited) == 1


def test_unconfirmed_cancel_never_retries(tmp_path):
    backend = MockBackend(['unsafe'])
    mission = run_plan(tmp_path, plan_of(
        {'id': 'a', 'action': 'navigate', 'place': 'a', 'max_retries': 2}), backend)
    assert len(backend.visited) == 1
    assert '无法确认' in mission['error']


def test_keyboard_interrupt_cancels_and_persists(tmp_path):
    backend = MockBackend(['interrupt'])
    mission = run_plan(tmp_path, plan_of(
        {'id': 'a', 'action': 'navigate', 'place': 'a'},
        {'id': 'b', 'action': 'navigate', 'place': 'b'}), backend)
    assert backend.cancel_called
    assert mission['status'] == 'CANCELED'
    assert [s['status'] for s in mission['steps']] == ['CANCELED', 'SKIPPED']
    assert mission['steps'][0]['attempts'][0]['result']['code'] == 'INTERRUPTED'


def test_external_cancellation_does_not_retry(tmp_path):
    class CanceledBackend(MockBackend):
        def navigate(self, pose, timeout_s):
            self.visited.append(pose)
            return NavigationResult('CANCELED')
    backend = CanceledBackend()
    mission = run_plan(tmp_path, plan_of(
        {'id': 'a', 'action': 'navigate', 'place': 'a', 'max_retries': 2},
        {'id': 'b', 'action': 'navigate', 'place': 'b'}), backend)
    assert mission['status'] == 'CANCELED'
    assert len(backend.visited) == 1
    assert mission['steps'][1]['status'] == 'SKIPPED'


def test_startup_failure_never_navigates(tmp_path):
    class UnreadyBackend(MockBackend):
        def prepare(self, timeout_s):
            raise TimeoutError('no localization')
    backend = UnreadyBackend()
    mission = run_plan(tmp_path, plan_of({'id': 'a', 'action': 'navigate', 'place': 'a'}), backend)
    assert mission['status'] == 'FAILED'
    assert not backend.visited
    assert mission['steps'][0]['status'] == 'SKIPPED'
    assert 'no localization' in mission['error']


@pytest.mark.parametrize('entry', [
    {'id': 'a', 'action': 'navigate', 'place': 'unknown'},
    {'id': 'a', 'action': 'inspect', 'place': 'a'},
    {'id': 'a', 'action': 'return_to_start', 'place': 'a'},
    {'id': 'a', 'action': 'navigate', 'place': 'a', 'timeout_s': float('nan')},
    {'id': 'a', 'action': 'navigate', 'place': 'a', 'timeout_s': True},
    {'id': 'a', 'action': 'navigate', 'place': 'a', 'max_retries': -1},
    {'id': 'a', 'action': 'navigate', 'place': 'a', 'max_retries': True},
    {'id': 'a', 'action': 'navigate', 'place': 'a', 'depends_on': ['later']},
    {'id': 'a', 'action': 'navigate', 'place': 'a', 'velocity': 10},
])
def test_invalid_plan_is_rejected(entry):
    with pytest.raises(ValidationError):
        plan_of(entry)


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValidationError):
        plan_of(*[{'id': 'a', 'action': 'navigate', 'place': 'a'}] * 2)


def test_nonfinite_coordinates_are_rejected():
    with pytest.raises(ValidationError):
        parse_places({'version': 1, 'frame_id': 'map', 'places': {
            'a': {'x': float('inf'), 'y': 0, 'yaw': 0}}})


def test_duplicate_json_keys_are_rejected(tmp_path):
    places = tmp_path / 'places.yaml'
    places.write_text('version: 1\nframe_id: map\nplaces:\n  a: {x: 0, y: 0, yaw: 0}\n')
    plan = tmp_path / 'plan.json'
    plan.write_text('{"version": 1, "version": 2}')
    with pytest.raises(ValidationError, match='duplicate JSON key'):
        load_inputs(places, plan)


def test_saved_plan_can_be_validated_again():
    plan = plan_of({'id': 'a', 'action': 'navigate', 'place': 'a'},
                   {'id': 'home', 'action': 'return_to_start', 'depends_on': ['a']})
    assert parse_plan(json.loads(json.dumps(plan.to_dict())), PLACES) == plan


@pytest.mark.parametrize('contents', [
    'version: 1\nframe_id: map\nplaces:\n  a: {x: 1, x: 5, y: 0, yaw: 0}\n',
    'version: 1\nframe_id: map\nplaces:\n  a: {x: 1, y: 0, yaw: 0}\n  a: {x: 5, y: 0, yaw: 0}\n',
])
def test_duplicate_yaml_keys_cannot_silently_change_destination(tmp_path, contents):
    places = tmp_path / 'places.yaml'
    places.write_text(contents)
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(plan_of({'id': 'a', 'action': 'navigate', 'place': 'a'}).to_dict()))
    with pytest.raises(ValidationError, match='duplicate YAML key'):
        load_inputs(places, plan)


def test_coordinate_overflow_is_validation_error():
    with pytest.raises(ValidationError):
        parse_places({'version': 1, 'frame_id': 'map', 'places': {
            'a': {'x': 10 ** 400, 'y': 0, 'yaw': 0}}})


def test_cli_validation_failure_has_no_run_artifacts(tmp_path):
    result = main(['run', '--places', str(tmp_path / 'missing.yaml'),
                   '--plan', str(tmp_path / 'missing.json'), '--output', str(tmp_path / 'runs')])
    assert result == 2
    assert not (tmp_path / 'runs').exists()
