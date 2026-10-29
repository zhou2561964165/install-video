import type { ProColumns } from '@ant-design/pro-components';
import { Link } from '@umijs/max';
import { Tag } from 'antd';
import { AdminTimestamp } from '@/components/AdminState';
import { booleanOptions, BusinessGuard, BusinessTable, PageContainer, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';

function UsersContent() {
  const { meta } = useAdminSession();
  const columns: ProColumns<Schemas['UserSummary']>[] = [
    { title: '用户 ID', dataIndex: 'id', search: false, copyable: true, render: (_, row) => <Link to={`/users/${encodeURIComponent(row.id)}`}>{row.id}</Link> },
    { title: '邮箱', dataIndex: 'email', sorter: true, copyable: true },
    { title: '账号状态', dataIndex: 'enabled', valueType: 'select', valueEnum: { true: { text: '启用' }, false: { text: '停用' } }, render: (_, row) => <Tag>{row.access.enabled ? '启用' : '停用'}</Tag> },
    { title: '有效会员', dataIndex: 'effective_vip', valueType: 'select', valueEnum: booleanOptions, render: (_, row) => <Tag>{row.membership.effective ? '生效中' : '未生效'}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.created_at} timezone={meta?.display_timezone} /> },
  ];
  return <PageContainer title="用户与权益" subTitle="查看账号、当前会员权益与当日额度。"><BusinessTable resource="adminListUsers" title="用户列表" columns={columns} load={adminApi.adminListUsers} /></PageContainer>;
}
export default function Users() { return <BusinessGuard permission="users:read"><UsersContent /></BusinessGuard>; }
