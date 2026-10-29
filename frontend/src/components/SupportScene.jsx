import React, { useCallback, useEffect, useId, useState } from 'react';
import * as defaultApi from '../api.js';

const STATE_LABEL = { open: '处理中', resolved: '已解决', rejected: '已驳回' };
const NOT_CREDITED = 'membership_not_credited';

function timeLabel(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN');
}
const errorText = (error) => error?.error || '请求失败，请稍后重试。';

/** Customer support: submit one ticket (fixed issue types) and read the replies. User text is always rendered as text. */
export default function SupportScene({ authed, onLogin, onBack, api = defaultApi }) {
  const titleId = useId(), typeId = useId(), noteId = useId(), orderId = useId();
  const [tab, setTab] = useState('submit');
  const [meta, setMeta] = useState(null);
  const [metaError, setMetaError] = useState(null);
  const [category, setCategory] = useState('');
  const [checkoutId, setCheckoutId] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const [tickets, setTickets] = useState(null);
  const [ticketsError, setTicketsError] = useState(null);

  const [metaVersion, setMetaVersion] = useState(0);
  useEffect(() => {
    if (!authed) return undefined;
    const controller = new AbortController();
    api.getSupportMeta(controller.signal).then((value) => { setMeta(value); setMetaError(null); })
      .catch((error) => { if (!controller.signal.aborted) setMetaError(error); });
    return () => controller.abort();
  }, [authed, api, metaVersion]);

  const loadTickets = useCallback((signal) => api.listSupportTickets(signal)
    .then((value) => { setTickets(value.items || []); setTicketsError(null); })
    .catch((error) => { if (!signal?.aborted) setTicketsError(error); }), [api]);
  useEffect(() => {
    if (!authed || tab !== 'list') return undefined;
    const controller = new AbortController();
    loadTickets(controller.signal);
    return () => controller.abort();
  }, [authed, tab, loadTickets]);

  const noteMax = meta?.note_max || 500;
  const noteLength = Array.from(note.trim()).length;
  const checkouts = meta?.checkouts || [];
  const needsOrder = category === NOT_CREDITED;
  const canSubmit = Boolean(meta && category && !busy && noteLength <= noteMax && (!needsOrder || checkoutId));

  async function submit(event) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true); setSubmitError(null); setSubmitted(false);
    try {
      await api.submitSupportTicket({ category, note: note.trim() || null, checkout_id: needsOrder ? checkoutId : null });
      setCategory(''); setCheckoutId(''); setNote(''); setSubmitted(true); setTickets(null); setTab('list');
      setMetaVersion((value) => value + 1);  // the appealed order is no longer offered
    } catch (error) { setSubmitError(error); } finally { setBusy(false); }
  }

  return <main className="membership-page support-page" aria-labelledby={titleId}>
    <button type="button" className="video-back membership-back" onClick={onBack}><span aria-hidden="true">←</span> 返回会员方案</button>
    <header className="membership-heading" data-follow-exclude="panel">
      <h1 id={titleId}>联系客服</h1>
      <p>选择问题类型并补充说明，客服会在“我的工单”里回复你。VIP 会员和付款未到账的工单优先处理。</p>
    </header>
    {!authed ? <section className="support-card" data-follow-exclude="panel">
      <p>登录后才能提交工单和查看回复。</p>
      <button type="button" className="support-primary" onClick={onLogin}>登录后联系客服</button>
    </section> : <>
      <div className="support-tabs" role="tablist" aria-label="客服" data-follow-exclude="panel">
        {[['submit', '提交问题'], ['list', '我的工单']].map(([value, label]) =>
          <button key={value} type="button" role="tab" aria-selected={tab === value} className="support-tab" onClick={() => setTab(value)}>{label}</button>)}
      </div>
      {submitted && <p className="membership-notice" role="status">已提交，客服会尽快回复，请留意下方工单状态。</p>}
      {tab === 'submit' ? <form className="support-card" onSubmit={submit} data-follow-exclude="panel" noValidate>
        {metaError && <p className="membership-error" role="alert">{errorText(metaError)}</p>}
        {!meta && !metaError && <p className="support-muted">正在读取问题类型…</p>}
        {meta && <>
          <div className="support-field">
            <span id={typeId} className="support-label">问题类型</span>
            <div role="radiogroup" aria-labelledby={typeId} className="support-options">
              {meta.categories.map((item) => <label key={item.id} className="support-option"><input type="radio" name="support-category" value={item.id}
                checked={category === item.id} onChange={() => { setCategory(item.id); setSubmitError(null); }} />{item.label}</label>)}
            </div>
          </div>
          {needsOrder && <div className="support-field">
            <span id={orderId} className="support-label">未到账的订单</span>
            {checkouts.length ? <div role="radiogroup" aria-labelledby={orderId} className="support-options">
              {checkouts.map((item) => <label key={item.checkout_id} className="support-option"><input type="radio" name="support-checkout" value={item.checkout_id}
                checked={checkoutId === item.checkout_id} onChange={() => setCheckoutId(item.checkout_id)} />订单 {item.label} · {timeLabel(item.created_at)}</label>)}
            </div> : <p className="support-muted">近 90 天没有可申诉的订单。若已扣款但这里看不到订单，请选择“其他问题”并说明付款时间。</p>}
          </div>}
          <div className="support-field">
            <label htmlFor={noteId} className="support-label">补充说明（可选）</label>
            <textarea id={noteId} value={note} rows={4} onChange={(event) => setNote(event.target.value)} aria-describedby={`${noteId}-count`} aria-invalid={noteLength > noteMax} />
            <span id={`${noteId}-count`} className={noteLength > noteMax ? 'support-count support-count--over' : 'support-count'}>{noteLength} / {noteMax}</span>
          </div>
          {submitError && <p className="membership-error" role="alert">{errorText(submitError)}</p>}
          <button type="submit" className="support-primary" disabled={!canSubmit}>{busy ? '正在提交…' : '提交问题'}</button>
        </>}
      </form> : <section className="support-card" aria-label="我的工单" data-follow-exclude="panel">
        {ticketsError && <p className="membership-error" role="alert">{errorText(ticketsError)}</p>}
        {!tickets && !ticketsError && <p className="support-muted">正在读取工单…</p>}
        {tickets && !tickets.length && <p className="support-muted">还没有工单。</p>}
        {tickets && tickets.length > 0 && <ul className="support-tickets">
          {tickets.map((ticket) => <li key={ticket.id} className="support-ticket">
            <div className="support-ticket__head"><strong>{ticket.category_label}</strong>
              <span className={`support-state support-state--${ticket.state}`}>{STATE_LABEL[ticket.state] || ticket.state}</span></div>
            <p className="support-muted">提交于 {timeLabel(ticket.created_at)}{ticket.checkout_label ? ` · 订单 ${ticket.checkout_label}` : ''}</p>
            {ticket.user_note && <p className="support-note">{ticket.user_note}</p>}
            {ticket.reply_text && <div className="support-reply"><span className="support-label">客服回复</span><p>{ticket.reply_text}</p>
              {ticket.reply_note && <p>{ticket.reply_note}</p>}</div>}
          </li>)}
        </ul>}
      </section>}
    </>}
  </main>;
}
