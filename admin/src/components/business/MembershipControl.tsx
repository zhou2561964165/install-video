import { Alert, Button, Checkbox, Form, Input, Modal, Radio, Space, Typography } from 'antd';
import { Link } from '@umijs/max';
import { useId, useReducer, useState } from 'react';
import { AdminError, AdminTimestamp } from '@/components/AdminState';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import type { Schemas } from '@/services/admin/types';
import { isUtcTime, localInputToUtc } from '@/utils/adminTime';
import { membershipAttempt, membershipModes, membershipPatch, membershipReason } from './membershipPolicy';
import { useReadResource } from './BusinessShared';

export function MembershipSummary({ membership }: { membership: Schemas['Membership'] }) {
  const { meta } = useAdminSession();
  return <Space orientation="vertical" size="small">
    <span>{membershipModes[membership.control_mode] ?? '未知管理方式'} · {membership.effective ? '会员生效中' : '会员未生效'}</span>
    <span>{membership.effective_permanent ? '永久有效' : membership.effective_expires_at ? <>有效至 <AdminTimestamp value={membership.effective_expires_at} timezone={meta?.display_timezone} /></> : '暂无有效期限'}</span>
    <Typography.Text type="secondary">{membershipReason(membership.effective_reason)}</Typography.Text>
  </Space>;
}

/** Both the user list and user detail use this exact dialog and request guard. */
export default function MembershipControl({ userId, onChanged }: { userId: string; onChanged?: () => void | Promise<unknown> }) {
  const session = useAdminSession();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Schemas['MembershipPatch']['mode']>('enabled');
  const [term, setTerm] = useState<'permanent' | 'until'>('permanent');
  const [date, setDate] = useState('');
  const [reason, setReason] = useState('');
  const [dateTouched, setDateTouched] = useState(false);
  const [, rerender] = useReducer((value: number) => value + 1, 0);
  const reasonId = useId(), dateId = useId();
  const attempt = membershipAttempt(session.me?.user_id ?? '', userId);
  const resource = useReadResource(() => open ? adminApi.adminGetUser(userId) : Promise.resolve(undefined), `${userId}:${open}`);
  const data = resource.data;
  const permitted = session.can('memberships:write');
  const ready = session.canFeature('memberships:write', 'membership_control_write');
  const min = session.meta?.limits?.reason_min_length ?? 10, max = session.meta?.limits?.reason_max_length ?? 500;
  const frozen = attempt.pending?.body;
  const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const untilSelected = frozen ? frozen.mode === 'enabled' && frozen.expires_at !== null : mode === 'enabled' && term === 'until';
  const expiresAt = frozen ? frozen.expires_at : untilSelected ? localInputToUtc(date) : null;
  const invalidDeadline = !frozen && untilSelected && (!isUtcTime(expiresAt) || Date.parse(expiresAt) <= Date.now());
  const deadlineError = '请先填写有效的未来到期时间';
  let body: Schemas['MembershipPatch'] | undefined;
  try {
    body = frozen ?? (data ? membershipPatch({ mode, expires_at: expiresAt, reason, expected_revision: data.membership.control_revision }, Date.now(), min, max) : undefined);
  } catch { /* Field validation is displayed in the dialog; invalid requests are never sent. */ }
  const blocked = !ready || !data || !body || !attempt.canSubmit() || resource.loading;
  async function refresh() { attempt.refreshed(await resource.reload()); rerender(); }
  async function submit() {
    if (blocked || !body || !attempt.canSubmit()) return;
    const request = attempt.prepare(body); attempt.busy = true; attempt.error = undefined; rerender();
    let succeeded = false;
    try {
      await adminApi.adminSetUserMembership(userId, request.body, request.key);
      attempt.complete(); setOpen(false); setReason(''); setDateTouched(false); succeeded = true;
    } catch (error) { attempt.fail(error); }
    finally { attempt.busy = false; rerender(); }
    // A refresh failure cannot turn a confirmed write back into an unknown write.
    if (succeeded) await onChanged?.();
  }
  if (!permitted) return null;
  return <>
    <Button disabled={!ready} onClick={() => setOpen(true)}>{attempt.unknown ? '核对会员操作' : '管理会员'}</Button>
    {!ready && <Typography.Text type="secondary">会员设置暂不可用</Typography.Text>}
    <Modal title={attempt.unknown ? '核对会员操作结果' : '管理会员'} open={open} maskClosable={false}
      onCancel={() => { if (!attempt.busy) setOpen(false); }} cancelButtonProps={{ disabled: attempt.busy }}
      confirmLoading={attempt.busy} okText={attempt.unknown ? '使用原请求确认结果' : '确认会员设置'} cancelText="关闭"
      okButtonProps={{ disabled: blocked, danger: (frozen?.mode ?? mode) === 'disabled' }} onOk={() => void submit()}>
      <Space className="admin-business admin-membership-dialog" orientation="vertical" size="middle">
        {resource.error !== undefined && <AdminError error={resource.error} onRetry={() => void refresh()} />}
        {!data && !resource.error && <span>正在读取用户与会员状态…</span>}
        {data && <>
          <Typography.Text>目标用户：{data.email}</Typography.Text>
          <MembershipSummary membership={data.membership} />
          <Form layout="vertical" disabled={attempt.busy || Boolean(frozen) || attempt.conflict}>
            <Form.Item label="管理方式" required><Radio.Group value={frozen?.mode ?? mode} onChange={(event) => setMode(event.target.value)} options={[
              { value: 'enabled', label: '管理员启用' }, { value: 'disabled', label: '管理员停用' }, { value: 'auto', label: '恢复自动管理' },
            ]} /></Form.Item>
            {(frozen?.mode ?? mode) === 'enabled' && <>
              <Form.Item label="启用期限" required><Radio.Group value={frozen ? frozen.expires_at ? 'until' : 'permanent' : term} onChange={(event) => setTerm(event.target.value)} options={[{ value: 'permanent', label: '永久有效' }, { value: 'until', label: '指定到期时间' }]} /></Form.Item>
              {untilSelected && <Form.Item label={`到期时间（${localTimezone}）`} htmlFor={dateId} required validateStatus={dateTouched && invalidDeadline ? 'error' : undefined} help={dateTouched && invalidDeadline ? deadlineError : '请选择未来时间；提交时转换为 UTC。到期后保持未生效，需再次设置或恢复自动管理。'}>
                {frozen ? <AdminTimestamp value={frozen.expires_at} timezone={localTimezone} /> : <Input id={dateId} type="datetime-local" value={date} onChange={(event) => { setDate(event.target.value); setDateTouched(true); }} onBlur={() => setDateTouched(true)} aria-invalid={dateTouched && invalidDeadline} />}
              </Form.Item>}
            </>}
            <Form.Item label="操作原因" htmlFor={reasonId} required help={`请输入 ${min}–${max} 字，原因会记录到操作日志。`}>
              <Input.TextArea id={reasonId} value={frozen?.reason ?? reason} onChange={(event) => setReason(event.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} />
            </Form.Item>
          </Form>
          <Alert showIcon type={(frozen?.mode ?? mode) === 'disabled' ? 'warning' : 'info'} title="确认变更后的效果" description={
            (frozen?.mode ?? mode) === 'disabled' ? '会员权益立即失效；账号登录及免费功能仍可使用。' :
            (frozen?.mode ?? mode) === 'auto' ? '清除管理员设置，重新按原付款会员记录判断；原记录已到期时不会生效。' :
            untilSelected ? invalidDeadline ? deadlineError : <>管理员启用，独立有效至 <AdminTimestamp value={expiresAt} timezone={localTimezone} />；不受原付款期限限制。</> : '管理员启用，永久有效；不受原付款状态及期限限制。'
          } />
          {attempt.error !== undefined && <AdminError error={attempt.error} />}
          {attempt.conflict && <Alert type="warning" showIcon title="会员设置已变化，请刷新后重新确认" description={<Button loading={resource.loading} onClick={() => void refresh()}>刷新会员设置</Button>} />}
          {attempt.unknown && <Alert type="warning" showIcon title="处理结果尚未确认" description={<Space orientation="vertical">
            <span>请先核对当前会员和操作记录，再使用原请求确认。原管理方式、期限、原因及请求编号已保留。</span>
            <Button loading={resource.loading} onClick={() => void refresh()}>查询最新会员状态</Button>
            {session.can('audit:read') && <Link target="_blank" rel="noopener noreferrer" to={`/audit?target_user_id=${encodeURIComponent(userId)}`}>查看操作记录</Link>}
            <Checkbox checked={attempt.checked} disabled={!attempt.hasRefreshed} onChange={(event) => { attempt.checked = event.target.checked; rerender(); }}>我已核对最新会员状态及操作记录，确认使用原请求核对结果</Checkbox>
          </Space>} />}
          <Typography.Text type="secondary">数据截至 <AdminTimestamp value={data.as_of} timezone={session.meta?.display_timezone} /></Typography.Text>
        </>}
      </Space>
    </Modal>
  </>;
}
