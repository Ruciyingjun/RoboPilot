"""Executable fixture-only RSI lifecycle. Never calls models or controls a robot."""
import json
from pathlib import Path

import cv2
import numpy as np

from .llm_config import LLMConfig
from .prompt_registry import pin_prompts
from .rsi_evaluator import evaluate
from .rsi_store import RSIStore
from .schemas import ValidationError


def run_demo(output):
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    cases=[]
    labels=('detected','detected','not_detected','not_detected','unknown','unknown',
            'detected','not_detected','unknown')
    for i,label in enumerate(labels):
        image=output/f'synthetic_{i}.png'
        canvas=np.full((80,120,3),70+i*5,dtype=np.uint8)
        cv2.putText(canvas,f'FIXTURE {i}',(4,40),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
        cv2.imwrite(str(image),canvas)
        cases.append({'id':f'fixture_{i}','target':'toolbox','image':str(image),
            'expected':label,'split':'gate' if i<6 else 'development','group_id':f'synthetic_{i}',
            'critical':label!='detected','reviewer':'synthetic-fixture-not-human-annotation',
            'reason':'Synthetic protocol fixture; not a semantic vision example',
            'failure_type':'fixture-only'})
    manifest=output/'cases.json'
    manifest.write_text(json.dumps({'version':1,'cases':cases},indent=2)+'\n')
    def reply(status):
        return {'view_clear':status!='unknown','status':status,'reason':'Explicit fixture response',
                'visual_cues':['handle','lid'] if status=='detected' else []}
    config=LLMConfig('deepseek','https://example.invalid','deepseek-flash','fixture-only','disabled','high',30)
    with RSIStore(output/'registry',kind='sandbox') as store:
        dataset=store.import_dataset(manifest)
        before=pin_prompts(['toolbox'],store.root)['toolbox']
        baseline={c['id']:reply('not_detected' if c['id']=='fixture_0' else c['expected']) for c in cases}
        correct={c['id']:reply(c['expected']) for c in cases}
        bad=store.candidate('toolbox','Overconfident fixture candidate.','Demonstrate critical failure rejection')
        bad_replies={**correct,'fixture_4':reply('not_detected')}
        rejected=evaluate(store,bad['id'],dataset['id'],config,fixtures={'baseline':baseline,'candidate':bad_replies})
        try:
            store.activate(rejected['id'],reason='Must be rejected')
        except ValidationError:
            bad_blocked=True
        else:
            raise AssertionError('Bad candidate unexpectedly activated')
        good=store.candidate('toolbox','Check visible handle and lid before classifying.','Demonstrate gated promotion')
        passed=evaluate(store,good['id'],dataset['id'],config,fixtures={'baseline':baseline,'candidate':correct})
        active=store.activate(passed['id'],reason='Fixture-only lifecycle acceptance')
        after=pin_prompts(['toolbox'],store.root)['toolbox']
        rolled_back=store.rollback('toolbox',reason='Fixture rollback acceptance')
        summary={'mode':'fixture-only; NOT real VLM or robot performance',
            'bad_candidate_blocked':bad_blocked,'good_candidate_activated':active['id']==good['id'],
            'pinned_old_version':before['id'],'new_task_version':after['id'],
            'snapshot_unchanged':before['id']!=after['id'],
            'rollback_restored_baseline':rolled_back['id']==before['id'],
            'rejected_evaluation':rejected['id'],'passed_evaluation':passed['id'],
            'model_requests':0,'robot_actions':0}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary
