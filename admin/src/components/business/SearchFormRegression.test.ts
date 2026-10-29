import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRequire } from 'node:module';
import { describe, expect, it, vi } from 'vitest';
import { resourceConfig } from '@/config/resourceConfig';
import type { Schemas } from '@/services/admin/types';

const captured = vi.hoisted(() => ({ table: undefined as Record<string, any> | undefined }));
const metadata = {
  queries: Object.entries(resourceConfig).map(([resource, entry]) => ({ resource, sort_values: entry.sortValues, filters: entry.filters.map((field) => ({ name: field.name, kind: field.kind, ...(field.schema.enum ? { allowed_values: field.schema.enum.map(String) } : {}) })) })),
} as unknown as Schemas['AdminMeta'];
vi.mock('@/hooks/useAdminSession', () => ({ useAdminSession: () => ({ meta: metadata }) }));
vi.mock('@/components/AdminState', () => ({ AdminError: () => null, AdminTimestamp: () => null }));
vi.mock('@/services/admin/api', () => ({ toProTableResult: (page: { items: unknown[]; total: number }) => ({ data: page.items, total: page.total, success: true }) }));
vi.mock('@ant-design/pro-components', () => ({
  ProTable: (props: Record<string, any>) => { captured.table = props; return null; },
  ProDescriptions: () => null, PageContainer: () => null,
}));
vi.mock('antd', () => ({ Alert: () => null, Button: () => null, Drawer: () => null, Empty: () => null, Grid: {}, Result: () => null, Skeleton: () => null, Space: ({ children }: { children: React.ReactNode }) => React.createElement('div', {}, children), Typography: { Text: () => null } }));
import { BusinessTable } from './BusinessShared';

const require = createRequire(import.meta.url);
// Exercise the installed QueryFilter and Space normalization functions, not copies.
const { flatMapQueryFilterItems } = require('@ant-design/pro-components/lib/form/layouts/QueryFilter/processQueryFilterItems');
const spaceToArray = require('@rc-component/util/lib/Children/toArray').default;

describe('actual BusinessTable query-form wiring', () => {
  it('opts out of ProTable default ignoreRules and retains UTC validation through installed QueryFilter', async () => {
    const load = vi.fn(async () => ({ items: [], total: 0, page: 1, page_size: 10, as_of: '2026-10-26T00:00:00Z' }));
    renderToStaticMarkup(React.createElement(BusinessTable, { resource: 'adminListAuditLogs', title: '审计', columns: [], load }));
    const table = captured.table!;
    expect(table.form.ignoreRules).toBe(false);
    const field = table.columns.find((column: Record<string, any>) => column.dataIndex === 'recorded_from');
    const item = React.createElement('input', { formItemProps: field.formItemProps });
    const normalized = flatMapQueryFilterItems([item], table.form.ignoreRules);
    const validator = normalized[0].props.formItemProps.rules[0].validator;
    await expect(validator({}, '2026-10-04T08:00:00+08:00')).rejects.toThrow('请输入有效的 UTC 时间');
    await expect(validator({}, '2026-10-04T00:00:00Z')).resolves.toBeUndefined();
    // Defense in depth: direct request bypass is still a local rejection, never an unfiltered API load.
    await table.request({ recorded_from: '2026-10-04T08:00:00+08:00' }, {}, {});
    expect(load).not.toHaveBeenCalled();
    await table.request({ recorded_from: '2026-10-04T00:00:00Z' }, {}, {});
    expect(load).toHaveBeenCalledWith(expect.objectContaining({ recorded_from: '2026-10-04T00:00:00Z' }));
  });
  it('installed Space flattens an error Fragment and shifts index keys; stable keyed wrappers preserve table identity', () => {
    const child = React.createElement('table');
    const error = React.createElement(React.Fragment, {}, React.createElement('div'), React.createElement('aside'));
    const keys = (children: React.ReactNode) => spaceToArray(children, { keepEmpty: true }).map((element: React.ReactElement | null, index: number) => element?.key ?? index);
    expect(keys([null, null, child])).toEqual([0, 1, 2]);
    expect(keys([null, error, child])).toEqual([0, 1, 2, 3]);
    const stable = (failure: React.ReactNode) => [React.createElement('div', { key: 'notice' }), React.createElement('div', { key: 'request-state' }, failure), React.createElement('table', { key: 'business-table' })];
    expect(keys(stable(null))).toEqual(keys(stable(error)));
  });
});
