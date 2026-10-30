import { Link, useParams } from '@umijs/max';
import { Alert, Button, Card, Collapse, Form, Input, Modal, Radio, Space, Tag, Typography } from 'antd';
import { useId, useReducer, useState } from 'react';
import { AdminStateTag, AdminTimestamp } from '@/components/AdminState';
import { BusinessGuard, Details, PageContainer, ReadState, Snapshot, text, useReadResource, yesNo } from '@/components/business/BusinessShared';
import { useAdminSession } from '@/hooks/useAdminSession';
import { adminApi } from '@/services/admin/api';
import { AdminApiError } from '@/services/admin/errors';
import { PriorityTag, TicketStateTag } from './SupportTags';
import { actionViews, initialReissue, NOTE_MAX, reissueReducer, replyTemplates, supportErrorText, supportLabel } from './supportPolicy';
import { MembershipSummary } from '@/components/business/MembershipControl';

type ReplyMode = 'reply' | 'reject';
const ACTION_TEXT = { verify: '向支付平台核实付款', reissue: '审核通过并补发会员', reply: '回复并结单', reject: '驳回并结单' } as const;

export function TicketRecord({ id }: { id: string }) {
  const noteId = useId();
  const session = useAdminSession();
  const resource = useReadResource(() => adminApi.adminGetSupportTicket(id), id);
  const data = resource.data;
  const time = (value: string | null | undefined) => <AdminTimestamp value={value ?? null} timezone={session.meta?.display_timezone} />;
  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'warning'; text: string }>();
  const [verifying, setVerifying] = useState(false);
  const [replyMode, setReplyMode] = useState<ReplyMode>();
  const [template, setTemplate] = useState<string>();
  const [note, setNote] = useState('');
  const [replying, setReplying] = useState(false);
  const [reissue, dispatch] = useReducer(reissueReducer, initialReissue);

  async function verify() {
    setVerifying(true); setNotice(undefined);
    try {
      const check = await adminApi.adminVerifySupportPayment(id);
      setNotice(check.result === 'verified' ? { type: 'success', text: '已核实付款，可在有效期内审核补发。' } : { type: 'warning', text: `核实未通过：${supportLabel('check', check.result)}` });
    } catch (error) { setNotice({ type: 'error', text: supportErrorText(error) }); }
    finally { setVerifying(false); await resource.reload(); }
  }
  async function sendReply() {
    if (!replyMode || !template || Array.from(note.trim()).length > NOTE_MAX) return;
    setReplying(true);
    try {
      const body = { template_id: template, note: note.trim() || null };
      await (replyMode === 'reply' ? adminApi.adminReplySupportTicket(id, body) : adminApi.adminRejectSupportTicket(id, body));
      setReplyMode(undefined); setNotice({ type: 'success', text: replyMode === 'reply' ? '已回复并结单。' : '已驳回并结单。' });
    } catch (error) {
      const unknown = !(error instanceof AdminApiError) || error.outcomeUnknown;
      setNotice({ type: unknown ? 'warning' : 'error', text: unknown ? '结果未知，请刷新核对工单状态，不要重复提交。' : supportErrorText(error) });
      setReplyMode(undefined);
    } finally { setReplying(false); await resource.reload(); }
  }
  async function sendReissue() {
    if (!reissue.key) return;
    dispatch({ type: 'submit' });
    try {
      const result = await adminApi.adminReissueMembership(id, reissue.key);
      dispatch({ type: 'succeeded' });
      setNotice({ type: 'success', text: `已补发 ${result.granted_days} 天会员，系统已回复用户：${result.reply_text}` });
    } catch (error) { dispatch({ type: 'failed', error }); }
    await resource.reload();
  }

  if (!data) return <ReadState resource={resource}>{null}</ReadState>;
  const views = actionViews(data.actions, session.permissions);
  const reissueOpen = reissue.phase === 'confirming' || reissue.phase === 'submitting' || reissue.phase === 'unknown';
  const noteLength = Array.from(note.trim()).length;
  return <ReadState resource={resource}><Space className="admin-business" orientation="vertical" size="middle" style={{ width: '100%' }}>
    {notice && <Alert type={notice.type} showIcon title={notice.text} closable onClose={() => setNotice(undefined)} />}
    {reissue.phase === 'rejected' && <Alert type="error" showIcon title={`补发未执行：${reissue.message}`} />}
    <Card><Details title={data.category_label} rows={[
      ['优先级', <PriorityTag key="priority" value={data.priority} />], ['状态', <TicketStateTag key="state" value={data.state} />],
      ['用户', session.can('users:read') ? <Link key="user" to={`/users/${encodeURIComponent(data.user_id)}`}>{data.user_email}</Link> : data.user_email],
      ['提交时间', time(data.created_at)], ['处理结果', data.resolution ? supportLabel('resolution', data.resolution) : '—'], ['结单时间', time(data.resolved_at)],
    ]} /></Card>
    <Card title="用户说明">
      {/* Rendered as text: user input is never interpreted as markup. */}
      <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{data.user_note ?? '（用户未填写补充说明）'}</Typography.Paragraph>
    </Card>
    {data.checkout && <Card><Details title="用户勾选的订单" rows={[
      ['订单状态', <AdminStateTag key="state" domain="checkout.state" value={data.checkout.state} meta={session.meta} />],
      ['已开通会员', yesNo(data.checkout.fulfilled)], ['创建时间', time(data.checkout.created_at)],
    ]} /></Card>}
    <Card title="用户当前会员"><MembershipSummary membership={data.membership} /></Card>
    <Collapse items={[{ key: 'advanced', label: '高级详情：工单编号与原付款记录', children: <Details rows={[
      ['工单编号', data.id], ['处理人编号', text(data.resolved_by)], ['订单编号', text(data.checkout_id)],
      ['原会员记录状态', <AdminStateTag key="status" domain="membership.status" value={data.membership.status} meta={session.meta} />],
      ['原付款有效期', time(data.membership.expires_at)], ['原付款权益来源', text(data.membership.entitlement_source)],
    ]} /> }]} />
    {data.category === 'membership_not_credited' && <Card title="支付平台核实">
      {data.latest_check
        ? <Space wrap><Tag color={data.latest_check.result === 'verified' ? 'success' : 'warning'}>{supportLabel('check', data.latest_check.result)}</Tag>
            <span>核实时间 {time(data.latest_check.checked_at)}</span>
            {data.latest_check.result === 'verified' && <Tag color={data.latest_check.fresh ? 'processing' : 'default'}>{data.latest_check.fresh ? '在有效期内' : '已过期，需重新核实'}</Tag>}</Space>
        : <Typography.Text type="secondary">尚未核实</Typography.Text>}
    </Card>}
    {data.state !== 'open' && <Card title="已回复用户">
      <Typography.Paragraph>{text(data.reply_text)}</Typography.Paragraph>
      {data.reply_note && <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>补充：{data.reply_note}</Typography.Paragraph>}
    </Card>}
    {/* A closed ticket has no further actions; its outcome is shown above. */}
    {data.state === 'open' && views.some((view) => view.visible) && <Card title="处理">
      <Space orientation="vertical" size="small">
        {views.filter((view) => view.visible && (view.action === 'reply' || view.action === 'reject' || data.category === 'membership_not_credited')).map((view) =>
          <Space key={view.action} wrap>
            <Button type={view.action === 'reissue' ? 'primary' : 'default'} danger={view.action === 'reject'} disabled={!view.enabled}
              loading={view.action === 'verify' && verifying}
              onClick={() => {
                setNotice(undefined);
                if (view.action === 'verify') void verify();
                else if (view.action === 'reissue') dispatch({ type: 'open', key: crypto.randomUUID() });
                else { setReplyMode(view.action); setTemplate(undefined); setNote(''); }
              }}>{ACTION_TEXT[view.action]}</Button>
            {view.reason && <Typography.Text type="secondary">{view.reason}</Typography.Text>}
          </Space>)}
      </Space>
    </Card>}
    <Snapshot value={data.as_of} />
    <Modal title={replyMode === 'reject' ? '驳回并结单' : '回复并结单'} open={replyMode !== undefined} maskClosable={false} confirmLoading={replying}
      onCancel={() => !replying && setReplyMode(undefined)} okText="发送并结单" cancelText="取消" okButtonProps={{ danger: replyMode === 'reject', disabled: !template || noteLength > NOTE_MAX }}
      onOk={() => void sendReply()}>
      <Form layout="vertical">
        <Form.Item label="回复模板" required>
          <Radio.Group value={template} onChange={(event) => setTemplate(event.target.value)}>
            <Space orientation="vertical">{replyTemplates.map((item) => <Radio key={item.id} value={item.id}>{item.name}：{item.text}</Radio>)}</Space>
          </Radio.Group>
        </Form.Item>
        <Form.Item label="补充一句（可选）" htmlFor={noteId} validateStatus={noteLength > NOTE_MAX ? 'error' : undefined} help={`${noteLength} / ${NOTE_MAX} 字，用户可见`}>
          <Input.TextArea id={noteId} value={note} onChange={(event) => setNote(event.target.value)} autoSize={{ minRows: 2, maxRows: 5 }} />
        </Form.Item>
      </Form>
    </Modal>
    <Modal title="审核通过并补发会员" open={reissueOpen} maskClosable={false} confirmLoading={reissue.phase === 'submitting'}
      onCancel={() => dispatch({ type: 'close' })} cancelText="取消"
      okText={reissue.phase === 'unknown' ? '使用原请求确认结果' : '确认补发'} okButtonProps={{ disabled: reissue.phase === 'unknown' && !reissue.refreshed }}
      onOk={() => void sendReissue()}>
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        <Typography.Paragraph>将为 {data.user_email} 按所选订单购买的天数延长会员，订单标记为已开通，工单结单并自动回复用户“已为您补发 N 天会员，请刷新会员页查看”（N 为订单天数）。同一订单只能补发一次；用户会员仍由另一笔付款生效或绑定订阅时服务端会拒绝。</Typography.Paragraph>
        {reissue.phase === 'unknown' && <Alert type="warning" showIcon title="结果未知，请刷新核对"
          description={<Space orientation="vertical"><span>请先查询工单最新状态。若工单已结单则无需再操作；否则可使用原请求确认结果，不会重复补发。</span>
            <Button loading={resource.loading} onClick={async () => { if (await resource.reload()) dispatch({ type: 'refreshed' }); }}>查询工单最新状态</Button></Space>} />}
      </Space>
    </Modal>
  </Space></ReadState>;
}
export default function SupportDetail() {
  const { ticket_id = '' } = useParams<{ ticket_id: string }>();
  return <BusinessGuard permission="support:read"><PageContainer title="工单详情" extra={<Link to="/support">返回工单列表</Link>}><TicketRecord key={ticket_id} id={ticket_id} /></PageContainer></BusinessGuard>;
}
