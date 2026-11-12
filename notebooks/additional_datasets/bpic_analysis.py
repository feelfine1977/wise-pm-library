"""Source binding and presentation for the BPIC analysis notebooks.

WISE computes constraints, scores, coverage, grouped quantities, priorities,
signed explanations and shortlist overlap. Readers preserve source records;
case-month and observed-span labels are data-preparation context only.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import pandas as pd
import wise
from wise.evaluation import data
from wise.evaluation.adapters.xes import iter_traces, local
from wise.evaluation.replay import residual

BASE = Path(__file__).parent


def specifications():
    return json.loads((BASE / 'bpic_datasets.json').read_text())['datasets']


def _value(element):
    value = element.get('value')
    kind = local(element.tag)
    if kind == 'boolean':
        return value == 'true'
    if kind in ('int', 'float'):
        try:
            return int(value) if kind == 'int' else float(value)
        except (ValueError, TypeError):
            return None
    return value


def _source(folder, name):
    if not name or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Input bindings must be relative to the supplied data folder.')
    path = folder / name
    if not path.is_file():
        raise ValueError('The configured source is unavailable in the supplied data folder.')
    return path


def _xes_frame(path, schema):
    attributes = schema['case_attributes']
    selected = set([schema['activity'], schema['timestamp'], 'lifecycle:transition',
                    *attributes, *schema.get('qualified_fields', [])])
    rows = []
    for trace in iter_traces(path):
        context = {e.get('key'): _value(e) for e in trace if local(e.tag) != 'event'}
        for event in trace:
            if local(event.tag) != 'event':
                continue
            row = {k: context.get(k, context.get(k.removeprefix('case:'))) for k in attributes}
            locations = schema.get('context_locations', {})
            row.update({e.get('key'): _value(e) for e in event
                        if e.get('key') in selected
                        and locations.get(e.get('key')) != 'trace'})
            row[schema['case_id']] = context.get('concept:name')
            rows.append(row)
    return pd.DataFrame(rows)


def _read_frame(entry, folder):
    schema = entry['source_schema']
    path = _source(folder, schema['path'])
    binding_notes = []
    if schema['format'] == 'xes':
        frame = _xes_frame(path, schema)
    else:
        frame = pd.read_csv(path, sep=schema.get('delimiter', ','),
                            encoding='utf-8-sig', low_memory=False)
        for join in schema.get('joins', []):
            other = pd.read_csv(_source(folder, join['source_path']), sep=';',
                                encoding='utf-8-sig', low_memory=False)
            fields = [join['key'], *join['context']]
            if any(k not in other for k in fields):
                raise ValueError('The context extract does not match its field binding.')
            key_present = other[join['key']].notna() & other[join['key']].astype(str).str.strip().ne('')
            binding_notes.append(dict(context_file=Path(join['source_path']).name,
                                      context_sha256=data.sha256(_source(folder, join['source_path'])),
                                      source_rows=len(other),
                                      rows_without_join_key=int((~key_present).sum()),
                                      unmatched_event_cases=int(frame.loc[
                                          ~frame[join['key']].isin(other.loc[key_present, join['key']]),
                                          join['key']].nunique())))
            source_rows = len(frame)
            frame = frame.merge(other.loc[key_present, fields], on=join['key'],
                                how='left', validate='many_to_one')
            if len(frame) != source_rows:
                raise ValueError('The context join changed the source event population.')
    qualified = schema.get('qualified_fields', [])
    if qualified:
        frame[schema['activity']] = frame[qualified].fillna('').astype(str).agg(
            schema.get('qualified_separator', '|').join, axis=1)
    frame.attrs['source_binding_notes'] = binding_notes
    return frame


def _group_keys(frame, keys):
    """Give mixed typed context values distinct, sortable display keys.

    This changes a grouping copy only. Original context values remain available
    in the case carrier and the source witness.
    """
    grouped = frame.copy()
    for key in keys:
        values = grouped[key]
        if len({type(value) for value in values.dropna()}) > 1:
            grouped[key] = values.astype(object).map(
                lambda value: None if pd.isna(value) else f'{type(value).__name__}: {value}')
    return grouped


def _grouped_result(result, keys):
    return replace(result, cases=_group_keys(result.cases, keys))


def _context(result):
    cases = result.cases.copy()
    cases['case_start_month'] = cases['first_ts'].dt.strftime('%Y-%m')
    cases['last_observed_month'] = cases['last_ts'].dt.strftime('%Y-%m')
    span = (cases['last_ts'] - cases['first_ts']) / pd.Timedelta(days=1)
    cases['observed_span_band'] = pd.cut(
        span, [-1, 1, 7, 30, 90, 365, float('inf')],
        labels=['under 1 day', '1–7 days', '7–30 days', '30–90 days',
                '90–365 days', '365 days or more'], right=False)
    cases['case_review'] = cases.index
    return replace(result, cases=cases)


def _run(entry, folder):
    started = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    path = _source(folder, entry['source_schema']['path'])
    record = dict(dataset=entry['dataset_id'], started_utc=started,
                  source_file=path.name, source_sha256=data.sha256(path),
                  source_bytes=path.stat().st_size, wise_version=wise.__version__,
                  policy_status='Draft diagnostic cut points; process-owner review required')
    run = dict(record=record, specification=entry, data_folder=folder)
    frame = _read_frame(entry, folder)
    record['source_binding_notes'] = frame.attrs.get('source_binding_notes', [])
    if entry['norm'] is None:
        record.update(status='context extract', source_rows=len(frame),
                      note='Case extract; no event sequence or synthetic events created.')
        run['context_extract'] = frame
    else:
        schema = entry['source_schema']
        record['bound_event_rows'] = len(frame)
        attributes = list(dict.fromkeys([*schema['case_attributes'],
                                       *[k for j in schema.get('joins', []) for k in j['context']]]))
        for name in attributes:
            if name not in frame:
                frame[name] = None
        log = wise.EventLog(frame, case_col=schema['case_id'], activity_col=schema['activity'],
                            timestamp_col=schema['timestamp'], case_attributes=attributes,
                            utc=True, timestamp_format=schema.get('timestamp_format'),
                            missing_timestamps='keep')
        norm = wise.Norm.from_dict(entry['norm'])
        result = _context(wise.score(log, norm))
        varying = dict(log.varying_case_attributes)
        groups = schema['group_by']
        if any(k in varying for k in groups):
            groups = ['case_start_month']
            record['grouping_note'] = 'Changing source attributes are not collapsed into a stable case label.'
        record.update(status='computed', events=len(log.events), cases=len(log.case_ids),
                      activities=len(log.activity_labels), norm_fingerprint=norm.fingerprint(),
                      grouping=groups, varying_case_attributes=varying,
                      unobserved_norm_labels=sorted(set(norm.activities()) - set(log.activity_labels)),
                      decomposition_residual=result.check_decomposition())
        run.update(log=log, norm=norm, result=result, grouping=groups)
        run['backlogs'] = {v: priorities(run, v) for v in result.views}
        run['signed'] = {v: wise.layer_contributions(
                            _grouped_result(result, list(b.spec.by)), b)
                         for v, b in run['backlogs'].items()}
    record.update(completed_utc=datetime.now(timezone.utc).isoformat(),
                  execution_seconds=time.perf_counter() - timer)
    return run


def challenge(year, data_folder=None):
    """Read every configured extract of one challenge, retaining whole cases."""
    folder = data.data_folder(data_folder)
    entries = [x for x in specifications() if x['challenge'] == int(year)]
    if not entries:
        raise ValueError('This challenge uses its existing dataset notebook.')
    return {x['dataset_id']: _run(x, folder) for x in entries}


def summary(runs):
    return pd.DataFrame([r['record'] for r in runs.values()]).drop(
        columns=['data_folder'], errors='ignore')


def norm_table(run):
    return pd.DataFrame(run['specification']['norm']['constraints'])


def priorities(run, view=None, gamma=0, by=None):
    result = run['result']
    view = view or result.views[0]
    keys = by or run['grouping']
    keys = [keys] if isinstance(keys, str) else list(keys)
    varying = run['record']['varying_case_attributes']
    if any(k in varying for k in keys):
        raise ValueError('Choose an explicit context-time policy before grouping by a changing attribute.')
    return wise.prioritize(_grouped_result(result, keys), by=keys, view=view, gamma=gamma)


def explanations(run, backlog):
    result = _grouped_result(run['result'], list(backlog.spec.by))
    return dict(contributions=wise.layer_contributions(result, backlog),
                drivers=wise.layer_drivers(result, backlog))


def _aggregate(series, volume='cases'):
    frame = pd.DataFrame({'value': series, 'population': 'All cases', 'zero': 0.0})
    return wise.prioritize(frame, by='population', score_col='value', volume=volume).table.iloc[0]


def _total(series):
    frame = pd.DataFrame({'quantity': series.astype(float), 'population': 'All cases', 'zero': 0.0})
    return wise.prioritize(frame, by='population', score_col='zero', volume='quantity').table.iloc[0]['volume']


def criterion_summary(run):
    rows = []
    for criterion in run['norm'].constraints:
        ev = wise.evaluate(criterion, run['log'])
        scope = ev.in_scope
        evaluated = int(_total(ev.value.notna()))
        scoped = int(_total(scope))
        mean = _aggregate(ev.value)['mean_score'] if evaluated else float('nan')
        coverage = (_aggregate(ev.value.notna().loc[scope].astype(float))['mean_score']
                    if scoped else float('nan'))
        row = dict(criterion_id=criterion.id, layer=criterion.layer,
                   evaluated_cases=evaluated, in_scope_cases=scoped,
                   mean_severity=mean, evidence_coverage=coverage,
                   description=criterion.description)
        reason_frame = pd.DataFrame({'reason': ev.reason, 'score': 0.0})
        reasons = wise.prioritize(reason_frame, by='reason').table
        row.update({f'reason_{key}': int(value) for key, value in reasons['n_cases'].items()})
        rows.append(row)
    return pd.DataFrame(rows)


def activity_summary(run, labels=None):
    rows = []
    for activity in labels if labels is not None else run['log'].activity_labels:
        count = run['log'].count(activity)
        presence = wise.evaluate(wise.Presence(activity), run['log'])
        rows.append(dict(activity=activity, occurrences=int(_total(count)),
                         observed_cases=int(_total(presence.value.eq(0)))))
    return pd.DataFrame(rows).sort_values('occurrences', ascending=False, kind='stable').reset_index(drop=True)


def context_profiles(run, attributes=None):
    cases = run['result'].cases
    attributes = attributes or [*run['grouping'], 'case_start_month',
                                'last_observed_month', 'observed_span_band']
    rows = []
    for attribute in dict.fromkeys(attributes):
        if attribute not in cases or attribute in run['record']['varying_case_attributes']:
            continue
        frame = _group_keys(cases[[attribute]], [attribute])
        frame['score'] = 0.0
        table = wise.prioritize(frame, by=attribute).table
        for key, row in table.iterrows():
            rows.append(dict(attribute=attribute, value=key, cases=int(row['n_cases'])))
    return pd.DataFrame(rows)


def view_agreement(run, k=10):
    backlogs = run['backlogs']
    return pd.DataFrame({a: {b: wise.top_k_overlap(x, y, k=k)
                            for b, y in backlogs.items()} for a, x in backlogs.items()})


def threshold_sensitivity(run, factors=(0.5, 1, 2)):
    rows = []
    for factor in factors:
        document = json.loads(run['norm'].dumps())
        for criterion in document['constraints']:
            params = criterion['params']
            if criterion['type'] == 'lag':
                params['delta'] *= factor
                params['width'] *= factor
            elif criterion['type'] == 'singularity':
                params['K'] *= factor
        alternative = wise.Norm.from_dict(document)
        scored = _context(wise.score(run['log'], alternative))
        for view in scored.views:
            backlog = wise.prioritize(_grouped_result(scored, run['grouping']),
                                     by=run['grouping'], view=view)
            aggregate = _aggregate(scored.scores[view])
            rows.append(dict(factor=factor, view=view, mean_score=aggregate['mean_score'],
                             scored_cases=int(aggregate['n_cases']),
                             top10_overlap=wise.top_k_overlap(run['backlogs'][view], backlog, k=10),
                             leading_slice=str(backlog.table.index[0]),
                             leading_priority=float(backlog.table.iloc[0]['PI']),
                             norm_fingerprint=alternative.fingerprint()))
    return pd.DataFrame(rows)


def integrity(run):
    again = wise.score(run['log'], wise.Norm.loads(run['norm'].dumps()))
    return dict(norm_roundtrip_residual=residual(run['result'].scores, again.scores),
                layer_decomposition_residual=run['result'].check_decomposition(),
                source_events_retained=len(run['log'].events),
                all_bound_source_rows_retained=(len(run['log'].events) ==
                                                run['record']['bound_event_rows']),
                evaluated_case_index_matches=run['result'].scores.index.equals(run['log'].case_ids))


def case_evidence(run, case_id=None, criterion=None):
    if criterion is None:
        criterion = run['norm'].constraints[0].id
    nc = run['norm'].get_constraint(criterion)
    ev = wise.evaluate(nc, run['log'])
    if case_id is None:
        candidates = ev.value.dropna().sort_values(ascending=False, kind='stable')
        case_id = candidates.index[0] if len(candidates) else run['log'].case_ids[0]
    schema = run['specification']['source_schema']
    path = _source(run['data_folder'], schema['path'])
    context = {}
    rows = []
    if schema['format'] == 'xes':
        for trace in iter_traces(path):
            values = {e.get('key'): _value(e) for e in trace if local(e.tag) != 'event'}
            if str(values.get('concept:name')) != str(case_id):
                continue
            context = values
            rows = [{e.get('key'): _value(e) for e in event}
                    for event in trace if local(event.tag) == 'event']
            break
    else:
        frame = pd.read_csv(path, sep=schema.get('delimiter', ','),
                            encoding='utf-8-sig', low_memory=False)
        rows = frame.loc[frame[schema['case_id']].eq(case_id)].to_dict(orient='records')
        context = run['result'].cases.loc[case_id].to_dict()
    evaluations = []
    for item in run['norm'].constraints:
        evaluated = wise.evaluate(item, run['log'])
        evaluations.append(dict(criterion_id=item.id, severity=evaluated.value.loc[case_id],
                                reason=str(evaluated.reason.loc[case_id])))
    return dict(case_id=case_id, selection='Purposive high-severity case; not a representative sample',
                events=pd.DataFrame(rows), case_context=pd.Series(context),
                evaluation=pd.DataFrame(evaluations),
                assessment=pd.DataFrame([
                    dict(view=view, compliance_score=run['result'].scores.loc[case_id, view],
                         weighted_evidence_coverage=run['result'].coverage(view).loc[case_id])
                    for view in run['result'].views]))


def plot_overview(run):
    import matplotlib.pyplot as plt
    figures = []
    for view, backlog in run['backlogs'].items():
        table = backlog.table.head(8)
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.barh([str(k) for k in table.index][::-1], table['PI'].tolist()[::-1], color='#376681')
        ax.set(title=f'{run["record"]["dataset"]}: {view}', xlabel='Priority Index under the diagnostic norm')
        fig.tight_layout()
        figures.append(fig)
    view = next(iter(run['backlogs']))
    key = run['backlogs'][view].table.index[0]
    row = run['signed'][view].loc[key]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.barh(list(row.index), row.tolist(), color=['#a86c32' if x >= 0 else '#528270' for x in row])
    ax.axvline(0, color='#444', linewidth=0.8)
    ax.set(title=f'{key}: signed layer explanation', xlabel='Signed contribution to the assessed gap')
    fig.tight_layout()
    figures.append(fig)
    table = criterion_summary(run)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].barh(table['criterion_id'], table['mean_severity'], color='#9a6236')
    axes[0].set(xlabel='Mean severity among evaluated cases', xlim=(0, 1))
    axes[1].barh(table['criterion_id'], table['evidence_coverage'], color='#386c83')
    axes[1].set(xlabel='Evaluated / in-scope cases', xlim=(0, 1))
    fig.tight_layout()
    figures.append(fig)
    return figures


def plot_case_timeline(run, case_id=None):
    """Display library-returned event timestamps without implying tie order."""
    import matplotlib.dates as dates
    import matplotlib.pyplot as plt
    if case_id is None:
        evaluation = wise.evaluate(run['norm'].constraints[0], run['log'])
        ranked = evaluation.value.dropna().sort_values(ascending=False, kind='stable')
        case_id = ranked.index[0] if len(ranked) else run['log'].case_ids[0]
    events = run['log'].trace(case_id)
    schema = run['specification']['source_schema']
    activity, timestamp = schema['activity'], schema['timestamp']
    focus = set(run['norm'].activities())
    lanes = events[activity].map(lambda value: value if value in focus else 'Other recorded activities')
    available = events[timestamp].notna()
    labels = list(dict.fromkeys(lanes))
    fig, ax = plt.subplots(figsize=(12, max(3, len(labels) * 0.45)))
    for label in labels:
        selected = available & lanes.eq(label)
        ax.scatter(events.loc[selected, timestamp], [label] * int(selected.sum()),
                   s=30, alpha=0.7, color='#406e89' if label in focus else '#999999')
    locator = dates.AutoDateLocator(minticks=3, maxticks=7)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(dates.ConciseDateFormatter(locator))
    ax.set(title=f'{run["record"]["dataset"]}: recorded case {case_id}',
           xlabel='Recorded event time (UTC); coincident points do not imply order',
           ylabel='Activity')
    fig.tight_layout()
    return fig


def journal(runs):
    rows = []
    for run in runs.values():
        record = run['record']
        rows.extend([
            dict(dataset=record['dataset'], phase='Extraction', decision='Use the bound source extract',
                 evidence=record['source_sha256'], status=record['status']),
            dict(dataset=record['dataset'], phase='Data Processing',
                 decision='Retain all source events of each selected case; declare context-time policy',
                 evidence=str(record.get('varying_case_attributes', {})), status='Recorded'),
            dict(dataset=record['dataset'], phase='Mining & Analysis',
                 decision='Evaluate explicit native diagnostic constraints with WISE',
                 evidence=record.get('norm_fingerprint', 'Context extract only'), status=record['status']),
            dict(dataset=record['dataset'], phase='Evaluation',
                 decision='Inspect source witnesses, coverage, view and cut-point sensitivity',
                 evidence='Notebook tables and figures', status='Review alongside execution'),
            dict(dataset=record['dataset'], phase='Process Improvement & Support',
                 decision='Agree a process change and balancing outcomes with its owner',
                 evidence='Notebook improvement plan', status='Process-owner review pending'),
        ])
    return pd.DataFrame(rows)


def save_outputs(runs, destination):
    import matplotlib.pyplot as plt
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    summary(runs).to_json(target / 'execution_record.json', orient='records', indent=2)
    journal(runs).to_csv(target / 'analysis_journal.csv', index=False)
    for run in runs.values():
        if 'result' not in run:
            continue
        folder = target / run['record']['dataset']
        folder.mkdir(exist_ok=True)
        criterion_summary(run).to_csv(folder / 'criteria.csv', index=False)
        context_profiles(run).to_csv(folder / 'case_context.csv', index=False)
        for view, backlog in run['backlogs'].items():
            backlog.table.to_csv(folder / f'priorities_{view}.csv')
            run['signed'][view].to_csv(folder / f'signed_layers_{view}.csv')
        for number, figure in enumerate(plot_overview(run), 1):
            figure.savefig(folder / f'figure_{number}.png', dpi=170)
            plt.close(figure)
