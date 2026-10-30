import type { ProColumns } from '@ant-design/pro-components';
import { Link, useLocation } from '@umijs/max';
import { Space, Tag } from 'antd';
import { useState } from 'react';
import { AdminTimestamp } from '@/components/AdminState';
import { booleanOptions, BusinessGuard, BusinessTable, PageContainer, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import MembershipControl, { MembershipSummary } from '@/components/business/MembershipControl';

function UsersContent() {
  const { meta } = useAdminSession();
  const { search } = useLocation();
  const [revision, refresh] = useState(0);
  const params = new URLSearchParams(search);
  const vip = params.get('effective_vip');
  const columns: ProColumns<Schemas['UserSummary']>[] = [
    { title: '邮箱', dataIndex: 'email', sorter: true, copyable: true, render: (_, row) => <Link to={`/users/${encodeURIComponent(row.id)}`}>{row.email}</Link> },
    { title: '账号状态', dataIndex: 'enabled', valueType: 'select', valueEnum: { true: { text: '启用' }, false: { text: '停用' } }, render: (_, row) => <Tag>{row.access.enabled ? '启用' : '停用'}</Tag> },
    { title: '会员状态', dataIndex: 'effective_vip', valueType: 'select', valueEnum: booleanOptions, render: (_, row) => <MembershipSummary membership={row.membership} /> },
    { title: '创建时间', dataIndex: 'created_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.created_at} timezone={meta?.display_timezone} /> },
    { title: '操作', valueType: 'option', render: (_, row) => <Space wrap><Link to={`/users/${encodeURIComponent(row.id)}`}>查看详情</Link><MembershipControl userId={row.id} onChanged={() => refresh(value => value + 1)} /></Space> },
  ];
  return <PageContainer title="用户管理"><BusinessTable resource="adminListUsers" title="用户与会员" columns={columns} load={adminApi.adminListUsers} reloadKey={revision} params={{ email: params.get('email') ?? undefined, effective_vip: vip === 'true' ? true : vip === 'false' ? false : undefined }} /></PageContainer>;
}
export default function Users() { return <BusinessGuard permission="users:read"><UsersContent /></BusinessGuard>; }
