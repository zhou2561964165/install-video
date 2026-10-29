import type { ProColumns } from '@ant-design/pro-components';
import { Link, useLocation } from '@umijs/max';
import { Alert } from 'antd';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { BusinessGuard, BusinessTable, PageContainer, text, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';

function JobsContent() {
  const { meta, can } = useAdminSession();
  const { search } = useLocation();
  const userId = new URLSearchParams(search).get('user_id') ?? undefined;
  const columns: ProColumns<Schemas['JobSummary']>[] = [
    { title: '任务 ID', dataIndex: 'id', search: false, render: (_, row) => <Link to={`/jobs/${encodeURIComponent(row.id)}`}>{row.id}</Link> },
    { title: '标题', dataIndex: 'title', search: false, render: (_, row) => text(row.title) },
    { title: '用户 ID', dataIndex: 'user_id', render: (_, row) => row.user_id && can('users:read') ? <Link to={`/users/${encodeURIComponent(row.user_id)}`}>{row.user_id}</Link> : text(row.user_id) },
    { title: '来源主机', dataIndex: 'source_host', search: false, render: (_, row) => text(row.source_host) },
    { title: '公开状态', dataIndex: 'public_status', render: (_, row) => <AdminStateTag domain="job.public_status" value={row.public_status} meta={meta} /> },
    { title: '内部状态', dataIndex: 'internal_state', render: (_, row) => <AdminStateTag domain="job.internal_state" value={row.internal_state} meta={meta} /> },
    { title: '执行版本', dataIndex: 'execution_version' },
    { title: '进度', dataIndex: 'progress', search: false, render: (_, row) => `${row.progress}%` },
    { title: '尝试次数', key: 'attempts', search: false, render: (_, row) => `${row.attempts_used} / ${row.attempts_limit}` },
    { title: '创建时间', dataIndex: 'created_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.created_at} timezone={meta?.display_timezone} /> },
    { title: '更新时间', dataIndex: 'updated_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.updated_at} timezone={meta?.display_timezone} /> },
  ];
  return <PageContainer title="下载任务" subTitle="只读当前保留的服务端任务，公开状态与内部状态分别呈现。"><BusinessTable key={userId ?? 'all'} resource="adminListJobs" title="任务列表" columns={columns} load={adminApi.adminListJobs} params={{ user_id: userId }} notice={<Alert type="info" showIcon title="此处不提供取消、重试或额度修改。历史任务内部状态未设置时保留未知，不改写为排队。" />} /></PageContainer>;
}
export default function Jobs() { return <BusinessGuard permission="jobs:read"><JobsContent /></BusinessGuard>; }
