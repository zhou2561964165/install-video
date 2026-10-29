import { ProTable } from '@ant-design/pro-components';
import { Link, useParams } from '@umijs/max';
import { Alert, Card, Space } from 'antd';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { BusinessGuard, Details, PageContainer, ReadState, Snapshot, text, useReadResource, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import { formatBytes } from '@/utils/adminFormat';

export function JobRecord({ id }: { id: string }) {
  const { meta, can } = useAdminSession();
  const resource = useReadResource(() => adminApi.adminGetJob(id), id);
  const data = resource.data;
  const time = (value: string | null) => <AdminTimestamp value={value} timezone={meta?.display_timezone} />;
  return <ReadState resource={resource}>{data && <Space className="admin-business" orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Card><Details title={data.title ?? '任务摘要'} rows={[
      ['任务 ID', data.id], ['用户 ID', data.user_id && can('users:read') ? <Link to={`/users/${encodeURIComponent(data.user_id)}`}>{data.user_id}</Link> : text(data.user_id)],
      ['来源主机', text(data.source_host)], ['执行版本', data.execution_version],
      ['公开状态', <AdminStateTag key="public" domain="job.public_status" value={data.public_status} meta={meta} />], ['内部状态', <AdminStateTag key="internal" domain="job.internal_state" value={data.internal_state} meta={meta} />],
      ['进度', `${data.progress}%`], ['尝试次数', `${data.attempts_used} / ${data.attempts_limit}`],
      ['创建时间', time(data.created_at)], ['更新时间', time(data.updated_at)], ['到期时间', time(data.expires_at)], ['执行截止时间', time(data.run_deadline_at)], ['下次执行时间', time(data.next_run_at)],
      ['安全错误类型', text(data.error_type)], ['安全错误说明', text(data.error_message)],
    ]} /></Card>
    <Card><Details title="安全成品摘要" rows={[
      ['媒体状态', text(data.artifact.media_state)], ['字节数', data.artifact.byte_size === null ? '未知' : `${data.artifact.byte_size} B (${formatBytes(data.artifact.byte_size)})`],
      ['媒体格式', text(data.artifact.media_format)], ['检查状态', text(data.artifact.media_check)], ['完成时间', time(data.artifact.completed_at)],
    ]} /></Card>
    <Alert type="info" showIcon title="仅显示安全投影" description="成品摘要不提供文件路径或下载地址。错误说明来自服务端安全映射。历史成品字段为空时保持未知。" />
    <ProTable<Schemas['AttemptSummary']> headerTitle="执行尝试" rowKey="id" dataSource={data.attempts} pagination={false} search={false} options={false} scroll={{ x: 'max-content' }} columns={[
      { title: '尝试 ID', dataIndex: 'id' }, { title: '序号', dataIndex: 'attempt_index' }, { title: '状态', dataIndex: 'state', render: (_, row) => <AdminStateTag domain="job.attempt" value={row.state} meta={meta} /> },
      { title: '开始时间', dataIndex: 'started_at', render: (_, row) => time(row.started_at) }, { title: '结束时间', dataIndex: 'ended_at', render: (_, row) => time(row.ended_at) }, { title: '安全错误码', dataIndex: 'error_code', render: (_, row) => text(row.error_code) },
    ]} />
    <Snapshot value={data.as_of} />
  </Space>}</ReadState>;
}
export default function JobDetail() {
  const { job_id = '' } = useParams<{ job_id: string }>();
  return <BusinessGuard permission="jobs:read"><PageContainer title="任务详情" extra={<Link to="/jobs">返回任务列表</Link>}><JobRecord key={job_id} id={job_id} /></PageContainer></BusinessGuard>;
}
