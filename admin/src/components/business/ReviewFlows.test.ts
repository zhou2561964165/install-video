import { describe, expect, it, vi } from 'vitest';
import { accessConfirmationReducer, initialAccessConfirmation } from '@/pages/Users/accessConfirmation';
import { createTableReadController, type TableReadSuccess } from './TableReadController';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const page = (id: string): TableReadSuccess<string> => ({ result: { data: [id], total: 1, success: true }, asOf: `snapshot:${id}` });
function tableHarness() {
  const displayed = { asOf: undefined as string | undefined, error: undefined as unknown };
  const success = vi.fn((value: TableReadSuccess<string>) => { displayed.asOf = value.asOf; displayed.error = undefined; });
  const failure = vi.fn((error: unknown) => { displayed.error = error; });
  const reader = createTableReadController<string>({ success, failure });
  return { reader, displayed, success, failure };
}

describe('I-01 actual UserRecord confirmation reducer flow', () => {
  it('409 -> cancel -> reopen preserves the conflict submission lock', () => {
    let state = accessConfirmationReducer(initialAccessConfirmation, { type: 'open' });
    state = accessConfirmationReducer(state, { type: 'conflict' });
    expect(state).toEqual({ open: true, conflict: true });
    state = accessConfirmationReducer(state, { type: 'close' });
    expect(state).toEqual({ open: false, conflict: true });
    state = accessConfirmationReducer(state, { type: 'open' });
    expect(state).toEqual({ open: true, conflict: true });
  });
  it('failed refresh still blocks after another cancel/reopen; only success permits a fresh confirmation', () => {
    let state = accessConfirmationReducer(initialAccessConfirmation, { type: 'open' });
    state = accessConfirmationReducer(state, { type: 'conflict' });
    state = accessConfirmationReducer(state, { type: 'refresh_result', success: false });
    expect(state).toEqual({ open: true, conflict: true });
    state = accessConfirmationReducer(state, { type: 'close' });
    state = accessConfirmationReducer(state, { type: 'open' });
    expect(state.conflict).toBe(true);
    state = accessConfirmationReducer(state, { type: 'refresh_result', success: true });
    expect(state).toEqual({ open: false, conflict: false });
    // A successful read closes the old confirmation; the operator must open a new one.
    state = accessConfirmationReducer(state, { type: 'open' });
    expect(state).toEqual({ open: true, conflict: false });
  });
});

describe('I-02 actual BusinessTable request controller asynchronous effects', () => {
  it('slow A success cannot replace fast B success snapshot or last successful rows', async () => {
    const { reader, displayed, success, failure } = tableHarness();
    const a = deferred<TableReadSuccess<string>>();
    const b = deferred<TableReadSuccess<string>>();
    const aRequest = reader.request(() => a.promise);
    const bRequest = reader.request(() => b.promise);
    b.resolve(page('B')); await bRequest;
    a.resolve(page('A')); await aRequest;
    expect(displayed).toEqual({ asOf: 'snapshot:B', error: undefined });
    expect(reader.last().data).toEqual(['B']);
    expect(success).toHaveBeenCalledTimes(1);
    expect(failure).not.toHaveBeenCalled();
  });
  it('slow A failure cannot add an error after fast B success', async () => {
    const { reader, displayed, success, failure } = tableHarness();
    const a = deferred<TableReadSuccess<string>>();
    const aRequest = reader.request(() => a.promise);
    await reader.request(async () => page('B'));
    a.reject(new Error('old A')); await aRequest;
    expect(displayed).toEqual({ asOf: 'snapshot:B', error: undefined });
    expect(reader.last().data).toEqual(['B']);
    expect(success).toHaveBeenCalledTimes(1);
    expect(failure).not.toHaveBeenCalled();
  });
  it('slow A success cannot clear fast B failure; failed refresh retains the previous successful data', async () => {
    const { reader, displayed, success, failure } = tableHarness();
    await reader.request(async () => page('previous'));
    const a = deferred<TableReadSuccess<string>>();
    const aRequest = reader.request(() => a.promise);
    const bError = new Error('current B failed');
    const result = await reader.request(async () => { throw bError; });
    expect(result).toEqual({ data: ['previous'], total: 1, success: false });
    a.resolve(page('A')); await aRequest;
    expect(displayed).toEqual({ asOf: 'snapshot:previous', error: bError });
    expect(reader.last()).toEqual(page('previous').result);
    expect(success).toHaveBeenCalledTimes(1);
    expect(failure).toHaveBeenCalledExactlyOnceWith(bError);
  });
  it.each(['resolve', 'reject'] as const)('a request that %ss after unmount cannot publish any effect', async (outcome) => {
    const { reader, displayed, success, failure } = tableHarness();
    await reader.request(async () => page('previous'));
    success.mockClear();
    const pending = deferred<TableReadSuccess<string>>();
    const request = reader.request(() => pending.promise);
    reader.dispose();
    if (outcome === 'resolve') pending.resolve(page('unmounted'));
    else pending.reject(new Error('unmounted failure'));
    await request;
    expect(displayed).toEqual({ asOf: 'snapshot:previous', error: undefined });
    expect(reader.last().data).toEqual(['previous']);
    expect(success).not.toHaveBeenCalled(); expect(failure).not.toHaveBeenCalled();
  });
  it('effect cleanup/reactivation cannot revive a request from the previous mount', async () => {
    const { reader, displayed, success, failure } = tableHarness();
    const previousMount = deferred<TableReadSuccess<string>>();
    const oldRequest = reader.request(() => previousMount.promise);
    reader.dispose(); reader.activate();
    await reader.request(async () => page('remounted'));
    previousMount.resolve(page('previousMount')); await oldRequest;
    expect(displayed).toEqual({ asOf: 'snapshot:remounted', error: undefined });
    expect(reader.last().data).toEqual(['remounted']);
    expect(success).toHaveBeenCalledTimes(1); expect(failure).not.toHaveBeenCalled();
  });
});
