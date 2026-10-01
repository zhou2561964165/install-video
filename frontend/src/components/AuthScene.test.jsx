import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AuthScene from './AuthScene.jsx';

vi.mock('../audio/audioManager.js', () => ({
  unlock: vi.fn(),
  playSfx: vi.fn(),
}));

describe('AuthScene', () => {
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
