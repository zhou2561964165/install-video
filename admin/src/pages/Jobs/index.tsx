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
    { title: '标题', dataIndex: 'title', search: false, render: (_, row) => <Link to={`/jobs/${encodeURIComponent(row.id)}`}>{row.title ?? '查看下载详情'}</Link> },
    { title: '用户 ID', dataIndex: 'user_id', hideInTable: true },
    { title: '来源主机', dataIndex: 'source_host', search: false, render: (_, row) => text(row.source_host) },
    { title: '公开状态', dataIndex: 'public_status', render: (_, row) => <AdminStateTag domain="job.public_status" value={row.public_status} meta={meta} /> },
    { title: '内部状态', dataIndex: 'internal_state', hideInTable: true },
    { title: '执行版本', dataIndex: 'execution_version', hideInTable: true },
    { title: '进度', dataIndex: 'progress', search: false, render: (_, row) => `${row.progress}%` },
    { title: '创建时间', dataIndex: 'created_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.created_at} timezone={meta?.display_timezone} /> },
    { title: '更新时间', dataIndex: 'updated_at', search: false, sorter: true, render: (_, row) => <AdminTimestamp value={row.updated_at} timezone={meta?.display_timezone} /> },
  ];
  return <PageContainer title="下载记录" subTitle="当前保留的服务端下载任务。"><BusinessTable key={userId ?? 'all'} resource="adminListJobs" title="下载列表" columns={columns} load={adminApi.adminListJobs} params={{ user_id: userId }} /></PageContainer>;
}
export default function Jobs() { return <BusinessGuard permission="jobs:read"><JobsContent /></BusinessGuard>; }
