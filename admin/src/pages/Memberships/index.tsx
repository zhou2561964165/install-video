import type { ProColumns } from '@ant-design/pro-components';
import { history, Link, useLocation } from '@umijs/max';
import { useEffect } from 'react';
import { Alert } from 'antd';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { booleanOptions, BusinessGuard, BusinessTable, PageContainer, text, yesNo, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import { MembershipSummary } from '@/components/business/MembershipControl';

function MembershipContent() {
  const { meta, can } = useAdminSession();
  const { search } = useLocation();
  const canReadUsers = can('users:read');
  useEffect(() => {
    if (!canReadUsers) return;
    const query = new URLSearchParams(search), user = query.get('user_id');
    // Preserve legacy filtered membership links that have no equivalent user-list filter.
    if (query.has('status')) return;
    history.replace(user ? `/users/${encodeURIComponent(user)}` : `/users${query.has('effective') ? `?effective_vip=${encodeURIComponent(query.get('effective')!)}` : ''}`);
  }, [canReadUsers, search]);
  const columns: ProColumns<Schemas['Membership']>[] = [
    { title: '用户 ID', dataIndex: 'user_id', render: (_, row) => can('users:read') ? <Link to={`/users/${encodeURIComponent(row.user_id)}`}>{row.user_id}</Link> : row.user_id },
    { title: '原会员记录状态', dataIndex: 'status', render: (_, row) => <AdminStateTag domain="membership.status" value={row.status} meta={meta} /> },
    { title: '会员权益', key: 'effective-summary', search: false, render: (_, row) => <MembershipSummary membership={row} /> },
    { title: '当前生效', dataIndex: 'effective', valueType: 'select', valueEnum: booleanOptions, render: (_, row) => yesNo(row.effective) },
    { title: '原付款有效期', dataIndex: 'expires_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.expires_at} timezone={meta?.display_timezone} /> },
  ];
  return <PageContainer title="用户会员"><BusinessTable resource="adminListMemberships" title="会员记录" rowKey="user_id" columns={columns} load={adminApi.adminListMemberships} params={Object.fromEntries(new URLSearchParams(search))} /></PageContainer>;
}
export default function Memberships() { return <BusinessGuard permission="memberships:read"><MembershipContent /></BusinessGuard>; }
