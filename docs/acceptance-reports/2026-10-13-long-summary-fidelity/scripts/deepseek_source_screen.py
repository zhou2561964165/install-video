"""Phase15: two unchanged Pro full-source requests; screening step 1 only.

Existing helpers own atomic accounting, shared locks and Responses filtering.
Protect closed evidence/env/accounts/models/UI; narrow one-way interfaces and
skill-first/UI three-tier-token engineering conventions continue to apply.
"""
import argparse
from contextlib import nullcontext
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types

spec = importlib.util.spec_from_file_location('source_screen_helpers', Path(__file__).with_name('planned_direct_delegate.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
legacy, base, engine, io = helpers.legacy, helpers.base, helpers.engine, helpers.io
PROJECT, REPORT = helpers.PROJECT, helpers.REPORT
SCREEN = REPORT.parent / '2026-10-16-deepseek-source-screen'
CORPUS = SCREEN / 'corpus'
GROUP, SHARED_LOCK, WORK_ID = helpers.GROUP, helpers.SHARED_LOCK, helpers.WORK_ID
PHASE, PARENT_POSTS, PHASE_POST_CAP = 'phase-15', 21, 2
RESULTS, TRACKER = REPORT / 'results' / PHASE, GROUP.with_name(PHASE + '.json')
RUNNER_RELATIVE = 'docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/deepseek_source_screen.py'
MODEL, ENDPOINT = 'deepseek-v4-pro', 'https://api.deepseek.com/responses'
MANIFEST_SHA = 'aa8e69b0ef9870385a79155899184db0fdc974e02049dd05c957ab1aaabd16ac'
SAMPLES = ('en-long-unseen', 'zh-listening-unseen')
read = engine.read


def bind():
    for name in ('PROJECT', 'REPORT', 'CORPUS', 'GROUP', 'SHARED_LOCK', 'WORK_ID', 'PHASE', 'RESULTS', 'TRACKER'):
        setattr(engine, name, globals()[name])
    base.native.PROJECT, base.native.RESULTS = PROJECT, RESULTS
    base.native.snapshot_bytes = snapshot_bytes


def safe_asset(path):
    path = Path(path).resolve()
    if (not path.is_relative_to(PROJECT.resolve()) or path.name.lower().startswith('.env')
            or 'credential' in path.name.lower() or path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.key', '.pem', '.p12'}):
        raise RuntimeError('Unsafe frozen asset')
    return path


def source_samples():
    path = safe_asset(CORPUS / 'manifest.json')
    if io.digest(path.read_bytes()) != MANIFEST_SHA:
        raise RuntimeError('Source manifest identity drift')
    samples = read(path)['samples']
    if tuple(row['id'] for row in samples) != SAMPLES:
        raise RuntimeError('Selected source order/identity drift')
    for sample in samples:
        raw = safe_asset(CORPUS / sample['file']).read_bytes()
        caption = safe_asset(CORPUS / sample['raw_path']).read_bytes()
        if (io.digest(raw) != sample['sha256'] or len(raw.decode('utf-8')) != sample['chars']
                or io.digest(caption) != sample['raw_sha256']):
            raise RuntimeError('Selected source hash/length drift')
        payload(sample, raw.decode('utf-8'))
    return samples


def payload(sample, source):
    if len(source) > 60000:
        raise RuntimeError('Source exceeds 60000 characters')
    # Preserve phase13 task body byte-for-byte; only its three metadata lines vary.
    before, metadata = legacy.TASK.split('标题：', 1)
    _, tail = metadata.split('\n\n完整字幕开始：', 1)
    task = (before + '标题：' + sample['title'] + '\n来源：' + sample['attribution']
            + '\n许可：' + sample['license'] + '，来源及派生材料保留署名。\n\n完整字幕开始：' + tail)
    body = {'model': MODEL, 'temperature': 0.2, 'instructions': legacy.SYSTEM,
            'input': [{'role': 'user', 'content': task + source}], 'max_output_tokens': 16384,
            'text': {'format': {'type': 'text'}}, 'reasoning': {'effort': 'high'}}
    if len(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))) > 80000:
        raise RuntimeError('Complete serialized payload exceeds 80000 characters')
    return body


def parent_paths(group):
    paths = []
    for row in group['phases']:
        paths.extend(engine.closed_binding(row, WORK_ID))
        # Bind raw/payload/result and auxiliary top-level evidence, not mutable docs.
        paths.extend(p for p in Path(row['ledger']).parent.iterdir() if p.is_file())
    for row in group.get('historical_parents', []):
        path = safe_asset(PROJECT / row['path'])
        if row.get('status') != 'closed' or io.digest(path.read_bytes()) != row['sha256']:
            raise RuntimeError('Historical parent drift')
        paths.append(path)
    return sorted(set(paths))


def parent_guard(group):
    if (group['status'] != 'active' or group['reserved_posts'] != 21
            or [r['phase'] for r in group['phases']] != [f'phase-{n}' for n in range(1, 15)]
            or any(r['status'] != 'closed' for r in group['phases'])
            or sum(r['reserved_posts'] for r in group['phases']) != 21):
        raise RuntimeError('Fresh phase15 requires fourteen closed phases and parent21')
    return parent_paths(group)


def candidate_assets():
    seen, paths = set(), set()
    def visit(module):
        if id(module) in seen:
            return
        seen.add(id(module))
        path = getattr(module, '__file__', None)
        if path is None or not Path(path).resolve().is_relative_to(Path(__file__).resolve().parents[4]):
            return
        paths.add(Path(path).resolve())
        for value in vars(module).values():
            if isinstance(value, types.ModuleType):
                visit(value)
    visit(helpers)
    paths.update([Path(__file__), PROJECT / 'backend/tests/test_deepseek_source_screen.py',
                  PROJECT / 'backend/app/services/llm_service.py', PROJECT / 'backend/app/config.py',
                  PROJECT / 'pyproject.toml', PROJECT / 'uv.lock', SCREEN / 'plan.md', SCREEN / 'review-criteria.md',
                  REPORT / 'unseen-review-criteria.md', REPORT / 'reviews/phase-15-deepseek-source-tool.md'])
    paths.update(CORPUS / name for name in ('manifest.json', 'en-long-unseen.txt', 'en-long-unseen.vtt',
                                          'zh-listening.txt', 'zh-listening.vtt'))
    return sorted(paths)


def plan():
    bind()
    parent_guard(engine.group_state(validate_history=False))
    return {'phase': PHASE, 'parent_posts': 21, 'planned_posts': 2, 'phase_post_cap': 2,
            'samples': source_samples(), 'network': False, 'dotenv_read': False,
            'model': MODEL, 'endpoint': ENDPOINT, 'max_output_tokens': 16384, 'timeout_seconds': 300,
            'format_posts': 0, 'semantic_posts': 0, 'extra_posts': 0}


def freeze():
    bind()
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError('Phase already allocated; never reopen')
        group = engine.group_state(validate_history=False)
        engine.allocation_guard(group)
        parents, samples = parent_guard(group), source_samples()
        assets = [(safe_asset(p), safe_asset(p).read_bytes()) for p in sorted(set(candidate_assets() + parents))]
        snapshots = {p.relative_to(PROJECT.resolve()).as_posix(): {'file': f'snapshots/{n:04d}.bin',
                     'sha256': io.digest(raw)} for n, (p, raw) in enumerate(assets, 1)}
        bodies = [payload(s, (CORPUS / s['file']).read_bytes().decode('utf-8')) for s in samples]
        frozen = {'work_id': WORK_ID, 'phase': PHASE, 'parent_posts': 21, 'planned_posts': 2, 'phase_post_cap': 2,
                  'budget_mode': 'uncapped', 'hard_ceiling': None, 'provider': 'deepseek', 'model': MODEL,
                  'endpoint': ENDPOINT, 'timeout_seconds': 300, 'http_retries': 0,
                  'format_posts': 0, 'semantic_posts': 0, 'extra_posts': 0, 'samples': samples,
                  'payloads': bodies, 'snapshots': snapshots, 'library_versions': helpers.versions(),
                  'group_at_freeze': group, 'parent_group_sha256': io.digest(GROUP.read_bytes()), 'frozen_utc': io.now()}
        RESULTS.mkdir(parents=True)
        io.exclusive(RESULTS / 'allocation.json', {'phase': PHASE, 'kind': 'owned_phase_allocation'})
        for path, raw in assets:
            target = RESULTS / snapshots[path.relative_to(PROJECT.resolve()).as_posix()]['file']
            target.parent.mkdir(exist_ok=True)
            helpers._write_bytes(target, raw)
        for n, body in enumerate(bodies, 1):
            io.exclusive(RESULTS / f'frozen-payload-{n:02d}.json', body)
        io.exclusive(RESULTS / 'provenance.json', frozen)
        io.exclusive(RESULTS / 'request-ledger.json', {'work_id': WORK_ID, 'phase': PHASE, 'planned_posts': 2, 'requests': []})
        tracker = {'work_id': WORK_ID, 'phase': PHASE, 'status': 'frozen', 'parent_posts': 21,
                   'reserved_posts': 0, 'planned_posts': 2, 'phase_post_cap': 2,
                   'budget_mode': 'uncapped', 'hard_ceiling': None, 'ledger': str(RESULTS / 'request-ledger.json'),
                   'provenance_sha256': io.digest((RESULTS / 'provenance.json').read_bytes())}
        io.exclusive(TRACKER, tracker)
        group['phases'].append({k: tracker[k] for k in ('phase', 'status', 'reserved_posts', 'planned_posts', 'ledger', 'provenance_sha256')} | {'tracker': str(TRACKER)})
        engine.durable(GROUP, group)
        return {'frozen': True, 'phase_post_cap': 2, 'network': False, 'dotenv_read': False}


def snapshot_bytes(frozen, path):
    record = frozen['snapshots'][safe_asset(path).relative_to(PROJECT.resolve()).as_posix()]
    target = (RESULTS / record['file']).resolve()
    if not target.is_relative_to((RESULTS / 'snapshots').resolve()):
        raise RuntimeError('Snapshot path escapes owned snapshots')
    raw = target.read_bytes()
    if io.digest(raw) != record['sha256']:
        raise RuntimeError('Frozen snapshot drift')
    return raw


def frozen_state(*, live):
    bind()
    frozen, ledger, tracker = [read(p) for p in (RESULTS / 'provenance.json', RESULTS / 'request-ledger.json', TRACKER)]
    if (any(o.get('work_id') != WORK_ID or o.get('phase') != PHASE or o.get('planned_posts') != 2 for o in (frozen, ledger, tracker))
            or any(frozen.get(k) != v for k, v in {'parent_posts': 21, 'phase_post_cap': 2, 'model': MODEL,
                'endpoint': ENDPOINT, 'timeout_seconds': 300, 'http_retries': 0, 'format_posts': 0, 'semantic_posts': 0, 'extra_posts': 0}.items())
            or tracker.get('parent_posts') != 21 or tracker.get('phase_post_cap') != 2
            or tracker.get('ledger') != str(RESULTS / 'request-ledger.json')
            or io.digest((RESULTS / 'provenance.json').read_bytes()) != tracker['provenance_sha256']):
        raise RuntimeError('Frozen identity/cap/options drift')
    for name, record in frozen['snapshots'].items():
        snapshot_bytes(frozen, PROJECT / name)
        if live and io.digest(safe_asset(PROJECT / name).read_bytes()) != record['sha256']:
            raise RuntimeError('Live frozen asset/parent drift')
    parent, rows = frozen['group_at_freeze'], ledger['requests']
    if io.digest(io.encoded(parent).encode('utf-8')) != frozen['parent_group_sha256']:
        raise RuntimeError('Parent group hash drift')
    group = engine.group_state(validate_history=False) if live else read(GROUP)
    owners = [r for r in group['phases'] if r['phase'] == PHASE]
    if (len(owners) != 1 or len(rows) > 2 or tracker['reserved_posts'] != len(rows)
            or owners[0]['reserved_posts'] != len(rows) or owners[0]['tracker'] != str(TRACKER)
            or owners[0]['ledger'] != tracker['ledger'] or owners[0]['provenance_sha256'] != tracker['provenance_sha256']
            or group['phases'][:14] != parent['phases'] or group['historical_parents'] != parent['historical_parents']
            or live and (len(group['phases']) != 15 or group['reserved_posts'] != 21 + len(rows))
            or not live and group['reserved_posts'] < 21 + len(rows)):
        raise RuntimeError('Phase/group reservation ownership drift')
    if live and (helpers.versions() != frozen['library_versions'] or source_samples() != frozen['samples']):
        raise RuntimeError('Live library/source drift')
    if tuple(s['id'] for s in frozen['samples']) != SAMPLES or len(frozen['payloads']) != 2:
        raise RuntimeError('Frozen selected sample drift')
    for n, sample in enumerate(frozen['samples'], 1):
        source = snapshot_bytes(frozen, CORPUS / sample['file'])
        if io.digest(source) != sample['sha256'] or len(source.decode('utf-8')) != sample['chars']:
            raise RuntimeError('Frozen source identity drift')
        body = read(RESULTS / f'frozen-payload-{n:02d}.json')
        if body != frozen['payloads'][n - 1] or body != payload(sample, source.decode('utf-8')):
            raise RuntimeError('Frozen complete payload drift')
    for n, row in enumerate(rows, 1):
        if row.get('ordinal') != n or row.get('sample') != SAMPLES[n - 1] or row.get('stage') != 'direct_pro_text' or row.get('sample_post') != 1:
            raise RuntimeError('Attempt sequence drift')
        for prefix, field in [('payload', 'payload_sha256'), ('response', 'response_sha256')]:
            path = RESULTS / f'{prefix}-{n:02d}.json'
            if row.get(field) and io.digest(path.read_bytes()) != row[field]:
                raise RuntimeError('Prior payload/raw drift')
        if read(RESULTS / f'payload-{n:02d}.json') != frozen['payloads'][n - 1]:
            raise RuntimeError('Actual payload differs')
        if row.get('result_sha256'):
            path = RESULTS / (row['sample'] + '.json')
            if io.digest(path.read_bytes()) != row['result_sha256']:
                raise RuntimeError('Prior result drift')
            result = read(path)
            if result.get('success') and (RESULTS / (row['sample'] + '.md')).read_bytes() != result['result']['text'].encode('utf-8'):
                raise RuntimeError('Prior summary drift')
    return frozen, ledger, tracker


def check():
    _, ledger, tracker = frozen_state(live=True)
    if tracker['status'] != 'frozen' or ledger['requests']:
        raise RuntimeError('Offline check only before first run')
    receipt = {'phase': PHASE, 'phase_post_cap': 2, 'provenance_sha256': tracker['provenance_sha256'], 'network': False, 'dotenv_read': False}
    path = RESULTS / 'offline-check.json'
    if path.exists() and read(path) != receipt:
        raise RuntimeError('Offline receipt drift')
    if not path.exists():
        io.exclusive(path, receipt)
    return receipt


def caller_guard(*, transport, caller):
    if transport is None:
        if caller != 'root' or os.environ.get('CODEX_ACCEPTANCE_CALLER') != 'root':
            raise RuntimeError('Real run requires root caller declaration')
    else:
        real, project, temp = Path(__file__).resolve().parents[4], PROJECT.resolve(), Path(tempfile.gettempdir()).resolve()
        if (project == temp or not project.is_relative_to(temp) or project.is_relative_to(real) or real.is_relative_to(project)
                or any(not p.resolve().is_relative_to(project) for p in (REPORT, SCREEN, CORPUS, GROUP, SHARED_LOCK, RESULTS, TRACKER))):
            raise RuntimeError('Mock run requires owned isolated system temp')


def runtime():
    settings, service, _ = base._live_runtime()
    if settings.llm_provider != 'deepseek' or service._endpoint(responses=True) != ENDPOINT or not settings.llm_api_key:
        raise RuntimeError('Explicit DeepSeek provider/endpoint/key required')
    return settings


def decode_response(raw, frozen):
    if raw.get('http_status') != 200 or raw.get('model') != MODEL:
        raise RuntimeError('Provider HTTP/model differs')
    base.native.responses_content(raw, frozen)
    return ''.join(p['text'] for item in raw['output'] for p in item['content'] if p['type'] == 'output_text')


def persist_result(sample, result, index):
    path = RESULTS / (sample['id'] + '.json')
    io.exclusive(path, result)
    checksum = io.digest(path.read_bytes())
    ledger = read(RESULTS / 'request-ledger.json')
    matching = [r for r in ledger['requests'] if r['sample'] == sample['id']]
    for row in matching:
        row['result_sha256'] = checksum
    engine.durable(RESULTS / 'request-ledger.json', ledger)
    index['samples'].append({'sample': sample['id'], 'success': result['success'], 'skipped': False,
                             'result_sha256': checksum, 'posts': len(matching)})


def close_phase(index, pending, frozen):
    """Close attempted accounting even when an old live evidence file drifted.

    Sending still requires live parent hashes. Closing uses the already-bound
    in-memory parent ownership validated before starting the run. Damaged live
    files or snapshots remain damaged evidence and cannot prevent the stop.
    """
    original = engine.closed_binding
    parents = {row['phase']: row for row in frozen['group_at_freeze']['phases']}
    def parent_binding(row, work_id):
        if row['phase'] == PHASE:
            return original(row, work_id)
        if work_id != WORK_ID or parents.get(row['phase']) != row:
            raise RuntimeError('Parent ownership changed during close')
        ledger = Path(row['ledger'])
        paths = [Path(row['tracker']), ledger, *(ledger.parent / name for name in (
            'closed-receipt.json', 'result-index.json', 'provenance.json'))]
        # Do not re-read possibly damaged evidence while recording a failure.
        # This callback does not certify it; frozen_state guards every POST and
        # verify still rejects snapshot corruption after the closed receipt.
        return paths
    engine.closed_binding = parent_binding
    try:
        engine.close_phase(index, pending)
    finally:
        engine.closed_binding = original


def run(*, transport=None, caller=None):
    caller_guard(transport=transport, caller=caller)
    bind()
    with io.directory_guard(SHARED_LOCK):
        frozen, ledger, tracker = frozen_state(live=True)
        if (tracker['status'] != 'frozen' or ledger['requests'] or (RESULTS / 'result-index.json').exists()
                or read(RESULTS / 'offline-check.json') != {'phase': PHASE, 'phase_post_cap': 2,
                    'provenance_sha256': tracker['provenance_sha256'], 'network': False, 'dotenv_read': False}):
            raise RuntimeError('Fresh checked phase required; never reopen')
        index = {'work_id': WORK_ID, 'phase': PHASE, 'posts': 0, 'stopped_on_error': False, 'samples': []}
        pending, active = None, None
        try:
            if transport is None:
                key = runtime().llm_api_key
                import httpx
                manager = httpx.Client(timeout=300, transport=httpx.HTTPTransport(retries=0))
            else:
                key, manager = 'offline-test-key', nullcontext(transport)
            with manager as http:
                for ordinal, sample in enumerate(frozen['samples'], 1):
                    active = None
                    current, ledger, tracker = frozen_state(live=True)
                    if len(ledger['requests']) != ordinal - 1 or ordinal > 2:
                        raise RuntimeError('Unplanned POST; finite cap2')
                    active = sample
                    body = current['payloads'][ordinal - 1]
                    io.exclusive(RESULTS / f'payload-{ordinal:02d}.json', body)
                    row = {'ordinal': ordinal, 'sample': sample['id'], 'sample_post': 1, 'stage': 'direct_pro_text',
                           'status': 'reserved', 'reserved_utc': io.now(),
                           'payload_sha256': io.digest((RESULTS / f'payload-{ordinal:02d}.json').read_bytes())}
                    pending = row
                    group = engine.group_state(validate_history=False)
                    group['reserved_posts'] += 1
                    next(r for r in group['phases'] if r['phase'] == PHASE).update(status='running', reserved_posts=ordinal)
                    ledger['requests'].append(row)
                    tracker.update(status='running', reserved_posts=ordinal)
                    engine.durable(GROUP, group)
                    engine.durable(RESULTS / 'request-ledger.json', ledger)
                    engine.durable(TRACKER, tracker)
                    response = http.post(ENDPOINT, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key}, json=body)
                    try:
                        raw = response.json()
                    except ValueError:
                        raw = None
                    safe = base.native.response_evidence(raw)
                    safe.update(http_status=response.status_code, received_utc=io.now(),
                                model=MODEL if isinstance(raw, dict) and raw.get('model') == MODEL else 'mismatch')
                    path = RESULTS / f'response-{ordinal:02d}.json'
                    io.exclusive(path, safe)
                    row.update(status='response', http_status=response.status_code, usage=safe.get('usage'),
                               response_sha256=io.digest(path.read_bytes()))
                    engine.durable(RESULTS / 'request-ledger.json', ledger)
                    pending = None
                    response.raise_for_status()
                    text = decode_response(safe, current)
                    helpers._write_bytes(RESULTS / (sample['id'] + '.md'), text.encode('utf-8'))
                    result = {'sample': sample['id'], 'source_sha256': sample['sha256'], 'success': True,
                              'result': {'text': text, 'provider': 'deepseek', 'model': MODEL}, 'semantic_quality_verified': False}
                    persist_result(sample, result, index)
                    active = None
        except BaseException as exc:
            index.update(stopped_on_error=True, phase_error_type=getattr(exc, 'error_type', type(exc).__name__))
            if active is not None and not (RESULTS / (active['id'] + '.json')).exists():
                persist_result(active, {'sample': active['id'], 'source_sha256': active['sha256'], 'success': False,
                    'error_type': index['phase_error_type'], 'semantic_quality_verified': False}, index)
        finally:
            for sample in frozen['samples'][len(index['samples']):]:
                index['samples'].append({'sample': sample['id'], 'success': False, 'skipped': True, 'posts': 0,
                                         'reason': 'Stopped before sample POST'})
            close_phase(index, pending, frozen)
        return index | {'success': not index['stopped_on_error'], 'semantic_quality_verified': False}


def verify():
    frozen, ledger, tracker = frozen_state(live=False)
    group = read(GROUP)
    engine.closed_binding(next(r for r in group['phases'] if r['phase'] == PHASE), WORK_ID)
    index, receipt = read(RESULTS / 'result-index.json'), read(RESULTS / 'closed-receipt.json')
    rows = ledger['requests']
    if (tracker['status'] != 'closed' or receipt['work_posts'] != 21 + len(rows)
            or [s['sample'] for s in index['samples']] != list(SAMPLES)
            or not index['stopped_on_error'] and len(rows) != 2):
        raise RuntimeError('Closed count/disposition differs')
    for sample, item in zip(frozen['samples'], index['samples']):
        matching = [r for r in rows if r['sample'] == sample['id']]
        path = RESULTS / (sample['id'] + '.json')
        if item.get('skipped'):
            if matching or path.exists() or item['posts'] != 0:
                raise RuntimeError('Skipped sample has attempted evidence')
            continue
        result = read(path)
        checksum = io.digest(path.read_bytes())
        if (item.get('result_sha256') != checksum or item['posts'] != len(matching) or item['success'] != result['success']
                or result['source_sha256'] != sample['sha256'] or any(r.get('result_sha256') != checksum for r in matching)):
            raise RuntimeError('Closed sample result drift')
        if result['success']:
            if len(matching) != 1 or matching[0]['status'] != 'response':
                raise RuntimeError('Successful sample lacks completed response')
            text = decode_response(read(RESULTS / f"response-{matching[0]['ordinal']:02d}.json"), frozen)
            if result['result'] != {'text': text, 'provider': 'deepseek', 'model': MODEL}:
                raise RuntimeError('Result differs from raw')
        elif 'result' in result or (RESULTS / (sample['id'] + '.md')).exists():
            raise RuntimeError('Failed sample exposed a result')
    return {'phase_closed': True, 'evidence_hashes_verified': True, 'posts': len(rows), 'work_posts': receipt['work_posts'],
            'stopped_on_error': index['stopped_on_error'], 'semantic_quality_verified': False, 'network': False, 'dotenv_read': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'freeze', 'check', 'run', 'verify'))
    parser.add_argument('--caller', choices=('root',))
    args = parser.parse_args(argv)
    print(json.dumps(globals()[args.action](caller=args.caller) if args.action == 'run' else globals()[args.action](), ensure_ascii=False))


if __name__ == '__main__':
    main()
