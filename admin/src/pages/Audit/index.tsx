import type { ProColumns } from '@ant-design/pro-components';
import { useLocation } from '@umijs/max';
import { Button } from 'antd';
import { useState } from 'react';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { BusinessGuard, BusinessTable, Details, DetailDrawer, PageContainer, text, yesNo, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import { membershipAuditLabel, membershipModes } from '@/components/business/membershipPolicy';

const actionLabels: Record<string, string> = {
  'auth.login_succeeded': '管理员登录', 'auth.login_failed': '登录失败', 'auth.logout': '管理员退出',
  'users.access_enabled': '启用账号', 'users.access_disabled': '停用账号', 'users.access_noop': '账号设置未变化', 'users.access.denied': '账号操作被拒绝',
  'users.membership.enabled': '管理员启用会员', 'users.membership.disabled': '管理员停用会员', 'users.membership.auto': '恢复自动管理',
  'users.membership.noop': '会员设置未变化', 'users.membership.denied': '会员设置被拒绝',
  'support.replied': '回复工单', 'support.rejected': '驳回工单', 'support.reissued': '补发会员',
};
function changeRows(change: Schemas['AuditChange']): [string, React.ReactNode][] {
  if ('control_mode_before' in change) {
    const record = change as Schemas['MembershipAuditChange'];
    return [
      ['变更前管理方式', membershipModes[record.control_mode_before]], ['变更后管理方式', membershipModes[record.control_mode_after]],
      ['变更前期限', record.control_mode_before === 'enabled' && !record.control_expires_at_before ? '永久有效' : <AdminTimestamp value={record.control_expires_at_before} />],
      ['变更后期限', record.control_mode_after === 'enabled' && !record.control_expires_at_after ? '永久有效' : <AdminTimestamp value={record.control_expires_at_after} />],
      ['变更前控制版本', record.control_revision_before], ['变更后控制版本', record.control_revision_after],
    ];
  }
  const record = change as Schemas['AccessAuditChange'];
  return [['变更前账号启用', yesNo(record.enabled_before)], ['变更后账号启用', yesNo(record.enabled_after)], ['变更前版本', record.revision_before], ['变更后版本', record.revision_after]];
}

function AuditContent() {
  const { meta } = useAdminSession();
  const { search } = useLocation();
  const target = new URLSearchParams(search).get('target_user_id') ?? undefined;
  const [record, setRecord] = useState<Schemas['AuditEntry']>();
  const columns: ProColumns<Schemas['AuditEntry']>[] = [
    { title: '操作者编号', dataIndex: 'actor_user_id', hideInTable: true },
    { title: '目标用户编号', dataIndex: 'target_user_id', hideInTable: true },
    { title: '操作', dataIndex: 'action', render: (_, row) => row.action === 'users.membership' ? membershipAuditLabel(row.change) : actionLabels[row.action] ?? '其他管理操作' }, { title: '结果', dataIndex: 'outcome', render: (_, row) => <AdminStateTag domain="audit.outcome" value={row.outcome} meta={meta} /> },
    { title: '原因', dataIndex: 'reason', search: false, render: (_, row) => text(row.reason) },
    { title: '记录时间', dataIndex: 'recorded_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.recorded_at} timezone={meta?.display_timezone} /> },
    { title: '操作', valueType: 'option', render: (_, row) => <Button type="link" onClick={() => setRecord(row)}>查看详情</Button> },
  ];
  return <PageContainer title="操作记录"><BusinessTable key={target ?? 'all'} resource="adminListAuditLogs" title="管理操作" columns={columns} load={adminApi.adminListAuditLogs} params={{ target_user_id: target }} />
    <DetailDrawer title="审计详情" open={Boolean(record)} onClose={() => setRecord(undefined)}>{record && <Details rows={[
      ['审计 ID', record.id], ['操作者 ID', text(record.actor_user_id)], ['目标用户 ID', text(record.target_user_id)], ['操作', record.action], ['幂等操作范围', text(record.operation)], ['结果', record.outcome], ['原因', text(record.reason)], ['请求编号', record.request_id], ['记录时间', <AdminTimestamp key="recorded" value={record.recorded_at} timezone={meta?.display_timezone} />],
      ...(record.change ? changeRows(record.change) : []),
    ]} />}</DetailDrawer>
  </PageContainer>;
}
export default function Audit() { return <BusinessGuard permission="audit:read"><AuditContent /></BusinessGuard>; }
