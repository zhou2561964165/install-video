import { ProTable } from '@ant-design/pro-components';
import { Alert, Card, Space, Tag } from 'antd';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { BusinessGuard, Details, PageContainer, ReadState, Snapshot, text, useReadResource, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import { sampledSystemState } from '@/components/business/BusinessPolicy';

function SystemContent() {
  const { meta } = useAdminSession();
  const resource = useReadResource(adminApi.adminSystemStatus, 'system');
  const data = resource.data;
  const labels: Record<string, string> = { database: '数据库', download_worker: '下载 Worker', billing_worker: '支付 Worker', artifact_store: '成品存储' };
  const capability = (value: Schemas['Capability']) => <Space wrap><Tag color={value.ready ? 'processing' : 'default'}>{value.ready ? '已就绪' : '未就绪'}</Tag><span>{text(value.reason)}</span></Space>;
  return <PageContainer title="系统状态" subTitle="只读安全采样与功能就绪状态。"><ReadState resource={resource}>{data && <Space className="admin-business" orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Alert type="info" showIcon title="状态依据可靠采样" description="接口返回成功只表示读取成功。没有可靠采样的组件显示未知，不能据进程存在推断健康。这里不进行第三方探测、配置编辑或服务重启。" />
    <ProTable<Schemas['ComponentStatus']> headerTitle="组件状态" rowKey="component" dataSource={data.components} search={false} options={false} pagination={false} scroll={{ x: 'max-content' }} columns={[
      { title: '组件', dataIndex: 'component', render: (_, row) => labels[row.component] ?? row.component },
      { title: '采样状态', dataIndex: 'status', render: (_, row) => <AdminStateTag domain="system.status" value={sampledSystemState(row)} meta={meta} /> },
      { title: '安全原因码', dataIndex: 'reason_code', render: (_, row) => text(row.reason_code) },
      { title: '采样时间', dataIndex: 'checked_at', render: (_, row) => <AdminTimestamp value={row.checked_at} timezone={meta?.display_timezone} /> },
    ]} />
    <Card><Details title="功能就绪状态" rows={[
      ['下载提交入口', capability(data.download_submission_ready)],
      ['账号启停', capability(data.capabilities.account_access_write)],
      ['支付金额投影', capability(data.capabilities.billing_amounts)],
    ]} /></Card>
    {!data.download_submission_ready.ready && <Alert type="warning" showIcon title="下载提交入口尚未就绪" description={data.download_submission_ready.reason ?? '当前状态不表示 PostgreSQL 下载提交已经接通。'} />}
    <Snapshot value={data.as_of} />
  </Space>}</ReadState></PageContainer>;
}
export default function System() { return <BusinessGuard permission="system:read"><SystemContent /></BusinessGuard>; }
