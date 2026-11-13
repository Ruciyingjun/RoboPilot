"""用途：解析校验/执行命令，选择 mock 或 ROS 后端，输出任务结果与报告路径。"""

import argparse
import json
from .targets import TARGETS
import math
import sys
import uuid
from pathlib import Path

from .backends import MockBackend
from .executor import MissionExecutor
from .schemas import ValidationError, load_inputs
from .storage import MissionStore
from .planning_context import aliases_from_file
from .planning_io import load_audit, save_audit, save_plan


def add_planner_arguments(parser):
    parser.add_argument('--instruction', required=True)
    parser.add_argument('--planner', choices=('rules', 'llm'), default='rules')
    parser.add_argument('--aliases', type=Path, help='Optional YAML mapping Chinese labels to place IDs')
    parser.add_argument('--llm-format', choices=('json', 'tools'), default='json')
    parser.add_argument('--repair-attempts', type=int, choices=(0, 1), default=1)


def positive_timeout(text):
    value = float(text)
    if not math.isfinite(value) or not 0.1 <= value <= 600:
        raise argparse.ArgumentTypeError('timeout must be between 0.1 and 600 seconds')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description='RoboPilot language-grounded inspection missions (v0.5)')
    subparsers = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'run', 'mission'):
        sub = subparsers.add_parser(name)
        sub.add_argument('--places', required=True, type=Path)
        if name == 'mission':
            add_planner_arguments(sub)
        else:
            sub.add_argument('--plan', required=True, type=Path)
        if name in ('run', 'mission'):
            sub.add_argument('--backend', choices=('mock', 'ros'), default='mock')
            sub.add_argument('--output', type=Path, default=Path('runs'))
            sub.add_argument('--startup-timeout', type=positive_timeout, default=30.0)
            sub.add_argument('--wall-time', action='store_true', help='ROS: disable use_sim_time')
            sub.add_argument('--mock-outcomes', default='',
                             help='Comma-separated per-attempt outcomes: succeeded,failed,timeout,unsafe')
            sub.add_argument('--mock-images', default='', help='Per-inspection: red,empty,dark,missing')
    planner = subparsers.add_parser('plan', help='Generate and validate a plan; does not move robot')
    planner.add_argument('--places', required=True, type=Path)
    add_planner_arguments(planner)
    planner.add_argument('--memory', type=Path, default=Path('runs'))
    planner.add_argument('--backend', choices=('mock', 'ros'), default='ros')
    planner.add_argument('--output', type=Path, required=True)
    history = subparsers.add_parser('memory', help='Show historical red-marker observations')
    history.add_argument('--target', choices=TARGETS, default='red_marker')
    history.add_argument('--memory', type=Path, default=Path('runs'))
    history.add_argument('--backend', choices=('mock', 'ros'), default='ros')
    doctor = subparsers.add_parser('doctor', help='Check clock, scan, localization and RGB camera')
    doctor.add_argument('--initialize-home', action='store_true',
                        help='Only for a fresh home simulator: initialize at x=2.7,y=-2.1,yaw=pi/2')
    doctor.add_argument('--initialize-demo', action='store_true',
                        help='Only for a fresh default simulator: initialize at x=-2,y=-0.5,yaw=0')
    doctor.add_argument('--timeout', type=positive_timeout, default=30)
    doctor.add_argument('--output', type=Path)
    evaluation = subparsers.add_parser('evaluate', help='Read-only summary of recorded missions')
    evaluation.add_argument('--memory', type=Path, default=Path('runs'))
    evaluation.add_argument('--backend', choices=('mock', 'ros'), default='ros')
    evaluation.add_argument('--output', type=Path)
    benchmark = subparsers.add_parser('benchmark-plan', help='Evaluate fixed synthetic instructions; never executes robot')
    benchmark.add_argument('--places', required=True, type=Path)
    benchmark.add_argument('--aliases', type=Path)
    benchmark.add_argument('--cases', required=True, type=Path)
    benchmark.add_argument('--planner', choices=('rules','llm'), default='rules')
    benchmark.add_argument('--llm-format', choices=('json','tools'), default='json')
    benchmark.add_argument('--repair-attempts', type=int, choices=(0,1), default=1)
    benchmark.add_argument('--case', action='append', dest='selected')
    benchmark.add_argument('--repeats', type=int, choices=range(1,6), default=1)
    benchmark.add_argument('--output', type=Path, default=Path('runs/planner-benchmark'))
    agent = subparsers.add_parser('agent', help='LLM tool loop: ordered find-first red-marker search and return')
    agent.add_argument('--target', choices=TARGETS, default='red_marker')
    agent.add_argument('--places', required=True, type=Path)
    agent.add_argument('--search-places', required=True, nargs='+', help='1–6 distinct place IDs; explicit search contract')
    agent.add_argument('--backend', choices=('mock', 'ros'), default='mock')
    agent.add_argument('--output', type=Path, default=Path('runs/agent-search'))
    agent.add_argument('--max-turns', type=int, choices=range(1,41), default=24)
    agent.add_argument('--total-timeout', type=positive_timeout, default=600)
    agent.add_argument('--mock-images', default='')
    check = subparsers.add_parser('check', help='List supported inspections, preview user selection, confirm execution')
    check.add_argument('--places', type=Path, default=Path('src/robopilot/config/places.home.yaml'))
    check.add_argument('--instruction')
    check.add_argument('--list', dest='list_only', action='store_true')
    check.add_argument('--preview', action='store_true')
    check.add_argument('--backend', choices=('ros','mock'), default='mock')
    check.add_argument('--output', type=Path, default=Path('runs/user-inspection'))
    args = parser.parse_args(argv)
    if args.command == 'check':
        from .task_catalog import run_interactive
        return run_interactive(args)
    if args.command == 'agent':
        return agent_command(args)
    if args.command == 'benchmark-plan':
        try:
            from .benchmark import run_benchmark
            places, _ = load_inputs(args.places)
            aliases = aliases_from_file(args.aliases, places)
            directory, report = run_benchmark(args.cases,places,aliases,args.output,args.planner,
                                              args.llm_format,args.repair_attempts,args.selected,args.repeats)
            print(f'评测报告：{(directory / "report.md").resolve()}')
            print(json.dumps(report['metrics'],ensure_ascii=False,indent=2))
            return 0 if report['status']=='COMPLETE' and all(r['passed'] for r in report['results']) else 1
        except KeyboardInterrupt:
            print('评测已中断，已完成样本保留在输出目录。',file=sys.stderr)
            return 130
        except Exception as exc:
            print(f'评测失败：{exc}',file=sys.stderr)
            return 2
    if args.command == 'evaluate':
        try:
            from .evaluation import evaluate
            text = json.dumps(evaluate(args.memory, args.backend), ensure_ascii=False, indent=2)
            print(text)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text + '\n')
            return 0
        except Exception as exc:
            print(f'统计失败：{exc}', file=sys.stderr)
            return 1
    if args.command == 'doctor':
        try:
            from .diagnostics import diagnose
            result = diagnose(args.timeout, args.initialize_demo, args.initialize_home)
            text = json.dumps(result, ensure_ascii=False, indent=2)
            print(text)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text + '\n')
            return 0 if result['ready'] else 1
        except Exception as exc:
            print(f'环境检查失败：{exc}', file=sys.stderr)
            return 1
    if args.command in ('plan', 'memory'):
        return planning_command(args)
    audit = None
    try:
        places, plan = load_inputs(args.places, None if args.command == 'mission' else args.plan)
        if args.command == 'mission':
            # Finish planning and persistence before constructing any robot backend.
            from .planner import generate_plan
            audit = {}
            plan_path = args.output / 'plans' / (uuid.uuid4().hex + '.json')
            planning_store = MissionStore(args.output)
            try:
                aliases = aliases_from_file(args.aliases, places)
                plan = generate_plan(args.instruction, places, aliases, planning_store, args.backend,
                                     args.planner, audit, args.llm_format, args.repair_attempts)
                save_plan(plan_path, plan, audit)
            except Exception:
                if audit:
                    save_audit(plan_path, audit)
                raise
            finally:
                planning_store.close()
            print(f'规划通过：{plan_path.resolve()}')
        elif args.command == 'run':
            audit = load_audit(args.plan, plan, places)
    except ValidationError as exc:
        print(f'计划校验失败：{exc}', file=sys.stderr)
        return 2
    except Exception as exc:
        print(f'规划失败：{exc}', file=sys.stderr)
        return 2
    if args.command == 'validate':
        print(f'计划有效：{plan.name}，{len(plan.steps)} 个步骤，{len(places)} 个地点。')
        return 0
    outcomes = args.mock_outcomes.split(',') if args.mock_outcomes else []
    if any(x not in ('succeeded', 'failed', 'timeout', 'unsafe') for x in outcomes):
        parser.error('--mock-outcomes contains an unsupported outcome')
    if args.backend == 'ros' and outcomes:
        parser.error('--mock-outcomes is only valid with --backend mock')
    if args.backend == 'mock' and args.wall_time:
        parser.error('--wall-time is only valid with --backend ros')
    images = args.mock_images.split(',') if args.mock_images else []
    if any(x not in ('red', 'empty', 'dark', 'missing') for x in images):
        parser.error('Invalid --mock-images value')
    if args.backend == 'ros' and images:
        parser.error('--mock-images is only valid with --backend mock')
    backend = store = None
    try:
        if args.backend == 'mock':
            print('MOCK 模式：仅验证任务逻辑，不会连接 ROS，不代表仿真导航成功。')
            backend = MockBackend(outcomes, images=images)
        else:
            from .ros_adapter import RosNavigationBackend
            print('ROS 模式：将向 /navigate_to_pose 发送实际导航目标。')
            backend = RosNavigationBackend(use_sim_time=not args.wall_time)
        store = MissionStore(args.output)
        mission = MissionExecutor(backend, store, args.startup_timeout, print).run(plan, places, audit)
        print(f"任务状态：{mission['status']}")
        print(f"报告：{(args.output / mission['id'] / 'report.md').resolve()}")
        if mission['error']:
            print(mission['error'], file=sys.stderr)
        return 0 if mission['status'] == 'SUCCEEDED' else 130 if mission['status'] == 'CANCELED' else 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f'运行失败：{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    finally:
        try:
            if backend:
                backend.close()
        finally:
            if store:
                store.close()


def planning_command(args):
    store = None
    audit = {}
    try:
        store = MissionStore(args.memory)
        if args.command == 'memory':
            print(json.dumps(store.history(args.target, args.backend), ensure_ascii=False, indent=2))
            return 0
        from .planner import generate_plan
        places, _ = load_inputs(args.places)
        aliases = aliases_from_file(args.aliases, places)
        plan = generate_plan(args.instruction, places, aliases, store, args.backend, args.planner,
                             audit, args.llm_format, args.repair_attempts)
        save_plan(args.output, plan, audit)
        print(f'计划已校验并保存：{args.output.resolve()}；尚未执行。规划器：{args.planner}')
        return 0
    except Exception as exc:
        if audit and args.command == 'plan':
            try:
                save_audit(args.output, audit)
            except (OSError, ValidationError):
                pass
        print(f'规划/查询失败：{type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()



def agent_command(args):
    """Constrained search contract; load credentials before constructing robot backend."""
    from .agent_loop import SearchAgent, model_decider
    from .llm_config import load_llm_config
    backend = store = None
    try:
        places, _ = load_inputs(args.places)
        if (not 1 <= len(args.search_places) <= 6 or len(set(args.search_places)) != len(args.search_places)
                or any(p not in places for p in args.search_places)):
            raise ValidationError('search-places must contain 1–6 distinct known places')
        images = args.mock_images.split(',') if args.mock_images else []
        if (any(x not in ('red','empty','dark','missing') for x in images)
                or (args.backend=='ros' and images)):
            raise ValidationError('mock-images only accepts mock red/empty/dark/missing')
        config = load_llm_config()
        if args.backend=='ros':
            from .ros_adapter import RosNavigationBackend
            backend = RosNavigationBackend()
        else:
            backend = MockBackend(images=images)
        store = MissionStore(args.output)
        mission = SearchAgent(backend,store,90,print).run_search(places,args.search_places,
            model_decider(config),max_turns=args.max_turns,total_timeout=args.total_timeout,model=config.model,target=args.target)
        print(f"任务状态：{mission['status']}")
        print(f"报告：{(args.output/mission['id']/'report.md').resolve()}")
        if mission['error']: print(mission['error'],file=sys.stderr)
        return 0 if mission['status']=='SUCCEEDED' else 1
    except Exception as exc:
        print(f'Agent 失败：{exc}',file=sys.stderr)
        return 2
    finally:
        if backend: backend.close()
        if store: store.close()


if __name__ == '__main__':
    raise SystemExit(main())
