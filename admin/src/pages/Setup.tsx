import { PageContainer } from '@ant-design/pro-components';
import { Alert, Card } from 'antd';

export default function Setup() {
  return <PageContainer title="管理端准备中">
    <Card><Alert type="info" showIcon title="管理端尚未开放"
      description="管理认证及业务页面正在准备，当前无法查询或修改业务数据。" /></Card>
  </PageContainer>;
}
