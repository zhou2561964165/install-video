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
const { FormStore } = require('@rc-component/form/lib/hooks/useForm');

describe('actual BusinessTable query-form wiring', () => {
  it('keeps ordinary state filters visible and technical filters behind advanced disclosure', () => {
    const load = vi.fn();
    renderToStaticMarkup(React.createElement(BusinessTable, { resource: 'adminListJobs', title: '下载记录', columns: [], load }));
    expect(captured.table!.columns.find((column: Record<string, any>) => column.dataIndex === 'public_status').search).not.toBe(false);
    for (const field of ['user_id', 'internal_state', 'execution_version']) expect(captured.table!.columns.find((column: Record<string, any>) => column.dataIndex === field).search).toBe(false);
    const control = captured.table!.toolBarRender()[0];
    expect(control.props.children).toBe('高级筛选');
    expect(control.props['aria-pressed']).toBe(false);
  });
  it('opts out of ProTable default ignoreRules and retains UTC validation through installed QueryFilter', async () => {
    const load = vi.fn(async () => ({ items: [], total: 0, page: 1, page_size: 10, as_of: '2026-10-26T00:00:00Z' }));
    renderToStaticMarkup(React.createElement(BusinessTable, { resource: 'adminListAuditLogs', title: '审计', columns: [], load }));
    const table = captured.table!;
    expect(table.form.ignoreRules).toBe(false);
    const field = table.columns.find((column: Record<string, any>) => column.dataIndex === 'recorded_from');
    expect(field.fieldProps).toMatchObject({ type: 'datetime-local' });
    expect(field.fieldProps.placeholder).toBeUndefined();
    const selected = '2026-10-04T08:00:00';
    const wire = field.formItemProps.getValueFromEvent({ target: { value: selected } });
    expect(wire).toBe(new Date(selected).toISOString());
    expect(wire).toMatch(/Z$/);
    expect(field.formItemProps.getValueProps(wire)).toEqual({ value: selected });
    const item = React.createElement('input', { formItemProps: field.formItemProps });
    const normalized = flatMapQueryFilterItems([item], table.form.ignoreRules);
    const validator = normalized[0].props.formItemProps.rules[0].validator;
    await expect(validator({}, '2026-10-04T08:00:00+08:00')).rejects.toThrow('请输入有效的 UTC 时间');
    await expect(validator({}, '2026-10-04T00:00:00Z')).resolves.toBeUndefined();
    // Defense in depth: direct request bypass is still a local rejection, never an unfiltered API load.
    await table.request({ recorded_from: '2026-10-04T08:00:00+08:00' }, {}, {});
    expect(load).not.toHaveBeenCalled();
    await table.request({ recorded_from: wire }, {}, {});
    expect(load).toHaveBeenCalledWith(expect.objectContaining({ recorded_from: wire }));
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
  it('retains supported hidden filters on ordinary search and clears them on explicit reset', async () => {
    const load = vi.fn(async (_query: Record<string, unknown>) => ({ items: [], total: 0, page: 1, page_size: 10, as_of: '2026-10-26T00:00:00Z' }));
    renderToStaticMarkup(React.createElement(BusinessTable, { resource: 'adminListJobs', title: '下载记录', columns: [], load, params: { user_id: 'original-url-user' } }));
    const table = captured.table!;
    const form = new FormStore(() => {}).getForm();
    // This is the installed store's actual behavior after advanced fields unmount.
    form.setFieldsValue({ user_id: 'original-url-user', internal_state: 'running', arbitrary: 'must-not-reach-api' });
    expect(form.getFieldsValue()).toEqual({});
    expect(form.getFieldsValue(true)).toMatchObject({ user_id: 'original-url-user' });
    if (table.formRef) table.formRef.current = form;
    const submitted = table.beforeSearchSubmit({ current: 1 });
    const search = (values: Record<string, unknown>) => table.request(table.beforeSearchSubmit(values), {}, {});
    await table.request(submitted, {}, {});
    expect(load).toHaveBeenLastCalledWith(expect.objectContaining({ user_id: 'original-url-user', internal_state: 'running' }));
    expect(load.mock.calls.at(-1)?.[0]).not.toHaveProperty('arbitrary');
    form.setFieldsValue({ user_id: 'changed-user' });
    await table.request(submitted, {}, {});
    expect(load).toHaveBeenLastCalledWith(expect.objectContaining({ user_id: 'original-url-user' }));
    await search({ current: 1 });
    expect(load).toHaveBeenLastCalledWith(expect.objectContaining({ user_id: 'changed-user' }));
    // Explicitly clearing a submitted field wins over an older preserved value.
    await search({ current: 1, user_id: '' });
    expect(load.mock.calls.at(-1)?.[0]).not.toHaveProperty('user_id');
    form.submit = vi.fn();
    expect(table.form.submitter.resetButtonProps.preventDefault).toBe(true);
    table.form.submitter.resetButtonProps.onClick();
    expect(form.submit).toHaveBeenCalledOnce();
    await search({ current: 1 });
    expect(load.mock.calls.at(-1)?.[0]).not.toHaveProperty('user_id');
    expect(load.mock.calls.at(-1)?.[0]).not.toHaveProperty('internal_state');
    // Neither repeated searches nor reset resurrect the original URL initialValues.
    await search({ current: 1 });
    expect(load.mock.calls.at(-1)?.[0]).not.toHaveProperty('user_id');
  });
});
