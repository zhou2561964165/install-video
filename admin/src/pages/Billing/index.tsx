import { ProTable } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { Link, useLocation } from '@umijs/max';
import { Alert, Button, Card, Empty, Space, Tabs } from 'antd';
import { useState } from 'react';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { booleanOptions, BusinessGuard, BusinessTable, Details, DetailDrawer, PageContainer, ReadState, Snapshot, text, useReadResource, yesNo, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import { formatMoney } from '@/utils/adminFormat';

function Facts({ data }: { data: Pick<Schemas['CheckoutDetail'], 'facts_state' | 'verified_facts'> }) {
  const session = useAdminSession();
  const showAmounts = session.canFeature('billing:read', 'billing_amounts');
  const columns: ProColumns<Schemas['BillingFactSnapshot']>[] = [
    { title: '事实 ID', dataIndex: 'id' }, { title: '供应商范围', dataIndex: 'provider_account_scope' },
    { title: '生产模式', dataIndex: 'livemode', render: (_, row) => yesNo(row.livemode) },
    { title: '核查状态', dataIndex: 'reconciliation', render: (_, row) => <AdminStateTag domain="reconciliation" value={row.reconciliation} meta={session.meta} /> },
    { title: '供应商状态', dataIndex: 'provider_status', render: (_, row) => text(row.provider_status) },
    { title: '观察时间', dataIndex: 'observed_at', render: (_, row) => <AdminTimestamp value={row.observed_at} timezone={session.meta?.display_timezone} /> },
  ];
  if (showAmounts) columns.push(
    { title: '事实金额', key: 'money', render: (_, row) => formatMoney(row.money) },
    { title: '此事实退款最小单位', dataIndex: 'amount_refunded_minor', render: (_, row) => text(row.amount_refunded_minor) },
  );
  return <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Alert type={data.facts_state === 'ambiguous' ? 'warning' : 'info'} showIcon title={data.facts_state === 'ambiguous' ? '关联存在歧义，未展示事实' : data.facts_state === 'none' ? '没有可靠关联的已核查事实' : '逐事件已核查事实'} description="观察时间不是付款时间；同一付款的多份快照不能相加，退款字段仅表示该事实。" />
    {data.facts_state === 'available' ? <ProTable<Schemas['BillingFactSnapshot']> headerTitle="关联事实" rowKey="id" columns={columns} dataSource={data.verified_facts} search={false} options={false} pagination={false} scroll={{ x: 'max-content' }} /> : <Empty description="没有可展示的可靠事实" />}
  </Space>;
}

export function CheckoutRecord({ id }: { id: string }) {
  const { meta } = useAdminSession();
  const resource = useReadResource(() => adminApi.adminGetCheckout(id), id);
  const data = resource.data;
  return <ReadState resource={resource}>{data && <Space className="admin-business" orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Card><Details title="Checkout 摘要" rows={[
      ['Checkout ID', data.id], ['用户 ID', data.user_id],
      ['状态', <AdminStateTag key="state" domain="checkout.state" value={data.state} meta={meta} />], ['核查状态', <AdminStateTag key="reconciliation" domain="reconciliation" value={data.reconciliation} meta={meta} />],
      ['已履行权益', yesNo(data.fulfilled)], ['供应商范围', text(data.provider_account_scope)], ['生产模式', yesNo(data.livemode)], ['版本', data.revision],
      ['创建时间', <AdminTimestamp key="created" value={data.created_at} timezone={meta?.display_timezone} />], ['到期时间', <AdminTimestamp key="expires" value={data.expires_at} timezone={meta?.display_timezone} />],
      ['Price ID', data.price_id], ['模式', data.mode], ['权益天数', data.duration_days], ['核查尝试次数', data.reconcile_attempts],
    ]} /></Card>
    <Facts data={data} /><Snapshot value={data.as_of} />
  </Space>}</ReadState>;
}

export function PaymentRecord({ id }: { id: string }) {
  const session = useAdminSession();
  const resource = useReadResource(() => adminApi.adminGetPayment(id), id);
  const data = resource.data;
  const showAmounts = session.canFeature('billing:read', 'billing_amounts');
  const rows: [string, React.ReactNode][] = data ? [
    ['Payment ID（PI）', data.id], ['用户 ID', text(data.user_id)], ['来源 ID', text(data.source_id)], ['已撤销绑定', yesNo(data.revoked)], ['关联说明', text(data.facts_reason)],
  ] : [];
  if (data && showAmounts) rows.push(['金额', data.amount_state === 'known' ? formatMoney(data.money) : '金额未知'], ['金额状态', text(data.amount_state)], ['金额来源', text(data.amount_source)]);
  return <ReadState resource={resource}>{data && <Space className="admin-business" orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Card><Details title="Payment 绑定与墓碑" rows={rows} /></Card>
    <Alert type="info" showIcon title="Payment 是支付意向绑定记录" description="撤销绑定不表示退款完成；本记录没有付款时间，不据此推断支付成功或营收。" />
    <Facts data={data} /><Snapshot value={data.as_of} />
  </Space>}</ReadState>;
}

function BillingContent() {
  const session = useAdminSession();
  const { search } = useLocation();
  const userId = new URLSearchParams(search).get('user_id') ?? undefined;
  const [selection, setSelection] = useState<{ kind: 'checkout' | 'payment'; id: string }>();
  const showAmounts = session.canFeature('billing:read', 'billing_amounts');
  const user = (id: string | null) => id && session.can('users:read') ? <Link to={`/users/${encodeURIComponent(id)}`}>{id}</Link> : text(id);
  const checkoutColumns: ProColumns<Schemas['CheckoutSummary']>[] = [
    { title: 'Checkout ID', dataIndex: 'id', search: false, render: (_, row) => <Button type="link" onClick={() => setSelection({ kind: 'checkout', id: row.id })}>{row.id}</Button> },
    { title: '用户 ID', dataIndex: 'user_id', render: (_, row) => user(row.user_id) },
    { title: '状态', dataIndex: 'state', render: (_, row) => <AdminStateTag domain="checkout.state" value={row.state} meta={session.meta} /> },
    { title: '核查状态', dataIndex: 'reconciliation', render: (_, row) => <AdminStateTag domain="reconciliation" value={row.reconciliation} meta={session.meta} /> },
    { title: '已履行权益', dataIndex: 'fulfilled', search: false, render: (_, row) => yesNo(row.fulfilled) },
    { title: '供应商范围', dataIndex: 'provider_account_scope', render: (_, row) => text(row.provider_account_scope) },
    { title: '生产模式', dataIndex: 'livemode', valueEnum: booleanOptions, render: (_, row) => yesNo(row.livemode) },
    { title: '创建时间', dataIndex: 'created_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.created_at} timezone={session.meta?.display_timezone} /> },
    { title: '到期时间', dataIndex: 'expires_at', search: false, render: (_, row) => <AdminTimestamp value={row.expires_at} timezone={session.meta?.display_timezone} /> },
    { title: '版本', dataIndex: 'revision', search: false },
  ];
  const paymentColumns: ProColumns<Schemas['PaymentSummary']>[] = [
    { title: 'Payment ID（PI）', dataIndex: 'id', search: false, render: (_, row) => <Button type="link" onClick={() => setSelection({ kind: 'payment', id: row.id })}>{row.id}</Button> },
    { title: '用户 ID', dataIndex: 'user_id', render: (_, row) => user(row.user_id) },
    { title: '来源 ID', dataIndex: 'source_id', search: false, render: (_, row) => text(row.source_id) },
    { title: '已撤销绑定', dataIndex: 'revoked', valueEnum: booleanOptions, render: (_, row) => yesNo(row.revoked) },
  ];
  if (showAmounts) paymentColumns.push(
    { title: '金额', key: 'money', search: false, render: (_, row) => row.amount_state === 'known' ? formatMoney(row.money) : '金额未知' },
    { title: '金额状态', dataIndex: 'amount_state', search: false },
  );
  return <PageContainer title="支付记录" subTitle="Checkout 状态、权益履行与 Payment 绑定各自独立。"><Space className="admin-business" orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Alert type="info" showIcon title="只读支付投影" description="这里不提供退款、会员修改或对账触发。金额能力未开放时隐藏金额，支付列表仍可查看。" />
    <Tabs items={[
      { key: 'checkouts', label: 'Checkout', children: <BusinessTable key={`checkout:${userId ?? 'all'}`} resource="adminListCheckouts" title="Checkout 记录" columns={checkoutColumns} load={adminApi.adminListCheckouts} params={{ user_id: userId }} /> },
      { key: 'payments', label: 'Payment', children: <BusinessTable key={`payment:${userId ?? 'all'}`} resource="adminListPayments" title="Payment 绑定" columns={paymentColumns} load={adminApi.adminListPayments} params={{ user_id: userId }} /> },
    ]} />
    <DetailDrawer title={selection?.kind === 'checkout' ? 'Checkout 详情' : 'Payment 详情'} open={Boolean(selection)} onClose={() => setSelection(undefined)}>
      {selection?.kind === 'checkout' && <CheckoutRecord key={`checkout:${selection.id}`} id={selection.id} />}
      {selection?.kind === 'payment' && <PaymentRecord key={`payment:${selection.id}`} id={selection.id} />}
    </DetailDrawer>
  </Space></PageContainer>;
}
export default function Billing() { return <BusinessGuard permission="billing:read"><BillingContent /></BusinessGuard>; }
