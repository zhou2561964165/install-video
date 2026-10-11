import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DoneScene from './DoneScene.jsx';

describe('DoneScene save controls', () => {
  it('delegates save to its callback without an unauthenticated file link', () => {
    const onSave = vi.fn();
    render(<DoneScene job={{ title: 'T' }} onSave={onSave} onReset={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /保存文件/ }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('link')).toBeNull();
  });
  it('announces waiting and prevents repeated saves while busy', () => {
    render(<DoneScene onSave={() => {}} saveBusy onReset={() => {}} />);
    expect(screen.getByRole('button', { name: /保存/ })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('正在获取文件');
  });
  it('shows save failure with an enabled retry while preserving completion', () => {
    render(<DoneScene onSave={() => {}} saveError={{ error: '请重新登录' }} onReset={() => {}} />);
    expect(screen.getByRole('alert')).toHaveTextContent('请重新登录');
    expect(screen.getByRole('button', { name: /保存文件/ })).toBeEnabled();
    expect(screen.getByText(/下载完成/)).toBeInTheDocument();
  });
});
