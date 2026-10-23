import React from 'react';
import VideoIcon from './ui/VideoIcon.jsx';

const FREE_FEATURES = ['不限下载次数', '基础视频信息解析', '支持的来源以实际解析结果为准'];
const VIP_FEATURES = ['不限下载次数', '来源支持时可下载 4K / 8K', '字幕读取、下载与翻译', 'AI 视频内容总结'];
const STATUS = { active: 'VIP 已生效', trialing: 'VIP 试用中', expired: '会员已到期', canceled: '会员已取消', past_due: '账单待处理', unpaid: '账单待支付', incomplete: '支付尚未完成', free: '免费版' };

function expiryLabel(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString('zh-CN');
}

export default function MembershipScene({ membership, authed, authLoading, onLogin, onBack, paymentReturn, loginIntent }) {
  const { plans, plansError, account, loading, error, busy, refresh, cancelAction, checkout, portal } = membership;
  const vip = authed && account?.plan === 'vip';
  const freeMaxHeight = Number.isInteger(plans?.free_max_height) && plans.free_max_height > 0 && plans.free_max_height <= 720 ? plans.free_max_height : 720;
  const freeFeatures = [FREE_FEATURES[0], `最高支持 ${freeMaxHeight}p 清晰度`, ...FREE_FEATURES.slice(1)];
  const available = plans?.checkout_available && (!authed || account?.checkout_available);
  const expiry = expiryLabel(account?.expires_at);
  const checkoutLabel = vip ? '当前方案' : !plans?.checkout_available ? '暂未开放支付' : !authed ? '登录后开通 VIP' : loading ? '正在确认会员状态…' : available ? '通过 Stripe 开通 VIP' : '暂未开放支付';

  return <main className="membership-page" aria-labelledby="membership-title">
    <button type="button" className="video-back membership-back" onClick={onBack}><span aria-hidden="true">←</span> 返回下载</button>
    <header className="membership-heading" data-follow-exclude="panel">
      <p className="membership-eyebrow">为你的收藏，选择更多可能</p>
      <h1 id="membership-title">选择适合你的下载方案</h1>
      <p>免费版满足日常下载，VIP 解锁高清画质与视频内容工具。</p>
    </header>
    {loginIntent && authed && <p className="membership-notice" role="status">已登录。请查看价格与计费说明，再点击开通 VIP。</p>}
    {paymentReturn && <div className="membership-notice" role="status">
      {paymentReturn === 'success' ? vip ? '服务器已确认当前 VIP 权益，请以下方有效期为准。' : '已从支付页面返回。支付结果正在由服务器确认，请刷新会员状态；确认前不会开通 VIP。' : paymentReturn === 'cancel' ? '已取消本次支付。会员权益以服务器显示的当前状态为准。' : '已从账单管理返回，请刷新会员状态查看最新权益。'}
    </div>}
    {authed && <section className="membership-account" aria-label="当前会员状态" data-follow-exclude="panel">
      <div><strong>{loading ? '正在读取会员状态…' : account ? (vip ? STATUS[account.status] || 'VIP 已生效' : STATUS[account.status] || '免费版') : '会员状态暂不可用'}</strong>
        {expiry && <p>{account.cancel_at_period_end ? '已取消续费，权益保留至' : '权益有效期至'} {expiry}</p>}
        {vip && account.cancel_at_period_end && !expiry && <p>已取消续费，当前有效期内仍可使用 VIP。</p>}
      </div>
      <div className="membership-account__actions"><button type="button" onClick={refresh} disabled={loading || Boolean(busy)}>刷新会员状态</button>
        {account?.portal_available && <button type="button" onClick={portal} disabled={Boolean(busy)}>{busy === 'portal' ? '正在前往账单…' : '管理账单'}</button>}</div>
    </section>}
    {(error || plansError) && <p className="membership-error" role="alert">{(error || plansError).error || '暂时无法读取会员信息，请稍后重试。'}</p>}
    <div className="membership-grid">
      <section className="membership-card membership-card--free" aria-labelledby="free-plan-title" data-follow-exclude="panel">
        <div><h2 id="free-plan-title">免费版</h2><p className="membership-card__subtitle">满足基础下载需求</p></div>
        <p className="membership-price">¥0 <span>/ 永久</span></p>
        <ul>{freeFeatures.map((feature) => <li key={feature}><VideoIcon name="check" /><span>{feature}</span></li>)}</ul>
        <button type="button" className="membership-card__cta" onClick={onBack}>{vip ? '返回下载' : '当前方案 · 免费版'}</button>
      </section>
      <section className="membership-card membership-card--vip" aria-labelledby="vip-plan-title" data-follow-exclude="panel">
        <div className="membership-card__top"><div><h2 id="vip-plan-title">VIP 高级版</h2><p className="membership-card__subtitle">高清下载，让内容更好用</p></div><span className="membership-badge">推荐</span></div>
        <div className="membership-price-group"><p className="membership-price">{plans?.price_label || '价格待定'}</p><p className="membership-billing">{plans?.renewal_label || '价格与计费周期确认后开放支付'}</p></div>
        <ul>{VIP_FEATURES.map((feature) => <li key={feature}><VideoIcon name="check" /><span>{feature}</span></li>)}
          <li className="membership-feature--pending"><VideoIcon name="check" /><span>批量下载 <small>即将支持</small></span></li>
          <li className="membership-feature--pending"><VideoIcon name="check" /><span>优先客服支持 <small>筹备中</small></span></li>
        </ul>
        <button type="button" className="membership-card__cta" onClick={authed ? checkout : onLogin} disabled={authLoading || Boolean(busy) || !plans?.checkout_available || (authed && (loading || vip || !available || !account))}>{busy === 'checkout' ? '正在前往 Stripe…' : checkoutLabel}</button>
      </section>
    </div>
    <footer className="membership-footnote" data-follow-exclude="panel"><p>不限下载次数；仍受来源可用性、合理使用、并发与服务器资源限制。画质以视频来源实际提供的格式为准。</p><p>支付由 Stripe 托管处理，本站不收集银行卡信息。{plans?.billing_mode === 'subscription' ? '当前方案自动续费，可在账单管理中取消后续续费。' : plans?.billing_mode === 'payment' ? '当前方案为一次性支付，到期后不自动续费。' : '支付尚未配置，暂不收款。'}</p></footer>
    {busy && <button type="button" className="membership-cancel" onClick={cancelAction}>取消跳转</button>}
  </main>;
}
