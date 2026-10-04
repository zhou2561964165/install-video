import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExpressionMenu from './ExpressionMenu.jsx';

describe('角色菜单键盘入口', () => {
  it('打开后聚焦关闭按钮，Tab 不移到背后的表单，关闭后恢复入口焦点', async () => {
    const button = document.createElement('button');
    document.body.appendChild(button);
    button.focus();
    const onClose = vi.fn();
    const { rerender, unmount } = render(<ExpressionMenu open={false} onClose={onClose} onExpression={vi.fn()} />);
    rerender(<ExpressionMenu open onClose={onClose} onExpression={vi.fn()} />);
    const close = screen.getByRole('button', { name: '关闭菜单' });
    expect(close).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole('dialog')).toContainElement(document.activeElement);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
    rerender(<ExpressionMenu open={false} onClose={onClose} onExpression={vi.fn()} />);
    expect(button).toHaveFocus();
    unmount(); button.remove();
  });
});
