import { Link, useParams } from '@umijs/max';
import { Alert, Button, Card, Checkbox, Form, Input, Modal, Space, Tag, Typography } from 'antd';
import { useId, useReducer, useRef, useState } from 'react';
import { AdminError, AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { BusinessGuard, Details, PageContainer, ReadState, Snapshot, text, useReadResource, yesNo, type Schemas } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import { formatQuota } from '@/utils/adminFormat';
import { accessFailureKind, canChangeAccess } from '@/components/business/BusinessPolicy';
import { accessConfirmationReducer, initialAccessConfirmation } from './accessConfirmation';

export function UserRecord({ id }: { id: string }) {
  const reasonInputId = useId();
  const session = useAdminSession();
  const resource = useReadResource(() => adminApi.adminGetUser(id), id);
  const [{ open: modal, conflict }, confirmation] = useReducer(accessConfirmationReducer, initialAccessConfirmation);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [writeError, setWriteError] = useState<unknown>();
  const [unknownOutcome, setUnknownOutcome] = useState(false);
  const [checked, setChecked] = useState(false);
  const [refreshed, setRefreshed] = useState(false);
  const pending = useRef<{ id: string; key: string; body: Schemas['AccessPatch'] } | undefined>(undefined);
  const data = resource.data;
  const ready = session.canFeature('users:access:write', 'account_access_write');
  const writable = canChangeAccess(data, session.me?.user_id, ready);
  const min = session.meta?.limits.reason_min_length ?? 10;
  const max = session.meta?.limits.reason_max_length ?? 500;
  const length = Array.from(reason.trim()).length;
  async function submit() {
    if (!data || !writable || busy || conflict || (unknownOutcome && (!checked || !refreshed))) return;
    if (!pending.current) {
      if (length < min || length > max) return;
      pending.current = { id, key: crypto.randomUUID(), body: { enabled: !data.access.enabled, reason: reason.trim(), expected_revision: data.access.revision } };
    }
    setBusy(true); setWriteError(undefined);
    try {
      const request = pending.current;
      await adminApi.adminSetUserAccess(request.id, request.body, request.key);
      pending.current = undefined; setUnknownOutcome(false); setChecked(false); confirmation({ type: 'close' }); setReason('');
      await resource.reload();
    } catch (error) {
      setWriteError(error);
      if (accessFailureKind(error) === 'conflict') {
        confirmation({ type: 'conflict' }); setUnknownOutcome(false); pending.current = undefined;
      } else if (accessFailureKind(error) === 'unknown') {
        setUnknownOutcome(true); setChecked(false); setRefreshed(false);
      } else {
        // A definite rejection permits a corrected operation. Unknown outcomes retain the exact key/body.
        pending.current = undefined; setUnknownOutcome(false); setChecked(false); setRefreshed(false);
      }
    } finally { setBusy(false); }
  }
  return <ReadState resource={resource}>{data && <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Card><Details title={data.email} rows={[
      ['用户 ID', data.id], ['账号状态', <Tag key="access">{data.access.enabled ? '启用' : '停用'}</Tag>],
      ['创建时间', <AdminTimestamp key="created" value={data.created_at} timezone={session.meta?.display_timezone} />],
      ['账号版本', data.access.revision], ['受保护账号', yesNo(data.access.protected_account)],
      ['原会员状态', <AdminStateTag key="membership" domain="membership.status" value={data.membership.status} meta={session.meta} />],
      ['会员当前生效', yesNo(data.membership.effective)], ['到期时间', <AdminTimestamp key="expires" value={data.membership.expires_at} timezone={session.meta?.display_timezone} />],
      ['权益来源', text(data.membership.entitlement_source)], ['会员版本', text(data.membership.revision)],
      ['期末取消标记', yesNo(data.membership.cancel_at_period_end)], ['当日额度', formatQuota(data.quota)],
      ['额度统计日（UTC）', data.quota.quota_day], ['已使用次数', data.quota.used],
    ]} /></Card>
    <Space wrap>
      {session.can('jobs:read') && <Link to={`/jobs?user_id=${encodeURIComponent(id)}`}>查看关联下载任务</Link>}
      {session.can('billing:read') && <Link to={`/billing?user_id=${encodeURIComponent(id)}`}>查看关联支付记录</Link>}
      {session.can('audit:read') && <Link to={`/audit?target_user_id=${encodeURIComponent(id)}`}>查看账号操作审计</Link>}
    </Space>
    {session.can('users:access:write') && !ready && <Alert showIcon type="info" title="账号启停暂不可用" description="账号鉴权改造完成并开放此功能后，才可进行启停操作。" />}
    {ready && (data.access.protected_account || data.id === session.me?.user_id) && <Alert showIcon type="info" title="此账号受保护，不能在这里启停。" />}
    {unknownOutcome && <Alert showIcon type="warning" title="上次操作的处理结果尚未确认" description="请查看账号最新状态与审计记录，再使用原请求确认结果。" />}
    {writable && <Button danger={data.access.enabled} onClick={() => { confirmation({ type: 'open' }); if (!pending.current && !conflict) { setWriteError(undefined); setReason(''); } }}>{unknownOutcome ? '继续核对启停结果' : data.access.enabled ? '停用账号' : '启用账号'}</Button>}
    <Snapshot value={data.as_of} />
    <Modal title={unknownOutcome ? '确认上次操作结果' : data.access.enabled ? '确认停用账号' : '确认启用账号'} open={modal} onCancel={() => !busy && confirmation({ type: 'close' })} maskClosable={false}
      confirmLoading={busy} okText={unknownOutcome ? '使用原请求确认结果' : '确认操作'} cancelText="取消"
      okButtonProps={{ danger: pending.current ? !pending.current.body.enabled : data.access.enabled, disabled: !writable || conflict || (unknownOutcome ? !checked || !refreshed : length < min || length > max) }} onOk={() => void submit()}>
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        <Typography.Paragraph>目标账号：{data.email}。停用会使该账号已有登录失效，已经受理的任务仍会继续；恢复后需要重新登录。</Typography.Paragraph>
        <Form layout="vertical"><Form.Item label="操作原因" htmlFor={reasonInputId} required validateStatus={!pending.current && reason && (length < min || length > max) ? 'error' : undefined} help={`请输入 ${min}–${max} 字，首尾空白不计入。`}>
          <Input.TextArea id={reasonInputId} value={pending.current?.body.reason ?? reason} onChange={(event) => setReason(event.target.value)} disabled={busy || Boolean(pending.current)} autoSize={{ minRows: 3, maxRows: 7 }} />
        </Form.Item></Form>
        {writeError !== undefined && <AdminError error={writeError} />}
        {conflict && <Alert type="warning" showIcon title="账号状态已变化" description={<Button loading={resource.loading} onClick={async () => { confirmation({ type: 'refresh_result', success: await resource.reload() }); }}>刷新账号并重新确认</Button>} />}
        {unknownOutcome && <Alert type="warning" showIcon title="处理结果未知，请先核对" description={<Space orientation="vertical"><span>请核对账号状态和操作审计。确认时只重放原始请求，不能修改原因、目标或幂等键。</span><Button loading={resource.loading} onClick={async () => { setChecked(false); setRefreshed(await resource.reload()); }}>查询账号最新状态</Button>{session.can('audit:read') && <Link target="_blank" rel="noopener noreferrer" to={`/audit?target_user_id=${encodeURIComponent(id)}`}>打开操作审计</Link>}<Checkbox checked={checked} disabled={!refreshed} onChange={(event) => setChecked(event.target.checked)}>我已核对最新账号状态及操作审计，确认使用原请求查询结果</Checkbox></Space>} />}
      </Space>
    </Modal>
  </Space>}</ReadState>;
}
export default function UserDetail() {
  const { user_id = '' } = useParams<{ user_id: string }>();
  return <BusinessGuard permission="users:read"><PageContainer title="用户详情" extra={<Link to="/users">返回用户列表</Link>}><UserRecord key={user_id} id={user_id} /></PageContainer></BusinessGuard>;
}
