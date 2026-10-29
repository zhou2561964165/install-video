import type { ProColumns } from '@ant-design/pro-components';
import { Link } from '@umijs/max';
import { Alert } from 'antd';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { booleanOptions, BusinessGuard, BusinessTable, PageContainer, text, yesNo, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';

function MembershipContent() {
  const { meta, can } = useAdminSession();
  const columns: ProColumns<Schemas['Membership']>[] = [
    { title: '用户 ID', dataIndex: 'user_id', render: (_, row) => can('users:read') ? <Link to={`/users/${encodeURIComponent(row.user_id)}`}>{row.user_id}</Link> : row.user_id },
    { title: '原始状态', dataIndex: 'status', render: (_, row) => <AdminStateTag domain="membership.status" value={row.status} meta={meta} /> },
    { title: '当前生效', dataIndex: 'effective', valueType: 'select', valueEnum: booleanOptions, render: (_, row) => yesNo(row.effective) },
    { title: '到期时间', dataIndex: 'expires_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.expires_at} timezone={meta?.display_timezone} /> },
    { title: '权益来源', dataIndex: 'entitlement_source', search: false, render: (_, row) => text(row.entitlement_source) },
    { title: '会员版本', dataIndex: 'revision', search: false, render: (_, row) => text(row.revision) },
    { title: '期末取消标记', dataIndex: 'cancel_at_period_end', search: false, render: (_, row) => yesNo(row.cancel_at_period_end) },
  ];
  return <PageContainer title="会员列表" subTitle="原始状态与当前生效状态分别呈现。"><BusinessTable resource="adminListMemberships" title="持久会员记录" rowKey="user_id" columns={columns} load={adminApi.adminListMemberships} notice={<Alert type="info" showIcon title="仅列出实际存在的会员记录。无记录的用户不会为显示需要而补写会员行；会员赠送、修改和退款不在本页提供。" />} /></PageContainer>;
}
export default function Memberships() { return <BusinessGuard permission="memberships:read"><MembershipContent /></BusinessGuard>; }
