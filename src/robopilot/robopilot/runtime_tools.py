"""Allowlisted robot tools, argument validation and independent completion review."""
from dataclasses import asdict
import math
from pathlib import Path
import time

from .schemas import Pose, ValidationError


TOOLS = {
    'navigate_to': 'Navigate to the place in a pending navigate step. Retry on recoverable failure.',
    'revisit': 'Revisit a completed navigation step to repair observation pose after drift or recovery.',
    'inspect_target': 'Capture fresh evidence and inspect the target in an inspect step.',
    'return_to_start': 'Navigate to the captured mission start pose for a return step.',
    'capture_image': 'Capture an extra fresh image at the current pose, without completing a step.',
    'observe': 'Read current localized robot pose.',
    'query_memory': 'Read historical clues; they never complete live inspection requirements.',
    'finish_task': 'Submit the run to independent review. No success is asserted by this tool.',
}
TOOL_SCHEMA = {'type':'object', 'additionalProperties':False, 'required':['action','step'],
    'properties': {'action':{'type':'string','enum':list(TOOLS)},
                   'step':{'type':'string','description':'Plan step ID, or empty for auxiliary tools'}}}
MOVEMENTS = {'navigate_to', 'return_to_start', 'revisit'}


def near(actual, expected):
    return (math.hypot(actual['x']-expected['x'], actual['y']-expected['y']) <= .35
            and abs(math.atan2(math.sin(actual['yaw']-expected['yaw']),
                               math.cos(actual['yaw']-expected['yaw']))) <= .35)


class RobotTools:
    def __init__(self, executor, plan, places):
        self.executor, self.backend = executor, executor.backend
        self.plan = {step.id:step for step in plan.steps}
        self.places = places

    def validate(self, call, context):
        if not isinstance(call, dict) or set(call) != {'action','step'}:
            raise ValidationError('Expected exactly action and step')
        action, step_id = call['action'], call['step']
        if not isinstance(action, str) or action not in TOOLS or not isinstance(step_id, str):
            raise ValidationError('Unknown tool or invalid step ID')
        expected = {'navigate_to':'navigate','inspect_target':'inspect','return_to_start':'return_to_start'}
        if action == 'revisit':
            step = self.plan.get(step_id)
            record = next((r for r in context['mission']['steps'] if r['id']==step_id), {})
            if step is None or step.action!='navigate' or record.get('status')!='SUCCEEDED':
                raise ValidationError('Revisit requires a completed approved navigation step')
            previous = [c for c in context['calls'] if c['call']==call and c['status']=='COMPLETED']
            if len(previous) >= 2:
                raise ValidationError('Revisit budget exhausted')
            return None
        if action not in expected:
            if step_id:
                raise ValidationError('Auxiliary tools require an empty step')
            return None
        step = self.plan.get(step_id)
        if step is None or step.action != expected[action]:
            raise ValidationError('Tool does not match an approved plan step')
        records = {r['id']:r for r in context['mission']['steps']}
        record = records[step_id]
        if record['status'] == 'SUCCEEDED':
            raise ValidationError('Completed steps cannot be replayed')
        if any(records[d]['status'] != 'SUCCEEDED' for d in step.depends_on):
            raise ValidationError('Step dependencies are incomplete')
        if len(record['attempts']) >= step.max_retries+1:
            raise ValidationError('Step attempt budget exhausted')
        return step

    def execute(self, call, context, timeout, goal_id):
        from .planning_context import digest
        action = call['action']
        mission = context['mission']
        if action == 'finish_task':
            return {'status':'submitted_for_review'}
        if action == 'observe':
            return {'status':'ok','pose':asdict(self.backend.runtime_pose(timeout))}
        if action == 'query_memory':
            targets = sorted({s.target for s in self.plan.values() if s.target})
            return {'status':'ok','memory':{target:self.executor.store.assess_memory(
                target, self.backend.name, digest(mission['places']), mission_id=mission['id'])
                for target in targets}}
        if action == 'capture_image':
            from .perception import save_evidence, detect_red_marker
            frame = self.backend.capture_image(timeout)
            path = 'evidence/'+goal_id+'.png'
            save_evidence(self.executor.store.root/mission['id']/path, frame, detect_red_marker(frame.image))
            return {'status':'captured','evidence_path':path,'pose':frame.pose,'stamp_ns':frame.stamp_ns,
                    'note':'Extra capture is not a target inspection'}
        step = self.plan[call['step']]
        if action == 'inspect_target':
            deadline = time.monotonic()+timeout
            pose = asdict(self.backend.runtime_pose(timeout))
            if not near(pose, asdict(self.places[step.place])):
                return {'status':'FAILED','code':'WRONG_OBSERVATION_POSE',
                        'message':'Robot must be at the approved inspection pose','safe_to_continue':True}
            # Use the single remaining wall-time budget for localization plus inspection.
            from types import SimpleNamespace
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Inspection localization used its time budget')
            result = self.executor._inspect(mission, SimpleNamespace(
                id=step.id, place=step.place, target=step.target, timeout_s=remaining))
            return {**asdict(result), 'observation':mission['observations'][-1]}
        target = Pose(**mission['start_pose']) if action == 'return_to_start' else self.places[step.place]
        return asdict(self.backend.navigate(target, timeout, goal_id=goal_id))

    def review(self, context, timeout):
        mission = context['mission']
        issues = []
        for record in mission['steps']:
            if record['status'] != 'SUCCEEDED':
                issues.append({'step':record['id'],'reason':'Step not completed'})
            elif record['action'] == 'inspect':
                observations = [o for o in mission['observations'] if o['step_id'] == record['id']]
                latest = observations[-1] if observations else {}
                path = latest.get('evidence_path')
                if (latest.get('status') not in ('detected','not_detected') or not path
                        or latest.get('mission_id') != mission['id']
                        or latest.get('target') != record['target']
                        or latest.get('place') != record['place']
                        or not latest.get('stamp_ns') or not latest.get('pose')
                        or not (self.executor.store.root/mission['id']/Path(path)).is_file()):
                    issues.append({'step':record['id'],'reason':'Valid live inspection evidence missing'})
        if any(s.action == 'return_to_start' for s in self.plan.values()):
            actual = asdict(self.backend.runtime_pose(timeout))
            if not near(actual, mission['start_pose']):
                issues.append({'step':next(s.id for s in reversed(list(self.plan.values()))
                    if s.action == 'return_to_start'), 'reason':'Robot is not at the mission start pose'})
        return {'accepted':not issues, 'issues':issues}
