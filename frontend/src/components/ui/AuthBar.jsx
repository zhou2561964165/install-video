import React from 'react';

// 顶部账号条（仅登录态渲染）：邮箱 + 今日额度余量 + 退出。
export default function AuthBar({ user, quota, onLogout }) {
  const unlimited = quota?.unlimited === true;
  const limited = Number.isInteger(quota?.remaining) && Number.isInteger(quota?.limit);
  const exhausted = !unlimited && limited && quota.remaining <= 0;
  const quotaStatus = unlimited ? '下载额度不限'
    : limited ? (exhausted ? '今日额度已用完' : `今日剩余 ${quota.remaining}/${quota.limit}`)
      : null;
  return (
    <div className="auth-bar">
      <span className="auth-bar__email">{user?.email}</span>
      {quotaStatus && (
        <span role="status" aria-atomic="true" className={exhausted ? 'auth-bar__quota auth-bar__exhausted' : 'auth-bar__quota'}>
          {quotaStatus}
        </span>
      )}
      <button type="button" className="auth-bar__logout" onClick={onLogout}>退出</button>
    </div>
  );
}
