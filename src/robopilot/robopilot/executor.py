"""用途：顺序执行任务，管理起点、依赖、有限重试、取消及状态记录。"""

import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from .backends import NavigationResult
from .planning_context import digest


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class MissionExecutor:
    def __init__(self, backend, store, startup_timeout=30.0, on_event=None):
        self.backend = backend
        self.store = store
        self.startup_timeout = startup_timeout
        self.on_event = on_event or (lambda message: None)

    def _save(self, mission):
        mission['updated_at'] = utc_now()
        self.store.save(mission)

    def run(self, plan, places, planning=None):
        mission = {
            'id': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12],
            'name': plan.name, 'backend': self.backend.name, 'status': 'PENDING',
            'created_at': utc_now(), 'finished_at': None, 'start_pose': None,
            'plan': plan.to_dict(), 'places': {name: asdict(pose) for name, pose in places.items()},
            'planning': planning or {'planner': 'json_file'},
            'error': '', 'observations': [], 'steps': [dict(step.to_dict(), status='PENDING', attempts=[], message='')
                                  for step in plan.steps],
        }
        current = None
        self._save(mission)
        try:
            mission['status'] = 'RUNNING'
            self._save(mission)
            self.on_event('等待导航就绪并记录任务起点…')
            start = self.backend.prepare(self.startup_timeout)
            mission['start_pose'] = asdict(start)
            self._save(mission)
            states = {}
            aborted = False
            for step, record in zip(plan.steps, mission['steps']):
                current = record
                if aborted or any(states[d] != 'SUCCEEDED' for d in step.depends_on):
                    record.update(status='SKIPPED', message='前序任务中止或依赖步骤未成功')
                else:
                    pose = places[step.place] if step.action in ('navigate', 'inspect') else start
                    record['target_pose'] = asdict(pose)
                    record['status'] = 'RUNNING'
                    for attempt in range(step.max_retries + 1):
                        entry = {'number': attempt + 1, 'started_at': utc_now(), 'result': None}
                        record['attempts'].append(entry)
                        self._save(mission)
                        self.on_event(f'{step.id}: {step.action}, 尝试 {attempt + 1}')
                        started = time.monotonic()
                        result = (self._inspect(mission, step) if step.action == 'inspect'
                                  else self.backend.navigate(pose, step.timeout_s))
                        entry.update(result=asdict(result), finished_at=utc_now(),
                                     duration_s=round(time.monotonic() - started, 3))
                        record.update(status=result.status, message=result.message)
                        self._save(mission)
                        if not result.safe_to_continue:
                            aborted = True
                            mission['error'] = '无法确认前一导航目标已终止，停止发送后续目标。'
                            break
                        if result.status == 'SUCCEEDED':
                            break
                        if result.status == 'CANCELED':
                            # An external action cancellation must not trigger a retry.
                            mission['status'] = 'CANCELED'
                            aborted = True
                            break
                        if attempt < step.max_retries:
                            record['status'] = 'RUNNING'
                    if record['status'] != 'SUCCEEDED' and step.on_failure == 'abort':
                        aborted = True
                states[step.id] = record['status']
                self._save(mission)
            if mission['status'] != 'CANCELED':
                succeeded = sum(s['status'] == 'SUCCEEDED' for s in mission['steps'])
                mission['status'] = ('SUCCEEDED' if succeeded == len(plan.steps)
                                     else 'PARTIAL' if succeeded else 'FAILED')
        except KeyboardInterrupt:
            confirmed = self._cancel()
            mission['status'] = 'CANCELED'
            mission['error'] = '用户取消任务。' + ('' if confirmed else '导航取消未确认，请检查机器人状态。')
            if current and current['status'] == 'RUNNING':
                current.update(status='CANCELED', message=mission['error'])
        except Exception as exc:
            confirmed = self._cancel()
            mission['status'] = 'FAILED'
            mission['error'] = f'{type(exc).__name__}: {exc}'
            if not confirmed:
                mission['error'] += '；导航取消未确认，请检查机器人状态。'
            if current and current['status'] == 'RUNNING':
                current.update(status='FAILED', message=mission['error'])
        finally:
            for record in mission['steps']:
                if record['status'] == 'PENDING':
                    record.update(status='SKIPPED', message='任务提前结束')
                for attempt in record['attempts']:
                    if attempt['result'] is None:
                        attempt.update(finished_at=utc_now(), result={
                            'status': record['status'], 'code': 'INTERRUPTED',
                            'message': record['message'], 'safe_to_continue': False,
                            'feedback': {},
                        })
            mission['finished_at'] = utc_now()
            self._save(mission)
        return mission

    def _inspect(self, mission, step):
        from .perception import detect_red_marker, save_evidence
        observation = {'id': uuid.uuid4().hex, 'mission_id': mission['id'], 'step_id': step.id,
                       'place': step.place, 'target': step.target, 'backend': self.backend.name,
                       'observed_at': utc_now(), 'status': 'unknown', 'evidence_path': None,
                       'context_id': digest(mission['places']) if mission.get('places') else None}
        try:
            from .targets import VISUAL_TARGETS
            definition = VISUAL_TARGETS.get(step.target)
            if definition and step.place != definition['place']:
                raise ValueError('该关系/状态检查需在已配置的专用观察点执行')
            deadline = time.monotonic()+step.timeout_s
            frame = self.backend.capture_image(step.timeout_s)
            if step.target != 'red_marker':
                from .toolbox_vision import inspect_toolbox
                remaining=deadline-time.monotonic()
                if remaining<=0: raise TimeoutError('检查预算已耗尽')
                result = inspect_toolbox(frame.image,remaining,target=step.target)
            else:
                result = detect_red_marker(frame.image)
            relative = 'evidence/' + observation['id'] + '.png'
            save_evidence(self.store.root / mission['id'] / relative, frame, result)
            observation.update(result, evidence_path=relative, stamp_ns=frame.stamp_ns,
                               frame_id=frame.frame_id, pose=frame.pose, observed_at=utc_now())
        except (TimeoutError, ValueError) as exc:
            observation['reason'] = str(exc)
        from .memory_validity import assess_memory
        observation['memory_validity'] = assess_memory([observation], target=step.target,
            backend=self.backend.name, context_id=observation['context_id'],
            mission_id=mission['id'], place=step.place)
        mission['observations'].append(observation)
        status = 'FAILED' if observation['status'] == 'unknown' else 'SUCCEEDED'
        return NavigationResult(status, 'INSPECTION_' + observation['status'].upper(),
                                observation.get('reason', ''))

    def _cancel(self):
        try:
            return self.backend.cancel()
        except (Exception, KeyboardInterrupt):
            return False
