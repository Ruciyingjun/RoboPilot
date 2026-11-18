"""Local immutable RSI artifacts, reviewed image datasets and atomic deployment history."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .planning_context import digest
from .schemas import ValidationError


def now():
    return datetime.now(timezone.utc).isoformat()


def model_fingerprint(config):
    return {'provider':config.provider,'model':config.model,
            'endpoint_sha256':digest(config.endpoint),'thinking':'disabled'}


def evaluator_fingerprint():
    names = ('toolbox_vision.py','targets.py','prompt_registry.py','rsi_evaluator.py','rsi_gate.py','llm_client.py')
    return digest({name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                   for name in names})


class RSIStore:
    def __init__(self, directory, *, kind=None):
        from .prompt_registry import snapshot
        from .targets import VISUAL_TARGETS
        if kind not in (None,'production','sandbox'):
            raise ValidationError('Registry kind must be production or sandbox')
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'images').mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root/'rsi.sqlite3', timeout=10)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS prompts (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY,target TEXT NOT NULL,
                image_hash TEXT NOT NULL,group_id TEXT NOT NULL,split TEXT NOT NULL,payload TEXT NOT NULL,
                UNIQUE(target,image_hash));
            CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evaluations (id TEXT PRIMARY KEY,status TEXT NOT NULL,
                payload TEXT NOT NULL,sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS active (target TEXT PRIMARY KEY,version TEXT NOT NULL,
                model_json TEXT);
            CREATE TABLE IF NOT EXISTS activations (seq INTEGER PRIMARY KEY,target TEXT NOT NULL,
                previous TEXT NOT NULL,version TEXT NOT NULL,evaluation TEXT,
                model_json TEXT,reason TEXT NOT NULL,created_at TEXT NOT NULL);
        ''')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('kind',kind or 'production'))
            self.kind = self.db.execute('SELECT value FROM meta WHERE key=?',('kind',)).fetchone()[0]
        if kind is not None and self.kind!=kind:
            self.db.close()
            raise ValidationError('Cannot change an existing registry kind')
        with self.db:
            for target in VISUAL_TARGETS:
                base = snapshot(target)
                self.db.execute('INSERT OR IGNORE INTO prompts VALUES (?,?)',
                                (base['id'],json.dumps(base,ensure_ascii=False)))

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self,*_):
        self.close()

    def prompt(self, version):
        from .prompt_registry import validate_snapshot
        row = self.db.execute('SELECT payload FROM prompts WHERE id=?',(version,)).fetchone()
        if not row:
            raise ValidationError('Unknown prompt version')
        value = json.loads(row[0])
        return validate_snapshot(value,value['target'])

    def active(self,target):
        from .prompt_registry import snapshot
        row = self.db.execute('SELECT version,model_json FROM active WHERE target=?',(target,)).fetchone()
        value = self.prompt(row[0]) if row else snapshot(target)
        if row and row[1]:
            value['deployment_model'] = json.loads(row[1])
        return value

    def candidate(self,target,guidance,rationale,*,parent=None,source='manual'):
        from .prompt_registry import snapshot
        parent = parent or self.active(target)['id']
        if self.prompt(parent)['target']!=target or not isinstance(guidance,str) or not guidance.strip():
            raise ValidationError('Candidate needs matching parent and nonempty guidance')
        value = snapshot(target,guidance,parent,rationale,source)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO prompts VALUES (?,?)',
                            (value['id'],json.dumps(value,ensure_ascii=False)))
        return value

    def import_dataset(self,manifest):
        """Human labels are explicit. Images and related scene groups cannot cross data splits."""
        import cv2
        path = Path(manifest).resolve()
        data = json.loads(path.read_text())
        if (not isinstance(data,dict) or set(data)!={'version','cases'} or type(data['version']) is not int or data['version']!=1
                or not isinstance(data['cases'],list) or not 1<=len(data['cases'])<=1000):
            raise ValidationError('Dataset requires version=1 and 1–1000 cases')
        values, images = [], {}
        from .targets import VISUAL_TARGETS
        for case in data['cases']:
            required = {'id','target','image','expected','split','group_id','critical','reviewer','reason','failure_type'}
            if not isinstance(case,dict) or not required<=set(case) or set(case)-required-{'source','original_result'}:
                raise ValidationError('Invalid reviewed case fields')
            if (case['target'] not in VISUAL_TARGETS or case['expected'] not in ('detected','not_detected','unknown')
                    or case['split'] not in ('development','gate','test') or type(case['critical']) is not bool
                    or any(not isinstance(case[k],str) or not 1<=len(case[k])<=1000
                           for k in ('id','group_id','reviewer','reason','failure_type'))):
                raise ValidationError('Invalid case label, provenance or split')
            image = path.parent/case['image']
            raw = image.read_bytes()
            if len(raw)>20*1024*1024 or cv2.imread(str(image)) is None:
                raise ValidationError('Image is invalid or exceeds 20 MiB')
            image_hash = hashlib.sha256(raw).hexdigest()
            images[image_hash] = raw
            value = {**case,'image':'images/'+image_hash+'.image','image_sha256':image_hash}
            values.append(value)
        if len({v['id'] for v in values})!=len(values) or len({(v['target'],v['image_sha256']) for v in values})!=len(values):
            raise ValidationError('Duplicate case IDs or image/target pairs')
        with self.db:
            for value in values:
                # Check both existing and newly inserted cases within this transaction.
                other = self.db.execute('SELECT payload FROM cases WHERE id=?',(value['id'],)).fetchone()
                if other and json.loads(other[0])!=value:
                    raise ValidationError('Reviewed cases are immutable; use a new case ID')
                groups = self.db.execute('SELECT split FROM cases WHERE group_id=? OR image_hash=?',
                                        (value['group_id'],value['image_sha256'])).fetchall()
                if any(g[0]!=value['split'] for g in groups):
                    raise ValidationError('Image or scene group leaks across dataset splits')
                try:
                    self.db.execute('INSERT OR IGNORE INTO cases VALUES (?,?,?,?,?,?)',
                        (value['id'],value['target'],value['image_sha256'],value['group_id'],value['split'],
                         json.dumps(value,ensure_ascii=False)))
                    actual = self.db.execute('SELECT id FROM cases WHERE target=? AND image_hash=?',
                                             (value['target'],value['image_sha256'])).fetchone()
                    if actual[0]!=value['id']:
                        raise ValidationError('Image is already registered under another case ID')
                except sqlite3.IntegrityError as exc:
                    raise ValidationError('Conflicting case registration') from exc
            dataset = {'version':1,'cases':sorted(values,key=lambda c:c['id'])}
            dataset['id'] = 'dataset_'+digest(dataset)
            for image_hash,raw in images.items():
                dest = self.root/'images'/(image_hash+'.image')
                if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()!=image_hash:
                    raise ValidationError('Registered image content was changed')
                if not dest.exists():
                    dest.write_bytes(raw)
            self.db.execute('INSERT OR IGNORE INTO datasets VALUES (?,?)',
                            (dataset['id'],json.dumps(dataset,ensure_ascii=False)))
        return dataset

    def dataset(self,identifier):
        row = self.db.execute('SELECT payload FROM datasets WHERE id=?',(identifier,)).fetchone()
        if not row:
            raise ValidationError('Unknown dataset')
        value = json.loads(row[0])
        if value['id']!='dataset_'+digest({k:v for k,v in value.items() if k!='id'}):
            raise ValidationError('Dataset checksum mismatch')
        return value

    def image(self,case):
        import cv2
        path = self.root/case['image']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=case['image_sha256']:
            raise ValidationError('Evaluation image checksum mismatch')
        return cv2.imread(str(path))

    def save_evaluation(self,report):
        encoded = json.dumps(report,ensure_ascii=False,allow_nan=False)
        with self.db:
            existing = self.db.execute('SELECT status FROM evaluations WHERE id=?',(report['id'],)).fetchone()
            if existing and existing[0]!='RUNNING':
                raise ValidationError('Completed evaluation is immutable')
            self.db.execute('INSERT OR REPLACE INTO evaluations VALUES (?,?,?,?)',
                            (report['id'],report['status'],encoded,digest(report)))

    def evaluation(self,identifier):
        row = self.db.execute('SELECT payload,sha256 FROM evaluations WHERE id=?',(identifier,)).fetchone()
        if not row:
            raise ValidationError('Unknown evaluation')
        value = json.loads(row[0])
        if digest(value)!=row[1]:
            raise ValidationError('Evaluation checksum mismatch')
        return value

    def activate(self,evaluation_id,*,reason):
        from .rsi_gate import assess
        report = self.evaluation(evaluation_id)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if report['status']!='COMPLETE' or (self.kind=='production' and report['mode']!='live'):
                raise ValidationError('Only complete live evaluations may deploy in production')
            if report['evaluator_sha256']!=evaluator_fingerprint():
                raise ValidationError('Evaluator code changed; evaluate again before activation')
            base, candidate = self.prompt(report['baseline']),self.prompt(report['candidate'])
            if self.active(candidate['target'])['id']!=base['id'] or candidate['parent']!=base['id']:
                raise ValidationError('Active baseline changed; re-evaluation is required')
            if report['target']!=candidate['target']:
                raise ValidationError('Evaluation target mismatch')
            dataset = self.dataset(report['dataset'])
            for case in dataset['cases']:
                if case['target']==candidate['target'] and case['split']=='gate':
                    self.image(case)
            if any(row['prompt_sha256']!=(base if row['role']=='baseline' else candidate)['sha256']
                   for row in report['rows']):
                raise ValidationError('Evaluation prompt checksum mismatch')
            verdict = assess(report,dataset)
            if not verdict['passed']:
                raise ValidationError('RSI gate rejected activation: '+', '.join(verdict['failed']))
            self._deploy(candidate['target'],base['id'],candidate['id'],report['model'],evaluation_id,reason)
        return self.active(candidate['target'])

    def _deploy(self,target,previous,version,model,evaluation,reason):
        if not isinstance(reason,str) or not reason.strip() or len(reason)>2000:
            raise ValidationError('A bounded deployment reason is required')
        self.db.execute('INSERT OR REPLACE INTO active VALUES (?,?,?)',
                        (target,version,json.dumps(model) if model else None))
        self.db.execute('INSERT INTO activations(target,previous,version,evaluation,model_json,reason,created_at) '
            'VALUES (?,?,?,?,?,?,?)',(target,previous,version,evaluation,json.dumps(model),reason,now()))

    def rollback(self,target,*,reason):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            current = self.active(target)
            row = self.db.execute('SELECT previous FROM activations WHERE target=? ORDER BY seq DESC LIMIT 1',
                                  (target,)).fetchone()
            if not row:
                raise ValidationError('No activation to roll back')
            previous = self.prompt(row[0])
            model_row = self.db.execute('SELECT model_json FROM activations WHERE target=? AND version=? '
                'ORDER BY seq DESC LIMIT 1',(target,previous['id'])).fetchone()
            model = json.loads(model_row[0]) if model_row else None
            self._deploy(target,current['id'],previous['id'],model,None,reason)
        return self.active(target)

    def proposal(self,value):
        value = {**value,'id':'proposal_'+uuid.uuid4().hex,'created_at':now()}
        with self.db:
            self.db.execute('INSERT INTO proposals VALUES (?,?)',(value['id'],json.dumps(value,ensure_ascii=False)))
        return value
