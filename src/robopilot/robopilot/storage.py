"""用途：将任务状态持久化到 SQLite，并生成 JSON 快照和 Markdown 报告。"""

import json
import sqlite3
from pathlib import Path


def _atomic_write(path, text):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def _cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def render_report(mission):
    label = 'MOCK：仅验证执行逻辑，不代表机器人实际运行' if mission['backend'] == 'mock' else 'ROS：Nav2 Action 执行记录'
    semantic = any(o.get('target') not in (None,'red_marker') for o in mission.get('observations',[]))
    lines = [f"# RoboPilot 任务报告：{mission['name']}", '', f'**{label}**', '',
             f"- 任务 ID：`{mission['id']}`", f"- 状态：**{mission['status']}**",
             f"- 开始时间（UTC）：{mission['created_at']}",
             f"- 结束时间（UTC）：{mission.get('finished_at') or '尚未结束'}",
             f"- 起点：`{json.dumps(mission.get('start_pose'), ensure_ascii=False)}`",
             '', (('语义目标由云端VLM判断；detected表示检查条件满足，not_detected表示本次视野内条件不满足，unknown表示无法确认。red_marker为本地颜色检测。'
                   if semantic else '红色标记检查基于颜色区域，不代表工具箱语义识别；未检测到不代表整个房间不存在。')
                  if mission.get('observations') else '本次未进行视觉检查；本报告不包含图像证据。'), '',
             '| 步骤 | 动作 | 地点 | 状态 | 尝试次数 | 原因 |',
             '|---|---|---|---|---:|---|']
    for step in mission['steps']:
        values = (step['id'], step['action'], step.get('place') or '任务起点',
                  step['status'], len(step['attempts']), step.get('message', ''))
        lines.append('| ' + ' | '.join(_cell(v) for v in values) + ' |')
    if mission.get('error'):
        lines.extend(['', '任务说明：' + mission['error']])
    planning = mission.get('planning', {})
    if planning:
        lines.extend(['', '## 任务来源', '', f"- 规划方式：{_cell(planning.get('planner', 'json_file'))}"])
        if planning.get('instruction'):
            lines.append('- 原始指令：' + _cell(planning['instruction']))
        if planning.get('model'):
            lines.append('- 模型：' + _cell(planning['model']))
        if planning.get('intent_contract'):
            lines.append('- 完整性检查：有限地点/检查/返航/简单否定约束，不是任意自然语言语义验证。')
        if planning.get('context', {}).get('last_seen'):
            memory = planning['context']['last_seen']
            lines.append(f"- 规划时历史发现：{_cell(memory['place'])}，{_cell(memory['observed_at'])}；不代表当前存在")
    if mission.get('agent'):
        lines.extend(['', '## 工具反馈循环', '',
                      '搜索契约：`' + _cell(json.dumps(mission['agent']['contract'],ensure_ascii=False)) + '`', '',
                      '| 轮次 | 工具参数 | 返回结果 |', '|---|---|---|'])
        for turn in mission['agent']['turns']:
            lines.append('| ' + ' | '.join(_cell(x) for x in (turn['number'],
                json.dumps(turn['call'],ensure_ascii=False), json.dumps(turn['result'],ensure_ascii=False))) + ' |')
    for obs in mission.get('observations', []):
        lines.extend(['', f"## 观测：{obs['place']} / {obs['target']}", '',
                      f"- 结果：{obs['status']}", f"- 时间：{obs['observed_at']}",
                      f"- 说明：{obs.get('reason', '')}"])
        if obs.get('memory_validity'):
            validity = obs['memory_validity']
            lines.append('- 记忆有效性：' + _cell(validity['state']) + '；' + _cell('；'.join(validity['reasons'])))
        if obs.get('predicate'):
            lines.append('- 检查要求：' + _cell(obs['predicate']))
            lines.append('- 条件满足：' + {'detected':'是','not_detected':'否','unknown':'无法确认'}[obs['status']])
        if obs.get('method'):
            lines.append('- 感知方法：' + _cell(obs['method']) + '；模型：' + _cell(obs.get('model','本地')))
        if obs.get('visual_cues'):
            lines.append('- 模型报告的可见特征（未经独立标注核验）：' + _cell(', '.join(obs['visual_cues'])))
        if obs.get('evidence_path'):
            lines.extend(['', f"![巡检图像证据]({obs['evidence_path']})"])
    semantic_observations = [o for o in mission.get('observations', []) if o.get('target') not in (None,'red_marker')]
    if semantic_observations:
        counts = {status:sum(o['status']==status for o in semantic_observations)
                  for status in ('detected','not_detected','unknown')}
        lines.extend(['', f"检查条件汇总：满足 {counts['detected']}；不满足 {counts['not_detected']}；无法确认 {counts['unknown']}。",
                      '任务状态描述执行是否完成，不表示所有检查条件都满足。'])
    lines.extend(['', '每次尝试的耗时、反馈及错误码见同目录 `mission.json`。', ''])
    return '\n'.join(lines)


class MissionStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'robopilot.sqlite3')
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY, backend TEXT NOT NULL, status TEXT NOT NULL,
                updated_at TEXT NOT NULL, record_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS steps (
                mission_id TEXT NOT NULL REFERENCES missions(id), id TEXT NOT NULL,
                ordinal INTEGER NOT NULL, status TEXT NOT NULL, record_json TEXT NOT NULL,
                PRIMARY KEY (mission_id, id)
            );
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(id),
                place TEXT NOT NULL, target TEXT NOT NULL, backend TEXT NOT NULL,
                observed_at TEXT NOT NULL, status TEXT NOT NULL, record_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS observations_lookup
                ON observations(target, backend, status, observed_at);
        ''')

    def save(self, mission):
        record = json.dumps(mission, ensure_ascii=False, indent=2, allow_nan=False)
        with self.db:
            self.db.execute('''INSERT INTO missions VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET backend=excluded.backend,
                            status=excluded.status, updated_at=excluded.updated_at,
                            record_json=excluded.record_json''',
                            (mission['id'], mission['backend'], mission['status'],
                             mission['updated_at'], record))
            for ordinal, step in enumerate(mission['steps']):
                self.db.execute('INSERT OR REPLACE INTO steps VALUES (?, ?, ?, ?, ?)',
                                (mission['id'], step['id'], ordinal, step['status'],
                                 json.dumps(step, ensure_ascii=False, allow_nan=False)))
            for obs in mission.get('observations', []):
                self.db.execute('INSERT OR IGNORE INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                                (obs['id'], mission['id'], obs['place'], obs['target'], obs['backend'],
                                 obs['observed_at'], obs['status'],
                                 json.dumps(obs, ensure_ascii=False, allow_nan=False)))
        directory = self.root / mission['id']
        directory.mkdir(exist_ok=True)
        _atomic_write(directory / 'mission.json', record + '\n')
        _atomic_write(directory / 'report.md', render_report(mission))

    def close(self):
        self.db.close()

    def last_seen(self, target, backend='ros'):
        row = self.db.execute('''SELECT record_json FROM observations
            WHERE target=? AND backend=? AND status='detected'
            ORDER BY observed_at DESC, rowid DESC LIMIT 1''', (target, backend)).fetchone()
        return json.loads(row[0]) if row else None

    def history(self, target, backend='ros', limit=20):
        rows = self.db.execute('''SELECT record_json FROM observations
            WHERE target=? AND backend=? ORDER BY observed_at DESC, rowid DESC LIMIT ?''',
                               (target, backend, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def assess_memory(self, target, backend, context_id, mission_id=None, place=None, now=None):
        from .memory_validity import assess_memory
        # 不截取最近20条：其他检查点的大量观测不能遮蔽本检查点的更新。
        rows = self.db.execute("SELECT record_json FROM observations WHERE target=? AND backend=? ORDER BY observed_at DESC, rowid DESC",
                               (target, backend)).fetchall()
        return assess_memory([json.loads(row[0]) for row in rows], target=target,
            backend=backend, context_id=context_id, mission_id=mission_id, place=place, now=now)
