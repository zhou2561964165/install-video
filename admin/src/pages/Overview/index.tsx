import { ProTable } from '@ant-design/pro-components';
import { Alert, Card, Col, Row, Space, Statistic } from 'antd';
import { AdminStateTag } from '@/components/AdminState';
import { BusinessGuard, PageContainer, ReadState, Snapshot, useReadResource, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';

function OverviewContent() {
  const { meta } = useAdminSession();
  const resource = useReadResource(adminApi.adminOverview, 'overview');
  const data = resource.data;
  const distribution = (title: string, domain: string, rows: Schemas['StateCount'][]) => <ProTable<Schemas['StateCount']> headerTitle={title} rowKey="state" dataSource={rows} search={false} options={false} pagination={false} locale={{ emptyText: '当前快照没有任务状态记录' }} columns={[
    { title: '状态', dataIndex: 'state', render: (_, row) => <AdminStateTag domain={domain} value={row.state} meta={meta} /> },
    { title: '数量', dataIndex: 'count', valueType: 'digit' },
  ]} />;
  return <PageContainer title="概览" subTitle="用户、有效会员与当前保留的服务端任务快照。"><ReadState resource={resource}>{data && <Space className="admin-business" orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Row gutter={[16, 16]}>
      {[
        ['用户总数', data.users_total, data.scope.users],
        ['有效 VIP', data.effective_vip_total, data.scope.effective_vip],
        ['保留服务端任务', data.retained_server_jobs_total, data.scope.jobs],
      ].map(([title, value, scope]) => <Col key={String(title)} xs={24} md={8}><Card><Statistic title={title} value={value ?? '未知'} /><p>{scope}</p></Card></Col>)}
    </Row>
    <Alert type="info" showIcon title="统计口径" description="任务数量只覆盖当前保留的 server Job，不等于全部下载历史、下载操作数或扣额数。此页不提供营收估算。" />
    {distribution('公开状态分布', 'job.public_status', data.jobs_by_public_status)}
    {distribution('内部状态分布', 'job.internal_state', data.jobs_by_internal_state)}
    <Snapshot value={data.as_of} />
  </Space>}</ReadState></PageContainer>;
}
export default function Overview() { return <BusinessGuard permission="overview:read"><OverviewContent /></BusinessGuard>; }
