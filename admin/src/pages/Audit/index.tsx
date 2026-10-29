import type { ProColumns } from '@ant-design/pro-components';
import { useLocation } from '@umijs/max';
import { Alert, Button } from 'antd';
import { useState } from 'react';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { BusinessGuard, BusinessTable, Details, DetailDrawer, PageContainer, text, yesNo, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';

function AuditContent() {
  const { meta } = useAdminSession();
  const { search } = useLocation();
  const target = new URLSearchParams(search).get('target_user_id') ?? undefined;
  const [record, setRecord] = useState<Schemas['AuditEntry']>();
  const columns: ProColumns<Schemas['AuditEntry']>[] = [
    { title: '审计 ID', dataIndex: 'id', search: false, render: (_, row) => <Button type="link" onClick={() => setRecord(row)}>{row.id}</Button> },
    { title: '操作者 ID', dataIndex: 'actor_user_id', render: (_, row) => text(row.actor_user_id) },
    { title: '目标用户 ID', dataIndex: 'target_user_id', render: (_, row) => text(row.target_user_id) },
    { title: '操作', dataIndex: 'action' }, { title: '结果', dataIndex: 'outcome', render: (_, row) => <AdminStateTag domain="audit.outcome" value={row.outcome} meta={meta} /> },
    { title: '原因', dataIndex: 'reason', search: false, render: (_, row) => text(row.reason) },
    { title: '请求编号', dataIndex: 'request_id', search: false, copyable: true },
    { title: '记录时间', dataIndex: 'recorded_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.recorded_at} timezone={meta?.display_timezone} /> },
  ];
  return <PageContainer title="操作审计" subTitle="只读不可变记录，可按操作者、目标与 UTC 时间查询。"><BusinessTable key={target ?? 'all'} resource="adminListAuditLogs" title="审计记录" columns={columns} load={adminApi.adminListAuditLogs} params={{ target_user_id: target }} notice={<Alert type="info" showIcon title="审计只显示安全字段，不提供编辑或删除操作。未知操作结果保留原始安全状态，不推断成功。" />} />
    <DetailDrawer title="审计详情" open={Boolean(record)} onClose={() => setRecord(undefined)}>{record && <Details rows={[
      ['审计 ID', record.id], ['操作者 ID', text(record.actor_user_id)], ['目标用户 ID', text(record.target_user_id)], ['操作', record.action], ['幂等操作范围', text(record.operation)], ['结果', record.outcome], ['原因', text(record.reason)], ['请求编号', record.request_id], ['记录时间', <AdminTimestamp key="recorded" value={record.recorded_at} timezone={meta?.display_timezone} />],
      ...(record.change ? [['变更前启用', yesNo(record.change.enabled_before)], ['变更后启用', yesNo(record.change.enabled_after)], ['变更前版本', record.change.revision_before], ['变更后版本', record.change.revision_after]] as [string, React.ReactNode][] : []),
    ]} />}</DetailDrawer>
  </PageContainer>;
}
export default function Audit() { return <BusinessGuard permission="audit:read"><AuditContent /></BusinessGuard>; }
