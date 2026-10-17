"""Finite source screen exercises only owned system-temp evidence and mock HTTP."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/deepseek_source_screen.py'


def load_entry():
    assert SCRIPT.exists(), 'source screen runner is not implemented'
    spec = importlib.util.spec_from_file_location('source_screen_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(text='Full public answer\n', *, status='completed', model='deepseek-v4-pro', code=200):
    return httpx.Response(code, request=httpx.Request('POST', 'https://api.deepseek.com/responses'), json={
        'object': 'response', 'status': status, 'model': model,
        'output': [{'type': 'reasoning', 'content': 'PRIVATE'}, {'type': 'message', 'role': 'assistant',
                   'status': 'completed', 'content': [{'type': 'output_text', 'text': text}]}],
        'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}, 'secret': 'CREDENTIAL'})


@pytest.fixture
def entry(tmp_path, monkeypatch):
    module = load_entry()
    assets = module.candidate_assets()
    project = tmp_path / 'owned'
    report = project / module.REPORT.relative_to(ROOT)
    screen = project / module.SCREEN.relative_to(ROOT)
    group = project / '.planning/work/group.json'
    def write(path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(module.io.encoded(obj), encoding='utf-8', newline='\n')
    for name, value in {'PROJECT': project, 'REPORT': report, 'SCREEN': screen, 'CORPUS': screen / 'corpus',
                        'GROUP': group, 'SHARED_LOCK': project / 'shared.lock',
                        'RESULTS': report / 'results/phase-15', 'TRACKER': group.with_name('phase-15.json')}.items():
        monkeypatch.setattr(module, name, value)
    copied = []
    for original in assets:
        target = project / original.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original.read_bytes() if original.exists() else b'Offline review fixture\n')
        copied.append(target)
    monkeypatch.setattr(module, 'candidate_assets', lambda: copied)
    rows = []
    for n, count in enumerate((3, 1, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1, 1, 2), 1):
        phase = f'phase-{n}'
        out = report / 'results' / phase
        write(out / 'provenance.json', {'work_id': module.WORK_ID, 'phase': phase})
        write(out / 'request-ledger.json', {'work_id': module.WORK_ID, 'phase': phase,
              'requests': [{'ordinal': k, 'status': 'response'} for k in range(1, count + 1)]})
        write(out / 'result-index.json', {'work_id': module.WORK_ID, 'phase': phase, 'posts': count})
        receipt = {'work_id': module.WORK_ID, 'phase': phase, 'status': 'closed', 'posts': count,
                   'ledger_sha256': module.io.digest((out / 'request-ledger.json').read_bytes()),
                   'index_sha256': module.io.digest((out / 'result-index.json').read_bytes()),
                   'provenance_sha256': module.io.digest((out / 'provenance.json').read_bytes())}
        write(out / 'closed-receipt.json', receipt)
        tracker = {'work_id': module.WORK_ID, 'phase': phase, 'status': 'closed', 'reserved_posts': count,
                   'provenance_sha256': receipt['provenance_sha256'],
                   'closed_receipt_sha256': module.io.digest((out / 'closed-receipt.json').read_bytes())}
        path = group.with_name(phase + '.json')
        write(path, tracker)
        rows.append(tracker | {'tracker': str(path), 'ledger': str(out / 'request-ledger.json')})
    write(group, {'work_id': module.WORK_ID, 'budget_mode': 'uncapped', 'hard_ceiling': None,
                  'status': 'active', 'reserved_posts': 21, 'phases': rows, 'historical_parents': []})
    monkeypatch.setattr(module, 'runtime', lambda: pytest.fail('offline dotenv read'))
    module.bind()
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_full_sources_single_calls_preallocated_and_closed_replay(entry):
    before = {p: p.read_bytes() for p in entry.REPORT.rglob('*') if p.is_file()}
    assert entry.plan()['parent_posts'] == 21
    ready(entry)
    calls = []
    def post(url, **kw):
        calls.append(kw['json'])
        assert entry.read(entry.GROUP)['reserved_posts'] == 21 + len(calls)
        assert entry.read(entry.TRACKER)['reserved_posts'] == len(calls)
        assert entry.read(entry.RESULTS / 'request-ledger.json')['requests'][-1]['status'] == 'reserved'
        return response(f'Answer {len(calls)}\n')
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result['success'] and result['posts'] == 2
    for body, source in zip(calls, ('en-long-unseen.txt', 'zh-listening.txt')):
        assert body['input'][0]['content'].endswith((entry.CORPUS / source).read_bytes().decode())
        assert body['model'] == 'deepseek-v4-pro' and body['reasoning'] == {'effort': 'high'}
        assert body['max_output_tokens'] == 16384 and body['text'] == {'format': {'type': 'text'}}
        assert body['instructions'] == entry.legacy.SYSTEM
        assert '主题规划' not in body['input'][0]['content']
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert entry.verify()['work_posts'] == 23
    evidence = ''.join(p.read_text(encoding='utf-8') for p in entry.RESULTS.glob('response-*.json'))
    assert 'PRIVATE' not in evidence and 'CREDENTIAL' not in evidence
    (entry.PROJECT / entry.RUNNER_RELATIVE).write_text('live changed', encoding='utf-8')
    assert entry.verify()['evidence_hashes_verified']
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail('closed paid')))


@pytest.mark.parametrize('position', [1, 2])
@pytest.mark.parametrize('failure', ['network', 'incomplete', 'http', 'model', 'json'])
def test_first_error_closes_keeps_prior_sample_and_marks_skipped(entry, position, failure):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(kw)
        if len(calls) != position:
            return response()
        if failure == 'network':
            raise httpx.ConnectError('offline')
        if failure == 'json':
            return httpx.Response(200, text='invalid', request=httpx.Request('POST', entry.ENDPOINT))
        return response(status='incomplete' if failure == 'incomplete' else 'completed',
                        code=500 if failure == 'http' else 200, model='other' if failure == 'model' else entry.MODEL)
    result = entry.run(transport=SimpleNamespace(post=post))
    assert not result['success'] and result['posts'] == len(calls) == position
    assert len(result['samples']) == 2
    if position == 1:
        assert result['samples'][1]['skipped'] is True
    else:
        assert entry.read(entry.RESULTS / 'en-long-unseen.json')['success'] is True
    assert entry.verify()['stopped_on_error']


@pytest.mark.parametrize('target', ['payload', 'response', 'result', 'summary', 'parent', 'source', 'snapshot'])
def test_first_sample_drift_stops_before_second_reservation(entry, target, monkeypatch):
    ready(entry)
    original = entry.persist_result
    def corrupt(*args, **kw):
        answer = original(*args, **kw)
        paths = {'payload': entry.RESULTS / 'payload-01.json', 'response': entry.RESULTS / 'response-01.json',
                 'result': entry.RESULTS / 'en-long-unseen.json', 'summary': entry.RESULTS / 'en-long-unseen.md',
                 'parent': entry.REPORT / 'results/phase-14/provenance.json',
                 'source': entry.CORPUS / 'zh-listening.txt',
                 'snapshot': entry.RESULTS / entry.read(entry.RESULTS / 'provenance.json')['snapshots'][
                     entry.GROUP.with_name('phase-1.json').relative_to(entry.PROJECT).as_posix()]['file']}
        path = paths[target]
        path.write_bytes(path.read_bytes() + b' ')
        return answer
    monkeypatch.setattr(entry, 'persist_result', corrupt)
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: response()))
    assert result['posts'] == 1 and not result['success']
    assert entry.read(entry.GROUP)['reserved_posts'] == 22
    assert result['samples'][1]['skipped'] is True


def test_offline_actions_and_manifest_identity(entry, monkeypatch):
    monkeypatch.setattr(httpx.Client, 'post', lambda *a, **k: pytest.fail('offline network'))
    assert entry.plan()['network'] is False
    path = entry.CORPUS / 'manifest.json'
    original = path.read_bytes()
    path.write_bytes(original + b' ')
    with pytest.raises(RuntimeError, match='manifest'):
        entry.plan()
    path.write_bytes(original)
    ready(entry)
    assert entry.check()['dotenv_read'] is False


@pytest.mark.parametrize('drift', ['count', 'open', 'missing'])
def test_parent21_fourteen_closed_guard(entry, drift):
    group = entry.read(entry.GROUP)
    if drift == 'count':
        group['reserved_posts'] = 22
    elif drift == 'open':
        group['phases'][-1]['status'] = 'running'
    else:
        group['phases'].pop()
    entry.engine.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError):
        entry.plan()
    assert not entry.RESULTS.exists()


def test_root_and_mock_isolation_precede_writes(entry, monkeypatch):
    monkeypatch.delenv('CODEX_ACCEPTANCE_CALLER', raising=False)
    with pytest.raises(RuntimeError, match='root'):
        entry.run(caller='root')
    monkeypatch.setattr(entry, 'PROJECT', ROOT)
    with pytest.raises(RuntimeError, match='isolated'):
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail('mock escaped')))


def test_capacity_rejects_without_clipping():
    entry = load_entry()
    sample = {'title': 'T', 'attribution': 'A', 'license': 'L'}
    with pytest.raises(RuntimeError, match='60000'):
        entry.payload(sample, 'x' * 60001)
    sample['title'] = 'x' * 80000
    with pytest.raises(RuntimeError, match='80000'):
        entry.payload(sample, 'source')
