"""Offline A/B delegation: owned temp evidence, no dotenv or real HTTP."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/planned_direct_delegate.py'


def load_entry():
    assert SCRIPT.exists(), 'planned direct delegate is not implemented'
    spec = importlib.util.spec_from_file_location('planned_direct_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_serial_pipeline_preserves_complete_source_and_plan():
    entry = load_entry()
    source = 'source beginning\nsource ending'
    calls = []
    def send(stage, payload):
        calls.append((stage, payload))
        return json.dumps({'topics': ['First topic', 'Closing topic']}) if stage == 'plan' else '# Unmodified answer\n'
    result = entry.invoke(source, send=send)
    assert [stage for stage, _ in calls] == ['plan', 'generate']
    assert all(source in p['input'][0]['content'] for _, p in calls)
    assert 'First topic' in calls[1][1]['input'][0]['content']
    assert result == {'topics': ['First topic', 'Closing topic'], 'text': '# Unmodified answer\n'}


def response(text, *, status='completed', model='deepseek-v4-pro', http_status=200):
    body = {'object': 'response', 'status': status, 'model': model,
            'output': [{'type': 'reasoning', 'summary': [], 'content': 'PRIVATE-REASONING'},
                       {'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': text}]}],
            'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30},
            'credential': 'SHOULD-NOT-PERSIST'}
    return httpx.Response(http_status, json=body, request=httpx.Request('POST', 'https://api.deepseek.com/responses'))


@pytest.fixture
def entry(tmp_path, monkeypatch):
    module = load_entry()
    originals = module.candidate_assets()
    project = tmp_path / 'owned'
    report = project / 'docs/acceptance-reports/2026-10-13-long-summary-fidelity'
    corpus = project / 'docs/acceptance-reports/2026-10-04-natural-subtitle-quality/corpus'
    group_path = project / '.planning/work/call-group.json'
    group_path.parent.mkdir(parents=True)
    corpus.mkdir(parents=True)
    for filename in ('manifest.json', 'en-long.txt', 'en-long.vtt'):
        (corpus / filename).write_bytes((module.CORPUS / filename).read_bytes())
    for name, value in {'PROJECT': project, 'REPORT': report, 'CORPUS': corpus,
                        'GROUP': group_path, 'SHARED_LOCK': project / 'shared.lock',
                        'RESULTS': report / 'results/phase-14', 'TRACKER': group_path.with_name('phase-14.json')}.items():
        monkeypatch.setattr(module, name, value)
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(module.io.encoded(value), encoding='utf-8', newline='\n')
    rows = []
    source = (corpus / 'en-long.txt').read_bytes()
    for n, count in enumerate((3, 1, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1, 1), 1):
        phase = f'phase-{n}'
        out = report / 'results' / phase
        provenance = {'work_id': module.WORK_ID, 'phase': phase}
        requests = [{'ordinal': i, 'status': 'response'} for i in range(1, count + 1)]
        result_index = {'work_id': module.WORK_ID, 'phase': phase, 'posts': count, 'stopped_on_error': False}
        if n == 13:
            request = {'input': [{'role': 'user', 'content': module.legacy.TASK + source.decode('utf-8')}],
                       'instructions': module.legacy.SYSTEM}
            provenance.update(source_sha256=module.SOURCE_SHA, source_chars=34894, payload=request)
            write(out / 'payload-01.json', request)
            write(out / 'response-01.json', {'http_status': 200, 'model': module.MODEL})
            write(out / 'en-long.json', {'success': True})
            requests[0].update(payload_sha256=module.io.digest((out / 'payload-01.json').read_bytes()),
                               response_sha256=module.io.digest((out / 'response-01.json').read_bytes()),
                               result_sha256=module.io.digest((out / 'en-long.json').read_bytes()))
            result_index['samples'] = [{'result_sha256': requests[0]['result_sha256']}]
            (out / 'full-transcript.txt').write_bytes(source)
        write(out / 'provenance.json', provenance)
        write(out / 'request-ledger.json', {'work_id': module.WORK_ID, 'phase': phase, 'requests': requests})
        write(out / 'result-index.json', result_index)
        receipt = {'work_id': module.WORK_ID, 'phase': phase, 'status': 'closed', 'posts': count,
                   'ledger_sha256': module.io.digest((out / 'request-ledger.json').read_bytes()),
                   'index_sha256': module.io.digest((out / 'result-index.json').read_bytes()),
                   'provenance_sha256': module.io.digest((out / 'provenance.json').read_bytes())}
        write(out / 'closed-receipt.json', receipt)
        tracker = {'work_id': module.WORK_ID, 'phase': phase, 'status': 'closed', 'reserved_posts': count,
                   'provenance_sha256': receipt['provenance_sha256'],
                   'closed_receipt_sha256': module.io.digest((out / 'closed-receipt.json').read_bytes())}
        tracker_path = group_path.with_name(phase + '.json')
        write(tracker_path, tracker)
        rows.append(tracker | {'tracker': str(tracker_path), 'ledger': str(out / 'request-ledger.json')})
    write(group_path, {'work_id': module.WORK_ID, 'budget_mode': 'uncapped', 'hard_ceiling': None,
                       'status': 'active', 'reserved_posts': 19, 'phases': rows, 'historical_parents': []})
    assets = []
    for original in originals:
        relative = original.resolve().relative_to(ROOT)
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original.read_bytes() if original.exists() else b'Offline review fixture\n')
        assets.append(target)
    monkeypatch.setattr(module, 'candidate_assets', lambda: assets)
    monkeypatch.setattr(module, 'runtime', lambda: pytest.fail('Mock/offline read dotenv'))
    module.bind()
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_two_calls_preallocate_then_closed_offline_replay(entry):
    old = {p: p.read_bytes() for p in entry.REPORT.rglob('*') if p.is_file()}
    ready(entry)
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs['json'])
        assert entry.read(entry.GROUP)['reserved_posts'] == 19 + len(calls)
        row = entry.read(entry.RESULTS / 'request-ledger.json')['requests'][-1]
        assert row['status'] == 'reserved'
        assert entry.read(entry.TRACKER)['reserved_posts'] == len(calls)
        if len(calls) == 1:
            return response('{"topics":["  Course roadmap  ","Final concepts"]}')
        assert entry.read(entry.RESULTS / 'accepted-plan.json')['topics'] == ['Course roadmap', 'Final concepts']
        return response('# Full answer\n\nEnd.\n')
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result['success'] and result['posts'] == len(calls) == 2
    assert calls[0]['reasoning'] == {'effort': 'none'}
    assert calls[0]['max_output_tokens'] == 4096
    assert calls[1]['reasoning'] == {'effort': 'high'}
    assert calls[1]['max_output_tokens'] == 16384
    source = (entry.CORPUS / 'en-long.txt').read_bytes().decode('utf-8')
    assert all(p['input'][0]['content'].endswith(source) for p in calls)
    assert (entry.RESULTS / 'pro-summary.md').read_bytes() == b'# Full answer\n\nEnd.\n'
    assert all(p.read_bytes() == raw for p, raw in old.items())
    assert entry.verify()['posts'] == 2
    text = '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in entry.RESULTS.glob('response-*.json'))
    assert 'PRIVATE-REASONING' not in text and 'SHOULD-NOT-PERSIST' not in text
    # Closed replay uses snapshots, not changed live candidate/parent inputs.
    (entry.PROJECT / entry.RUNNER_RELATIVE).write_text('live drift', encoding='utf-8')
    (entry.REPORT / 'results/phase-13/payload-01.json').write_text('parent drift', encoding='utf-8')
    assert entry.verify()['evidence_hashes_verified']
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail('Closed phase paid')))


@pytest.mark.parametrize('raw', ['{"topics":[]}', '{"topics":[1]}', '{"topics":[" "]}',
    '{"topics":["A"," a "]}', '{"topics":["A"],"facts":[]}',
    '{"topics":["A"],"topics":["B"]}', json.dumps({'topics': ['a' * 121]}),
    json.dumps({'topics': [str(i) for i in range(13)]}), '```json\n{"topics":["A"]}\n```'])
def test_invalid_plan_stops_after_first_billed_attempt(entry, raw):
    ready(entry)
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return response(raw)
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result['posts'] == len(calls) == 1 and not result['success']
    assert not (entry.RESULTS / 'accepted-plan.json').exists()
    assert not (entry.RESULTS / 'pro-summary.md').exists()
    assert entry.verify()['stopped_on_error']


@pytest.mark.parametrize('position', [1, 2])
@pytest.mark.parametrize('failure', ['network', 'incomplete', 'model', 'http', 'json'])
def test_terminal_transport_failures_keep_prior_evidence(entry, position, failure):
    ready(entry)
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) != position:
            return response('{"topics":["Accepted"]}')
        if failure == 'network':
            raise httpx.ConnectError('offline failure')
        if failure == 'json':
            return httpx.Response(200, text='bad json', request=httpx.Request('POST', entry.ENDPOINT))
        return response('x', status='incomplete' if failure == 'incomplete' else 'completed',
                        model='other' if failure == 'model' else entry.MODEL,
                        http_status=503 if failure == 'http' else 200)
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result['posts'] == len(calls) == position and not result['success']
    if position == 2:
        assert entry.read(entry.RESULTS / 'accepted-plan.json') == {'topics': ['Accepted']}
    assert entry.verify()['stopped_on_error']


def test_offline_actions_never_load_runtime_or_network(entry, monkeypatch):
    monkeypatch.setattr(httpx.Client, 'post', lambda *a, **kw: pytest.fail('Offline HTTP'))
    assert entry.plan()['dotenv_read'] is False
    assert not entry.RESULTS.exists()
    ready(entry)
    assert entry.check()['network'] is False


@pytest.mark.parametrize('target', ['source', 'runner', 'parent', 'template', 'schema', 'group'])
def test_drift_before_run_never_reserves(entry, target):
    ready(entry)
    paths = {'source': entry.CORPUS / 'en-long.txt', 'runner': entry.PROJECT / entry.RUNNER_RELATIVE,
             'parent': entry.REPORT / 'results/phase-13/en-long.json',
             'template': entry.RESULTS / 'templates.json', 'schema': entry.RESULTS / 'planning-schema.json',
             'group': entry.GROUP}
    path = paths[target]
    if target == 'group':
        state = entry.read(path)
        state['reserved_posts'] = 20
        path.write_text(entry.io.encoded(state), encoding='utf-8')
    else:
        path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail('Drift paid')))
    assert entry.read(entry.RESULTS / 'request-ledger.json')['requests'] == []


def test_second_request_plan_drift_closes_without_second_reservation(entry, monkeypatch):
    ready(entry)
    original = entry.invoke
    def invoke(*a, **kwargs):
        accept = kwargs['accept_plan']
        def corrupt(value):
            accept(value)
            (entry.RESULTS / 'accepted-plan.json').write_text('{"topics":["Changed"]}', encoding='utf-8')
        kwargs['accept_plan'] = corrupt
        return original(*a, **kwargs)
    monkeypatch.setattr(entry, 'invoke', invoke)
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: response('{"topics":["Original"]}')))
    assert result['posts'] == 1 and not result['success']
    assert entry.read(entry.GROUP)['reserved_posts'] == 20


def test_root_and_mock_isolation_guards_precede_any_write(entry, monkeypatch):
    monkeypatch.delenv('CODEX_ACCEPTANCE_CALLER', raising=False)
    with pytest.raises(RuntimeError, match='root'):
        entry.run(caller='root')
    monkeypatch.setattr(entry, 'PROJECT', ROOT)
    with pytest.raises(RuntimeError, match='isolated'):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail('Mock escaped')))


def test_real_lcel_construction_and_invocation_disable_tracing(monkeypatch):
    from langsmith import get_tracing_context
    entry = load_entry()
    monkeypatch.setenv('LANGSMITH_TRACING', 'true')
    constructor = entry.RunnableSequence
    observed = []
    def sequence(*a, **kwargs):
        observed.append(get_tracing_context()['enabled'])
        return constructor(*a, **kwargs)
    monkeypatch.setattr(entry, 'RunnableSequence', sequence)
    def send(stage, body):
        observed.append(get_tracing_context()['enabled'])
        return '{"topics":["A"]}' if stage == 'plan' else 'answer'
    entry.invoke('source', send=send)
    assert observed == [False, False, False]


def test_capacity_rejects_before_any_send(monkeypatch):
    entry = load_entry()
    with pytest.raises(RuntimeError, match='60000'):
        entry.invoke('a' * 60001, send=lambda *a: pytest.fail('Oversize paid'))
    monkeypatch.setattr(entry, 'PAYLOAD_LIMIT', 100)
    with pytest.raises(RuntimeError, match='80000'):
        entry.invoke('short', send=lambda *a: pytest.fail('Payload oversize paid'))
