import type { ProColumns } from '@ant-design/pro-components';
import { Link, useLocation } from '@umijs/max';
import { Alert } from 'antd';
import { AdminTimestamp } from '@/components/AdminState';
import { BusinessGuard, BusinessTable, PageContainer, text, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import { supportEnumText, supportLabel } from './supportPolicy';
import { PriorityTag, TicketStateTag } from './SupportTags';

function SupportContent() {
  const { meta, can } = useAdminSession();
  const { search } = useLocation();
  const userId = new URLSearchParams(search).get('user_id') ?? undefined;
  const columns: ProColumns<Schemas['SupportTicketSummary']>[] = [
    { title: '优先级', dataIndex: 'priority', render: (_, row) => <PriorityTag value={row.priority} /> },
    { title: '工单', dataIndex: 'id', search: false, render: (_, row) => <Link to={`/support/${encodeURIComponent(row.id)}`}>{row.category_label}</Link> },
    { title: '问题类型', dataIndex: 'category', hideInTable: true },
    { title: '状态', dataIndex: 'state', render: (_, row) => <TicketStateTag value={row.state} /> },
    { title: '处理结果', dataIndex: 'resolution', search: false, render: (_, row) => row.resolution ? supportLabel('resolution', row.resolution) : '—' },
    { title: '用户', dataIndex: 'user_id', render: (_, row) => can('users:read') ? <Link to={`/users/${encodeURIComponent(row.user_id)}`}>{row.user_email}</Link> : text(row.user_email) },
    { title: '关联订单', dataIndex: 'checkout_id', search: false, render: (_, row) => text(row.checkout_id ?? '—') },
    { title: '提交时间', dataIndex: 'created_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.created_at} timezone={meta?.display_timezone} /> },
    { title: '结单时间', dataIndex: 'resolved_at', search: false, render: (_, row) => <AdminTimestamp value={row.resolved_at} timezone={meta?.display_timezone} /> },
  ];
  return <PageContainer title="客服工单" subTitle="会员用户的工单与“会员付款后未到账”工单标记为优先，默认排在前面。">
    <BusinessTable key={userId ?? 'all'} resource="adminListSupportTickets" title="工单列表" columns={columns} load={adminApi.adminListSupportTickets}
      params={{ user_id: userId, state: 'open' }} enumText={{ category: supportEnumText('category'), state: supportEnumText('state'), priority: supportEnumText('priority') }}
      notice={<Alert type="info" showIcon title="默认只显示待处理工单，可清空“状态”筛选查看全部。每张工单只回复一次；补发会员需先向支付平台核实付款，审核通过后系统自动回复用户。" />} />
  </PageContainer>;
}
export default function Support() { return <BusinessGuard permission="support:read"><SupportContent /></BusinessGuard>; }
