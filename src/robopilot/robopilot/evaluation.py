"""用途：只读汇总任务数据库的完成率、导航步骤结果与耗时，不把检测数量当作识别准确率。"""

import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path


def evaluate(root, backend='ros'):
    database = Path(root).resolve() / 'robopilot.sqlite3'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        records = [json.loads(row[0]) for row in db.execute(
            'SELECT record_json FROM missions WHERE backend=?', (backend,))]
    finished = [r for r in records if r.get('finished_at')]
    statuses = Counter(r['status'] for r in finished)
    nav = [s for r in finished for s in r['steps']
           if s['action'] in ('navigate', 'return_to_start')]
    durations = [(datetime.fromisoformat(r['finished_at']) -
                  datetime.fromisoformat(r['created_at'])).total_seconds() for r in finished]
    return {'backend': backend, 'finished_missions': len(finished),
            'unfinished_missions': len(records)-len(finished), 'mission_statuses': dict(statuses),
            'mission_success_rate': statuses['SUCCEEDED']/len(finished) if finished else None,
            'navigation_steps': len(nav),
            'navigation_step_success_rate': sum(s['status']=='SUCCEEDED' for s in nav)/len(nav) if nav else None,
            'mean_mission_duration_s': round(sum(durations)/len(durations), 3) if durations else None,
            'inspection_results': dict(Counter(o['status'] for r in finished for o in r.get('observations', []))),
            'note': '记录级统计；复查任务不独立。没有人工真值，不能计算视觉准确率，也不能据此推断泛化能力。'}
