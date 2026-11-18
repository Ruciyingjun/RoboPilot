"""RSI commands: reviewed cases, prompt proposals, evaluation, gated activation and rollback."""
import json
from pathlib import Path
import uuid

from .targets import VISUAL_TARGETS


def add_rsi_parser(subparsers):
    from .prompt_registry import registry_directory
    parser = subparsers.add_parser('rsi',help='Controlled visual prompt improvement loop')
    parser.add_argument('--registry',type=Path,default=registry_directory())
    commands = parser.add_subparsers(dest='rsi_command',required=True)
    init = commands.add_parser('init')
    init.add_argument('--sandbox',action='store_true',help='Fixture-only deployment demo; not a production registry')
    imp = commands.add_parser('import',help='Import a human-reviewed image manifest')
    imp.add_argument('--manifest',type=Path,required=True)
    collect = commands.add_parser('collect',help='Create a reviewed case from one mission observation')
    collect.add_argument('--mission',type=Path,required=True)
    collect.add_argument('--observation',required=True)
    collect.add_argument('--id',required=True)
    collect.add_argument('--expected',choices=('detected','not_detected','unknown'),required=True)
    collect.add_argument('--split',choices=('development','gate','test'),required=True)
    collect.add_argument('--group',required=True,help='Scene/session group, kept in one split')
    collect.add_argument('--reviewer',required=True)
    collect.add_argument('--reason',required=True)
    collect.add_argument('--failure-type',required=True)
    collect.add_argument('--critical',action='store_true')
    candidate = commands.add_parser('candidate',help='Register manually authored supplementary guidance')
    candidate.add_argument('--target',choices=VISUAL_TARGETS,required=True)
    candidate.add_argument('--guidance-file',type=Path,required=True)
    candidate.add_argument('--reason',required=True)
    propose = commands.add_parser('propose',help='Paid model proposal using development cases only')
    propose.add_argument('--target',choices=VISUAL_TARGETS,required=True)
    propose.add_argument('--dataset',required=True)
    propose.add_argument('--max-tokens',type=int,default=4000)
    evaluate = commands.add_parser('evaluate',help='Paid paired VLM calls, or explicit sandbox fixtures')
    evaluate.add_argument('--candidate',required=True)
    evaluate.add_argument('--dataset',required=True)
    evaluate.add_argument('--split',choices=('development','gate','test'),default='gate')
    evaluate.add_argument('--repeats',type=int,default=3)
    evaluate.add_argument('--max-requests',type=int,default=200)
    evaluate.add_argument('--max-tokens',type=int,default=50000)
    evaluate.add_argument('--timeout',type=float,default=600.)
    evaluate.add_argument('--fixtures',type=Path,help='Only sandbox registries can use fixture responses')
    activate = commands.add_parser('activate',help='Recompute gate and atomically activate the evaluated candidate')
    activate.add_argument('--evaluation',required=True)
    activate.add_argument('--reason',required=True)
    rollback = commands.add_parser('rollback')
    rollback.add_argument('--target',choices=VISUAL_TARGETS,required=True)
    rollback.add_argument('--reason',required=True)
    commands.add_parser('status')
    demo=commands.add_parser('demo',help='Offline synthetic lifecycle; no model requests or robot actions')
    demo.add_argument('--output',type=Path,required=True)


def rsi_command(args):
    from .llm_config import LLMConfig, load_llm_config
    from .rsi_store import RSIStore
    try:
        if args.rsi_command=='demo':
            from .rsi_demo import run_demo
            print(json.dumps(run_demo(args.output),ensure_ascii=False,indent=2))
            return 0
        kind = ('sandbox' if args.sandbox else 'production') if args.rsi_command=='init' else None
        with RSIStore(args.registry,kind=kind) as store:
            action = args.rsi_command
            if action=='init':
                result = {'registry':str(store.root),'kind':store.kind}
            elif action=='import':
                result = store.import_dataset(args.manifest)
            elif action=='collect':
                mission = json.loads(args.mission.read_text())
                obs = next(o for o in mission['observations'] if o['id']==args.observation)
                image = (args.mission.resolve().parent/obs['evidence_path']).resolve()
                manifest = {'version':1,'cases':[{'id':args.id,'target':obs['target'],
                    'image':str(image),'expected':args.expected,'split':args.split,'group_id':args.group,
                    'critical':args.critical,'reviewer':args.reviewer,'reason':args.reason,
                    'failure_type':args.failure_type,'original_result':obs,
                    'source':{'mission_id':mission['id'],'observation_id':obs['id'],
                              'mission_path':str(args.mission.resolve()),
                              'prompt_version':obs.get('prompt_version'),'backend':mission['backend']}}]}
                incoming = store.root/'imports'
                incoming.mkdir(exist_ok=True)
                path = incoming/(uuid.uuid4().hex+'.json')
                path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
                result = store.import_dataset(path)
            elif action=='candidate':
                result = store.candidate(args.target,args.guidance_file.read_text(),args.reason)
            elif action=='propose':
                from .rsi_proposer import propose
                result = propose(store,args.target,args.dataset,load_llm_config(),max_tokens=args.max_tokens)
            elif action=='evaluate':
                from .rsi_evaluator import evaluate
                fixtures = json.loads(args.fixtures.read_text()) if args.fixtures else None
                config = (LLMConfig('deepseek','https://example.invalid','deepseek-flash','fixture-only',
                                   'disabled','high',30) if fixtures is not None else load_llm_config())
                result = evaluate(store,args.candidate,args.dataset,config,split=args.split,
                    repeats=args.repeats,fixtures=fixtures,max_requests=args.max_requests,
                    max_tokens=args.max_tokens,total_timeout=args.timeout)
            elif action=='activate':
                result = store.activate(args.evaluation,reason=args.reason)
            elif action=='rollback':
                result = store.rollback(args.target,reason=args.reason)
            else:
                result = {'kind':store.kind,'active':{target:store.active(target)['id'] for target in VISUAL_TARGETS},
                    'activations':[dict(zip(('seq','target','previous','version','evaluation','reason','created_at'),row))
                        for row in store.db.execute('SELECT seq,target,previous,version,evaluation,reason,created_at '
                                                    'FROM activations ORDER BY seq')]}
            if action in ('import','collect'):
                result = {'id':result['id'],'cases':len(result['cases'])}
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 1 if action=='evaluate' and not result['gate']['passed'] else 0
    except Exception as exc:
        print(f'RSI error: {type(exc).__name__}: {exc}')
        return 2
