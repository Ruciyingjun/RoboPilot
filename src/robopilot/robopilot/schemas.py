"""用途：定义位姿与任务数据结构，严格校验 JSON 计划和 YAML 地点配置。"""

import json
from .targets import TARGETS
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


class ValidationError(ValueError):
    pass


def _object(value, allowed, required, label):
    if not isinstance(value, dict):
        raise ValidationError(f'{label}: expected an object')
    unknown = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unknown or missing:
        raise ValidationError(f'{label}: unknown fields {unknown}; missing fields {missing}')


def _name(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value):
        raise ValidationError(f'{label}: use 1–64 ASCII letters, digits, underscores or hyphens')
    return value


def _number(value, label, lower=None, upper=None):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValidationError(f'{label}: expected a finite number')
    if lower is not None and value < lower or upper is not None and value > upper:
        raise ValidationError(f'{label}: expected a value between {lower} and {upper}')
    return float(value)


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    yaw: float
    frame_id: str = 'map'


@dataclass(frozen=True)
class Step:
    id: str
    action: str
    place: str | None = None
    timeout_s: float = 120.0
    max_retries: int = 0
    on_failure: str = 'continue'
    depends_on: tuple[str, ...] = ()
    target: str | None = None

    def to_dict(self):
        data = dict(asdict(self), depends_on=list(self.depends_on))
        if self.action == 'return_to_start':
            data.pop('place')
        if self.target is None:
            data.pop('target')
        return data


@dataclass(frozen=True)
class Plan:
    name: str
    steps: tuple[Step, ...]
    version: int = 1

    def to_dict(self):
        return {'version': self.version, 'name': self.name,
                'steps': [step.to_dict() for step in self.steps]}


def parse_places(data):
    _object(data, {'version', 'frame_id', 'places'}, {'version', 'frame_id', 'places'}, 'places')
    if type(data['version']) is not int or data['version'] != 1:
        raise ValidationError('places.version: only version 1 is supported')
    if data['frame_id'] != 'map':
        raise ValidationError('places.frame_id: initial implementation requires map')
    entries = data['places']
    if not isinstance(entries, dict) or not entries:
        raise ValidationError('places: at least one named pose is required')
    places = {}
    for name, entry in entries.items():
        _name(name, 'place name')
        _object(entry, {'x', 'y', 'yaw'}, {'x', 'y', 'yaw'}, name)
        places[name] = Pose(**{key: _number(entry[key], f'{name}.{key}') for key in entry})
    return places


def parse_plan(data, places):
    _object(data, {'$comment', 'version', 'name', 'steps'}, {'version', 'name', 'steps'}, 'plan')
    if '$comment' in data and not isinstance(data['$comment'], str):
        raise ValidationError('plan.$comment: expected a string')
    if type(data['version']) is not int or data['version'] != 1:
        raise ValidationError('plan.version: only version 1 is supported')
    name = _name(data['name'], 'plan.name')
    if not isinstance(data['steps'], list) or not 1 <= len(data['steps']) <= 32:
        raise ValidationError('plan.steps: expected 1–32 steps')
    steps, seen = [], set()
    for entry in data['steps']:
        _object(entry, {'id', 'action', 'place', 'target', 'timeout_s', 'max_retries', 'on_failure', 'depends_on'},
                {'id', 'action'}, 'step')
        step_id = _name(entry['id'], 'step.id')
        if step_id in seen:
            raise ValidationError(f'duplicate step id: {step_id}')
        action = entry['action']
        if action not in ('navigate', 'return_to_start', 'inspect'):
            raise ValidationError(f'{step_id}: unsupported action {action!r}')
        place = entry.get('place')
        if action in ('navigate', 'inspect'):
            if not isinstance(place, str) or place not in places:
                raise ValidationError(f'{step_id}: unknown place {place!r}')
        elif 'place' in entry:
            raise ValidationError(f'{step_id}: return_to_start does not accept place')
        retries = entry.get('max_retries', 0)
        if type(retries) is not int or not 0 <= retries <= 2:
            raise ValidationError(f'{step_id}: max_retries must be an integer from 0 to 2')
        policy = entry.get('on_failure', 'continue')
        if policy not in ('continue', 'abort'):
            raise ValidationError(f'{step_id}: on_failure must be continue or abort')
        dependencies = entry.get('depends_on', [])
        if (not isinstance(dependencies, list)
                or any(not isinstance(d, str) or d not in seen for d in dependencies)
                or len(set(dependencies)) != len(dependencies)):
            raise ValidationError(f'{step_id}: depends_on must contain unique earlier step IDs')
        target = entry.get('target')
        if action == 'inspect':
            if target not in TARGETS:
                raise ValidationError(f'{step_id}: unsupported inspection target')
            previous_move = next((s for s in reversed(steps)
                                  if s.action in ('navigate', 'return_to_start')), None)
            if (previous_move is None or previous_move.action != 'navigate'
                    or previous_move.place != place or previous_move.id not in dependencies):
                raise ValidationError(f'{step_id}: inspect must depend on the latest navigation to its place')
        elif 'target' in entry:
            raise ValidationError(f'{step_id}: target is only allowed for inspect')
        timeout = _number(entry.get('timeout_s', 120), f'{step_id}.timeout_s', 0.1, 600)
        steps.append(Step(step_id, action, place, timeout, retries, policy, tuple(dependencies), target))
        seen.add(step_id)
    return Plan(name, tuple(steps))


def decode_json(text):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValidationError(str(exc)) from exc


def load_yaml(path):
    try:
        class UniqueSafeLoader(yaml.SafeLoader):
            def construct_mapping(self, node, deep=False):
                result = {}
                for key_node, value_node in node.value:
                    key = self.construct_object(key_node, deep=deep)
                    if not isinstance(key, str):
                        raise ValidationError('YAML keys must be strings')
                    if key in result:
                        raise ValidationError(f'duplicate YAML key: {key}')
                    result[key] = self.construct_object(value_node, deep=deep)
                return result

        return yaml.load(Path(path).read_text(encoding='utf-8'), Loader=UniqueSafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValidationError(str(exc)) from exc


def load_inputs(places_path, plan_path=None):
    try:
        places = parse_places(load_yaml(places_path))
        plan = (parse_plan(decode_json(Path(plan_path).read_text(encoding='utf-8')), places)
                if plan_path is not None else None)
        return places, plan
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ValidationError(str(exc)) from exc
