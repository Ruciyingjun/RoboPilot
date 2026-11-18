"""CLI wiring for durable workflows and explicit offline fault-injection decisions."""
import fcntl
import json
from pathlib import Path
import tempfile

from .backends import MockBackend
from .planning_context import digest
from .runtime_store import CheckpointStore
from .schemas import load_inputs, ValidationError
from .storage import MissionStore
from .workflow_runtime import WorkflowRuntime, model_decider


def workflow_command(args):
    backend = store = lease = None
    try:
        if args.resume:
            if args.places or args.plan:
                raise ValidationError('Resume uses checkpointed inputs; omit --places and --plan')
            plan = places = None
        else:
            if not args.places or not args.plan:
                raise ValidationError('New workflows require --places and --plan')
            places, plan = load_inputs(args.places, args.plan)
        if args.decider == 'scripted':
            if args.backend != 'mock' or not args.script:
                raise ValidationError('Scripted decisions are only permitted for explicit mock tests')
            calls = json.loads(args.script.read_text())
            if not isinstance(calls, list):
                raise ValidationError('Script must contain an array of tool calls')
            model_info = {'source':'scripted-mock', 'script_sha256':digest(calls)}
            def decide(messages, remaining, output_tokens):
                index = sum(m['role']=='assistant' for m in messages)
                if index >= len(calls):
                    raise ValidationError('Offline decision script exhausted')
                call = calls[index]
                return call, {'telemetry':{'total_tokens':0}, 'assistant_message':{
                    'role':'assistant','content':'','tool_calls':[{'id':f'offline_{index}',
                        'type':'function','function':{'name':'robot_tool','arguments':json.dumps(call)}}]}}
        else:
            if args.script:
                raise ValidationError('--script requires --decider scripted')
            from .llm_config import load_llm_config
            config = load_llm_config()
            model_info = {'source':'llm','model':config.model,'provider':config.provider,
                          'endpoint_sha256':digest(config.endpoint)}
            decide = model_decider(config)
        images = args.mock_images.split(',') if args.mock_images else []
        if any(i not in ('red','empty','dark','missing') for i in images) or (images and args.backend!='mock'):
            raise ValidationError('Invalid mock image configuration')
        if args.backend == 'mock':
            print('MOCK workflow: offline robot; scripted decisions are test fixtures, not model acceptance.')
            backend = MockBackend(images=images)
        else:
            from .ros_adapter import RosNavigationBackend
            backend = RosNavigationBackend()
        # Serialize workflow owners even when their output directories differ.
        identity = digest(backend.runtime_identity())
        lease = (Path(tempfile.gettempdir())/f'robopilot-workflow-{identity}.lock').open('a+')
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another workflow already owns this robot') from None
        store = MissionStore(args.output)
        with CheckpointStore(args.output) as checkpoints:
            runtime = WorkflowRuntime(backend, store, checkpoints, decide)
            context = runtime.run(plan, places, resume=args.resume, max_turns=args.max_turns,
                max_tokens=args.max_tokens, total_timeout=args.total_timeout,model_info=model_info)
        print('Workflow:', context['status'])
        print('Checkpoint:', (args.output/'context.json').resolve())
        print('Report:', (args.output/context['mission']['id']/'report.md').resolve())
        if context['mission']['error']:
            print(context['mission']['error'])
        return 0 if context['status']=='SUCCEEDED' else 1
    except Exception as exc:
        print(f'Workflow error: {type(exc).__name__}: {exc}')
        return 2
    finally:
        if backend:
            backend.close()
        if store:
            store.close()
        if lease:
            lease.close()
