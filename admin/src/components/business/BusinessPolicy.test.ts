import { describe, expect, it } from 'vitest';
import { resourceConfig, toAdminQuery } from '@/config/resourceConfig';
import type { Schemas } from '@/services/admin/types';
import { AdminApiError } from '@/services/admin/errors';
import { accessFailureKind, canChangeAccess, checkedTableParams, normalizeTableParams, sampledSystemState } from './BusinessPolicy';

const meta = {
  queries: Object.entries(resourceConfig).map(([resource, entry]) => ({ resource, sort_values: entry.sortValues, filters: entry.filters.map((field) => ({ name: field.name, kind: field.kind, ...(field.schema.enum ? { allowed_values: field.schema.enum.map(String) } : {}) })) })),
} as unknown as Schemas['AdminMeta'];
const target = { id: 'target', access: { protected_account: false } } as Schemas['UserDetail'];

describe('ProTable contract boundary', () => {
  it.each([['true', true], ['false', false], [false, false], [true, true]])('preserves boolean %s as %s', (value, expected) => {
    const params = checkedTableParams('adminListUsers', { enabled: value }, meta);
    expect(toAdminQuery('adminListUsers', params, {}, {}, meta).enabled).toBe(expected);
  });
  it('converts singleton boolean filter arrays and integer enum form keys', () => {
    expect(normalizeTableParams('adminListPayments', { revoked: ['false'] }, meta).revoked).toBe(false);
    expect(toAdminQuery('adminListJobs', checkedTableParams('adminListJobs', { execution_version: '2' }, meta), {}, {}, meta).execution_version).toBe(2);
    expect(toAdminQuery('adminListJobs', checkedTableParams('adminListJobs', { execution_version: '1' }, meta), {}, {}, meta).execution_version).toBe(1);
  });
  it('accepts arbitrary contract-valid ID and text without a value whitelist', () => {
    expect(toAdminQuery('adminListJobs', checkedTableParams('adminListJobs', { user_id: 'unlisted-user:42' }, meta), {}, {}, meta).user_id).toBe('unlisted-user:42');
    expect(toAdminQuery('adminListUsers', checkedTableParams('adminListUsers', { email: 'unlisted@example.invalid' }, meta), {}, {}, meta).email).toBe('unlisted@example.invalid');
  });
  it.each([
    ['adminListJobs', { user_id: 'bad/id' }],
    ['adminListJobs', { user_id: 'a'.repeat(257) }],
    ['adminListJobs', { execution_version: '3' }],
    ['adminListJobs', { execution_version: '01' }],
    ['adminListJobs', { execution_version: '1e0' }],
    ['adminListUsers', { enabled: 'yes' }],
    ['adminListAuditLogs', { recorded_from: 'yesterday' }],
    ['adminListAuditLogs', { recorded_before: '2026-10-26T10:00:00+08:00' }],
  ] as const)('rejects invalid supported filters locally: %s %j', (operation, params) => {
    expect(() => checkedTableParams(operation, params, meta)).toThrow(AdminApiError);
    try { checkedTableParams(operation, params, meta); } catch (error) { expect((error as AdminApiError).status).toBe(422); }
  });
  it('rejects a contract enum excluded by metadata rather than querying the whole list', () => {
    const restricted = { ...meta, queries: meta.queries.map((query) => query.resource === 'adminListJobs' ? { ...query, filters: query.filters.map((field) => field.name === 'public_status' ? { ...field, allowed_values: ['done'] } : field) } : query) };
    expect(() => checkedTableParams('adminListJobs', { public_status: 'queued' }, restricted)).toThrow(AdminApiError);
  });
  it('ignores unsupported fields and blank optional filters', () => {
    const query = toAdminQuery('adminListUsers', checkedTableParams('adminListUsers', { email: '', unsupported: 'x', current: 3 }, meta), {}, {}, meta);
    expect(query).toEqual({ page: 3, page_size: 20 });
  });
  it('accepts a UTC date without adding a finite allowed-value whitelist', () => {
    expect(toAdminQuery('adminListAuditLogs', checkedTableParams('adminListAuditLogs', { recorded_from: '2026-10-26T00:00:00Z' }, meta), {}, {}, meta).recorded_from).toBe('2026-10-26T00:00:00Z');
  });
});

describe('business safety policies', () => {
  it.each([0, 500, 503])('retains the original request for unknown HTTP %s outcomes', (status) => {
    expect(accessFailureKind(new AdminApiError(status))).toBe('unknown');
  });
  it('treats transport failure as unknown, 409 as conflict, and definite rejection as editable', () => {
    expect(accessFailureKind(new Error('timeout'))).toBe('unknown');
    expect(accessFailureKind(new AdminApiError(409))).toBe('conflict');
    expect(accessFailureKind(new AdminApiError(422))).toBe('rejected');
    expect(accessFailureKind(new AdminApiError(403))).toBe('rejected');
  });
  it('denies self even if server protected flag is false', () => { expect(canChangeAccess(target, 'target', true)).toBe(false); });
  it('denies protected, unknown actor and unavailable feature', () => {
    expect(canChangeAccess({ ...target, access: { ...target.access, protected_account: true } }, 'actor', true)).toBe(false);
    expect(canChangeAccess(target, undefined, true)).toBe(false);
    expect(canChangeAccess(target, 'actor', false)).toBe(false);
    expect(canChangeAccess(undefined, 'actor', true)).toBe(false);
  });
  it('permits a non-protected different target only when ready', () => { expect(canChangeAccess(target, 'actor', true)).toBe(true); });
  it('does not show sampled success without a sample timestamp', () => {
    expect(sampledSystemState({ status: 'ok', checked_at: null })).toBe('unknown');
    expect(sampledSystemState({ status: 'unknown', checked_at: null })).toBe('unknown');
    expect(sampledSystemState({ status: 'ok', checked_at: '2026-10-26T00:00:00Z' })).toBe('ok');
  });
});
