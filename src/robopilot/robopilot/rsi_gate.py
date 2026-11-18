"""Deterministic non-regression gate; recomputed from paired rows at activation."""
import math

POLICY = {'version':1,'min_cases':6,'min_repeats':3,'token_ratio':1.25,'latency_ratio':1.5,
          'latency_slack_s':.25,'require_net_improvement':True}


def assess(report,dataset):
    checks = {}
    cases = {c['id']:c for c in dataset['cases'] if c['target']==report['target'] and c['split']=='gate'}
    repeats = report['repeats']
    checks['complete_gate_evaluation'] = report['status']=='COMPLETE' and report['split']=='gate'
    checks['fixed_policy'] = report['policy']==POLICY
    checks['coverage'] = (len(cases)>=POLICY['min_cases'] and repeats>=POLICY['min_repeats']
        and {c['expected'] for c in cases.values()}=={'detected','not_detected','unknown'}
        and any(c['critical'] and c['expected']=='unknown' for c in cases.values()))
    expected = {(role,case_id,r) for role in ('baseline','candidate') for case_id in cases for r in range(repeats)}
    rows = report['rows']
    actual = {(r['role'],r['case_id'],r['repeat']) for r in rows}
    checks['paired_rows'] = actual==expected and len(rows)==len(expected)
    if not checks['paired_rows']:
        return {'passed':False,'checks':checks,'failed':[k for k,v in checks.items() if not v], 'metrics':{}}
    def correct(row):
        return not row.get('error_kind') and row['status']==cases[row['case_id']]['expected']
    base = [r for r in rows if r['role']=='baseline']
    candidate = [r for r in rows if r['role']=='candidate']
    valid_costs = all(type(r.get('tokens')) is int and r['tokens']>=0
        and type(r.get('duration_s')) in (int,float) and math.isfinite(r['duration_s']) and r['duration_s']>=0
        for r in rows)
    checks['known_costs_and_no_technical_errors'] = valid_costs and not any(r.get('error_kind') for r in rows)
    checks['critical_examples'] = all(correct(r) for r in candidate if cases[r['case_id']]['critical'])
    base_correct, candidate_correct = sum(map(correct,base)),sum(map(correct,candidate))
    checks['overall_non_regression'] = candidate_correct>=base_correct
    checks['per_class_non_regression'] = all(
        sum(correct(r) for r in candidate if cases[r['case_id']]['expected']==label)>=
        sum(correct(r) for r in base if cases[r['case_id']]['expected']==label)
        for label in ('detected','not_detected','unknown'))
    checks['net_improvement'] = candidate_correct>base_correct
    if valid_costs:
        base_tokens,candidate_tokens = sum(r['tokens'] for r in base),sum(r['tokens'] for r in candidate)
        checks['token_cost'] = candidate_tokens<=base_tokens*POLICY['token_ratio']
        base_time = sum(r['duration_s'] for r in base)/max(1,len(base))
        candidate_time = sum(r['duration_s'] for r in candidate)/max(1,len(candidate))
        checks['latency'] = candidate_time<=base_time*POLICY['latency_ratio']+POLICY['latency_slack_s']
    else:
        base_tokens=candidate_tokens=base_time=candidate_time=None
        checks['token_cost']=checks['latency']=False
    total = len(candidate)
    metrics = {'trials_per_version':total,'baseline_correct':base_correct,'candidate_correct':candidate_correct,
        'baseline_accuracy':base_correct/total if total else None,
        'candidate_accuracy':candidate_correct/total if total else None,
        'baseline_tokens':base_tokens,'candidate_tokens':candidate_tokens,
        'baseline_mean_s':base_time,'candidate_mean_s':candidate_time}
    recurrence={}
    for failure_type in sorted({c['failure_type'] for c in cases.values()}):
        before=[r for r in base if cases[r['case_id']]['failure_type']==failure_type]
        after=[r for r in candidate if cases[r['case_id']]['failure_type']==failure_type]
        baseline_frr=1-sum(map(correct,before))/len(before)
        candidate_frr=1-sum(map(correct,after))/len(after)
        recurrence[failure_type]={'trials_per_version':len(before),
            'baseline_failure_rate':baseline_frr,'candidate_failure_rate':candidate_frr,
            'reduction_percentage_points':100*(baseline_frr-candidate_frr),
            'relative_reduction':(baseline_frr-candidate_frr)/baseline_frr if baseline_frr else None}
    metrics['failure_recurrence_by_type']=recurrence
    metrics['recurrence_scope']='Repeated labeled image trials, NOT robot end-to-end recurrence'
    failed = [k for k,v in checks.items() if not v]
    return {'passed':not failed,'checks':checks,'failed':failed,'metrics':metrics}
