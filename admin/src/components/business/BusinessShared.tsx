import { PageContainer, ProDescriptions, ProTable } from '@ant-design/pro-components';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { Alert, Button, Drawer, Empty, Grid, Result, Skeleton, Space, Typography } from 'antd';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AdminError, AdminTimestamp } from '@/components/AdminState';
import { paginationPolicy, refreshInterval, resourceConfig, toAdminQuery } from '@/config/resourceConfig';
import { useAdminSession } from '@/hooks/useAdminSession';
import { toProTableResult } from '@/services/admin/api';
import type { operations, Schemas } from '@/services/admin/types';
import { stateDisplay } from '@/utils/adminFormat';
import { localInputToUtc, utcToLocalInput } from '@/utils/adminTime';
import { checkedTableParams } from './BusinessPolicy';
import { createTableReadController } from './TableReadController';
import './business.less';

export type ListOperation = 'adminListUsers' | 'adminListJobs' | 'adminListMemberships' | 'adminListCheckouts' | 'adminListPayments' | 'adminListAuditLogs' | 'adminListSupportTickets';
type Query<O extends ListOperation> = NonNullable<operations[O]['parameters']['query']>;
type ListPage<T> = { items: T[]; total: number; page: number; page_size: number; as_of: string };
export const text = (value: string | number | null | undefined) => value ?? '未知';
export const yesNo = (value: boolean | null | undefined) => value === true ? '是' : value === false ? '否' : '未知';
export const booleanOptions = { true: { text: '是' }, false: { text: '否' } };

export function BusinessGuard({ permission, children }: { permission: string; children: React.ReactNode }) {
  const session = useAdminSession();
  if (!session.can(permission)) return <Result status="403" title="无权查看此页面" subTitle="请联系有权限的管理员。" />;
  if (!session.meta) return <Result status="error" title="显示配置暂不可用" extra={<Button onClick={() => void session.reload()}>重新加载</Button>} />;
  return children;
}

export function Snapshot({ value }: { value?: string | null }) {
  const { meta } = useAdminSession();
  return <Typography.Text type="secondary">数据截至 <AdminTimestamp value={value ?? null} timezone={meta?.display_timezone} /> · 时间显示：{meta?.display_timezone ?? 'UTC'}</Typography.Text>;
}

/** Official table-list composition: ProTable request/actionRef, safe business columns only. */
export function BusinessTable<T extends Record<string, unknown>, O extends ListOperation>({ resource, title, columns, load, rowKey = 'id', params, notice, enumText, reloadKey }: {
  resource: O; title: string; columns: ProColumns<T>[]; load: (query: Query<O>) => Promise<ListPage<T>>;
  rowKey?: string; params?: Record<string, unknown>; notice?: React.ReactNode;
  /** Per-resource enum filter labels; overrides the shared state dictionaries for that field. */
  enumText?: Record<string, Record<string, string>>;
  reloadKey?: number;
}) {
  const { meta } = useAdminSession();
  const actionRef = useRef<ActionType | null>(null);
  const formRef = useRef<ProFormInstance | undefined>(undefined);
  const [error, setError] = useState<unknown>();
  const [asOf, setAsOf] = useState<string>();
  const [advanced, setAdvanced] = useState(false);
  useEffect(() => { if (reloadKey) void actionRef.current?.reload(); }, [reloadKey]);
  const [reader] = useState(() => createTableReadController<T>({
    success: (value) => { setAsOf(value.asOf); setError(undefined); },
    failure: setError,
  }));
  useEffect(() => { reader.activate(); return () => reader.dispose(); }, [reader]);
  const pagination = paginationPolicy(meta);
  const queryMeta = meta?.queries.find((entry) => entry.resource === resource);
  const configured = resourceConfig[resource];
  const extraColumns: ProColumns<T>[] = configured.filters.filter((field) => !columns.some((column) => column.dataIndex === field.name)).map((field) => ({ title: field.label, dataIndex: field.name, hideInTable: true }));
  const domains: Record<string, string> = { public_status: 'job.public_status', internal_state: 'job.internal_state', status: 'membership.status', state: 'checkout.state', reconciliation: 'reconciliation', outcome: 'audit.outcome' };
  const safeColumns = [...columns, ...extraColumns].map((column) => {
    const field = typeof column.dataIndex === 'string' ? column.dataIndex : '';
    const definition = configured.filters.find((entry) => entry.name === field);
    const descriptor = queryMeta?.filters.find((entry) => entry.name === field && entry.kind === definition?.kind);
    const common = ['email','enabled','effective_vip','effective','status','state','public_status','revoked','outcome','recorded_from','recorded_before'];
    const result: ProColumns<T> = { ...column, search: column.search === false || !descriptor || (!advanced && !common.includes(field)) ? false : column.search };
    if (column.sorter) result.sorter = Boolean(queryMeta?.sort_values.some((value) => value.startsWith(`${field}:`)));
    if (descriptor?.kind === 'enum') {
      result.valueType = 'select';
      result.valueEnum = Object.fromEntries((definition?.schema.enum ?? []).filter((value) => descriptor.allowed_values?.includes(String(value))).map((value) => [String(value), { text: enumText?.[field]?.[String(value)] ?? (domains[field] ? stateDisplay(domains[field], String(value), meta).label : String(value)) }]));
    } else if (descriptor?.kind === 'boolean') {
      result.valueType = 'select'; result.valueEnum = column.valueEnum ?? booleanOptions;
    } else if (descriptor) {
      result.valueType = 'text';
      if (descriptor.kind === 'datetime') {
        result.title = `${String(column.title)}（${Intl.DateTimeFormat().resolvedOptions().timeZone}）`;
        result.fieldProps = { type: 'datetime-local', step: 1 };
      }
    }
    if (descriptor) result.formItemProps = {
      ...(descriptor.kind === 'datetime' ? {
        getValueFromEvent: (event: React.ChangeEvent<HTMLInputElement>) => localInputToUtc(event.target.value),
        getValueProps: (value: unknown) => ({ value: utcToLocalInput(value) }),
      } : {}),
      rules: [{ validator: async (_, value) => {
      try { checkedTableParams(resource, { [field]: value }, meta); }
      catch { throw new Error(descriptor.kind === 'datetime' ? '请输入有效的 UTC 时间，以 Z 结尾。' : '此筛选值不符合接口约定，请检查后重试。'); }
    } }] };
    return result;
  });
  const interval = refreshInterval(meta);
  useEffect(() => {
    if (!interval) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void actionRef.current?.reload();
    }, interval * 1000);
    return () => window.clearInterval(timer);
  }, [interval]);
  return <Space className="admin-business" orientation="vertical" size="middle" style={{ width: '100%' }}>
    <div key="notice">{notice}</div>
    <div key="request-state">{error !== undefined && <><AdminError error={error} onRetry={() => void actionRef.current?.reload()} />{reader.last().success && <Alert type="warning" title="刷新未完成，以下保留上次成功读取的数据。" showIcon />}</>}</div>
    <ProTable<T>
      key="business-table" actionRef={actionRef} formRef={formRef} headerTitle={title} rowKey={rowKey} columns={safeColumns} form={{ initialValues: params, ignoreRules: false, submitter: { resetButtonProps: {
        // Reset means clear filters, including hidden values seeded by an old deep link.
        preventDefault: true,
        onClick: () => {
          formRef.current?.setFieldsValue(Object.fromEntries(configured.filters.map(field => [field.name, undefined])));
          formRef.current?.submit();
        },
      } } }}
      beforeSearchSubmit={(values) => {
        // ProForm submits registered fields only; collapsed advanced items are unmounted.
        // Capture preserved contract fields on submit so reloads never apply an unsubmitted draft.
        const stored = formRef.current?.getFieldsValue(true) ?? {};
        const preserved = Object.fromEntries(configured.filters.filter(field => Object.hasOwn(stored, field.name)).map(field => [field.name, stored[field.name]]));
        return { ...preserved, ...values };
      }}
      scroll={{ x: 'max-content' }} search={{ labelWidth: 'auto', defaultCollapsed: false }}
      toolBarRender={() => [<Button key="advanced-filters" aria-pressed={advanced} onClick={() => setAdvanced(value => !value)}>{advanced ? '收起高级筛选' : '高级筛选'}</Button>]}
      options={{ density: true, fullScreen: true, reload: true, setting: true }}
      pagination={{ defaultPageSize: pagination.default_page_size, showSizeChanger: true, pageSizeOptions: Array.from(new Set([pagination.default_page_size, 20, 50, 100].filter((size) => size <= pagination.max_page_size))), showTotal: (total) => `共 ${total} 条` }}
      locale={{ emptyText: <Empty description="没有符合当前条件的记录，可清空筛选后重试。" /> }}
      request={(tableParams, sort, filters) => reader.request(async () => {
          const query = toAdminQuery(resource, checkedTableParams(resource, tableParams, meta), sort, checkedTableParams(resource, filters, meta), meta) as Query<O>;
          const page = await load(query);
          return { result: toProTableResult(page), asOf: page.as_of };
      })}
    />
    {asOf && <Snapshot key="snapshot" value={asOf} />}
  </Space>;
}

export function Details({ title, rows }: { title?: string; rows: [string, React.ReactNode][] }) {
  return <ProDescriptions title={title} column={{ xs: 1, sm: 2, md: 2 }} emptyText="未知"
    dataSource={Object.fromEntries(rows.map(([, value], index) => [String(index), value]))}
    columns={rows.map(([label, value], index) => ({ title: label, dataIndex: String(index), render: () => value ?? '未知' }))} />;
}

/** Retain successful values during refresh; stale requests cannot replace another record. */
export function useReadResource<T>(loader: () => Promise<T>, identity: string) {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const sequence = useRef(0);
  const [record, setRecord] = useState<{ identity: string; value: T }>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    const current = ++sequence.current;
    setLoading(true);
    try {
      const value = await loaderRef.current();
      if (current === sequence.current) { setRecord({ identity, value }); setError(undefined); return true; }
    } catch (failure) {
      if (current === sequence.current) setError(failure);
    } finally { if (current === sequence.current) setLoading(false); }
    return false;
  }, [identity]);
  useEffect(() => {
    setRecord(undefined); setError(undefined); void reload();
    return () => { sequence.current += 1; };
  }, [identity, reload]);
  return { data: record?.identity === identity ? record.value : undefined, error, loading, reload };
}

export function ReadState({ resource, children }: { resource: ReturnType<typeof useReadResource<unknown>>; children: React.ReactNode }) {
  return <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Button key="reload" loading={resource.loading} onClick={() => void resource.reload()}>刷新</Button>
    <div key="read-state">{resource.error !== undefined && <><AdminError error={resource.error} onRetry={() => void resource.reload()} />{Boolean(resource.data) && <Alert type="warning" showIcon title="刷新失败，以下保留上次成功读取的数据。" />}</>}</div>
    <div key="read-content">{resource.loading && !resource.data ? <Skeleton active /> : children}</div>
  </Space>;
}

/** Official Drawer + ProDescriptions pattern, full viewport width on small screens. */
export function DetailDrawer({ title, open, onClose, children }: { title: string; open: boolean; onClose: () => void; children: React.ReactNode }) {
  const screens = Grid.useBreakpoint();
  return <Drawer title={title} open={open} onClose={onClose} size={screens.md ? 'large' : '100%'} destroyOnHidden>{children}</Drawer>;
}

export { PageContainer };
export type { Schemas };
