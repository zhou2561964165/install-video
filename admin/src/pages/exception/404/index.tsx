import { Link } from '@umijs/max';
import { Button, Card, Result } from 'antd';

// Official exception page composition; routes stay inside hash history.
export default function Exception404() {
  return <Card variant="borderless"><Result status="404" title="404"
    subTitle="页面不存在" extra={<Link to="/"><Button type="primary">返回</Button></Link>} />
  </Card>;
}
