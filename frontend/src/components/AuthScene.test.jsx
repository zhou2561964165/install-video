import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AuthScene from './AuthScene.jsx';

vi.mock('../audio/audioManager.js', () => ({
  unlock: vi.fn(),
  playSfx: vi.fn(),
}));

describe('AuthScene', () => {
  it('进入登录页聚焦邮箱，返回按钮调用首页回调', async () => {
    const onBack = vi.fn();
    render(<AuthScene loading={false} onLogin={vi.fn()} onRegister={vi.fn()} onBack={onBack} />);
    expect(screen.getByLabelText('邮箱')).toHaveFocus();
    await userEvent.click(screen.getByRole('button', { name: '返回首页' }));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it('提交中禁止返回，请求失败后可返回', async () => {
    let reject;
    const onLogin = vi.fn(() => new Promise((_resolve, rejectRequest) => { reject = rejectRequest; }));
    const onBack = vi.fn();
    render(<AuthScene loading={false} onLogin={onLogin} onRegister={vi.fn()} onBack={onBack} />);
    await userEvent.type(screen.getByLabelText('邮箱'), 'a@b.com');
    await userEvent.type(screen.getByLabelText('密码'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: '立即登录' }));
    expect(screen.getByRole('button', { name: '返回首页' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '返回首页' }));
    expect(onBack).not.toHaveBeenCalled();
    await act(async () => reject({ error: '登录失败' }));
    expect(screen.getByRole('button', { name: '返回首页' })).toBeEnabled();
  });

  it('loading 时显示恢复态，无表单', () => {
    render(<AuthScene loading onLogin={vi.fn()} onRegister={vi.fn()} />);
    expect(screen.getByTestId('auth-scene')).toBeInTheDocument();
    expect(screen.queryByLabelText('邮箱')).not.toBeInTheDocument();
  });

  it('登录提交调用 onLogin', async () => {
    const onLogin = vi.fn().mockResolvedValue({ token: 't', user: {} });
    const onRegister = vi.fn();
    render(<AuthScene loading={false} onLogin={onLogin} onRegister={onRegister} />);
    await userEvent.type(screen.getByLabelText('邮箱'), 'a@b.com');
    await userEvent.type(screen.getByLabelText('密码'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: '立即登录' }));
    expect(onLogin).toHaveBeenCalledWith('a@b.com', 'password123');
    expect(onRegister).not.toHaveBeenCalled();
  });

  it('注册 tab 提交调用 onRegister', async () => {
    const onLogin = vi.fn();
    const onRegister = vi.fn().mockResolvedValue({ token: 't', user: {} });
    render(<AuthScene loading={false} onLogin={onLogin} onRegister={onRegister} />);
    await userEvent.click(screen.getByRole('button', { name: '注册' }));
    await userEvent.type(screen.getByLabelText('邮箱'), 'a@b.com');
    await userEvent.type(screen.getByLabelText('密码'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: '立即注册' }));
    expect(onRegister).toHaveBeenCalledWith('a@b.com', 'password123');
    expect(onLogin).not.toHaveBeenCalled();
  });

  it('注册前本地校验邮箱与密码长度，不发请求并聚焦第一个错误字段', async () => {
    const onRegister = vi.fn();
    render(<AuthScene loading={false} onLogin={vi.fn()} onRegister={onRegister} />);
    await userEvent.click(screen.getByRole('button', { name: '注册' }));
    await userEvent.type(screen.getByLabelText('邮箱'), 'invalid-email');
    await userEvent.type(screen.getByLabelText('密码'), '1');
    await userEvent.click(screen.getByRole('button', { name: '立即注册' }));
    expect(onRegister).not.toHaveBeenCalled();
    expect(screen.getByText('请输入有效的邮箱地址，例如 you@example.com')).toBeInTheDocument();
    expect(screen.getByText('密码至少 8 位')).toBeInTheDocument();
    expect(screen.getByLabelText('邮箱')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('邮箱')).toHaveFocus();
    expect(screen.getByRole('button', { name: '立即注册' })).not.toHaveTextContent('注册中');
  });

  it('注册字段失焦即提示，修正后提示消失', async () => {
    render(<AuthScene loading={false} onLogin={vi.fn()} onRegister={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: '注册' }));
    await userEvent.type(screen.getByLabelText('邮箱'), 'a@b');
    await userEvent.tab();
    expect(screen.getByText('请输入有效的邮箱地址，例如 you@example.com')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('邮箱'), '.com');
    expect(screen.queryByText('请输入有效的邮箱地址，例如 you@example.com')).toBeNull();
  });

  it('登录不做长度校验（已有账号按服务端判断）', async () => {
    const onLogin = vi.fn().mockResolvedValue({});
    render(<AuthScene loading={false} onLogin={onLogin} onRegister={vi.fn()} />);
    await userEvent.type(screen.getByLabelText('邮箱'), 'a@b.com');
    await userEvent.type(screen.getByLabelText('密码'), '1');
    await userEvent.click(screen.getByRole('button', { name: '立即登录' }));
    expect(onLogin).toHaveBeenCalledWith('a@b.com', '1');
  });

  it('登录失败就近展示错误', async () => {
    const onLogin = vi.fn().mockRejectedValue({ error: '邮箱或密码错误' });
    render(<AuthScene loading={false} onLogin={onLogin} onRegister={vi.fn()} />);
    await userEvent.type(screen.getByLabelText('邮箱'), 'a@b.com');
    await userEvent.type(screen.getByLabelText('密码'), 'wrongpass');
    await userEvent.click(screen.getByRole('button', { name: '立即登录' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('邮箱或密码错误');
  });

  it('密码 show/hide 切换', async () => {
    render(<AuthScene loading={false} onLogin={vi.fn()} onRegister={vi.fn()} />);
    const pw = screen.getByLabelText('密码');
    expect(pw).toHaveAttribute('type', 'password');
    await userEvent.click(screen.getByRole('button', { name: '显示密码' }));
    expect(pw).toHaveAttribute('type', 'text');
    await userEvent.click(screen.getByRole('button', { name: '隐藏密码' }));
    expect(pw).toHaveAttribute('type', 'password');
  });
});
