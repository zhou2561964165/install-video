import React from 'react';

// 顶部账号条（仅登录态渲染）：邮箱 + 今日额度余量 + 退出。
export default function AuthBar({ user, quota, onLogout }) {
  const exhausted = quota && quota.remaining <= 0;
  return (
    <div className="auth-bar">
      <span className="auth-bar__email">{user?.email}</span>
      {quota && (
        <span className={exhausted ? 'auth-bar__quota auth-bar__exhausted' : 'auth-bar__quota'}>
          {exhausted ? '今日额度已用完' : `今日剩余 ${quota.remaining}/${quota.limit}`}
        </span>
      )}
      <button type="button" className="auth-bar__logout" onClick={onLogout}>退出</button>
    </div>
  );
}
