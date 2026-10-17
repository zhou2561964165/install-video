import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExpressionMenu from './ExpressionMenu.jsx';
import { EXPRESSIONS } from '../../pixi/mascotConfig.js';

describe('角色菜单键盘入口', () => {
  it('保留原有尺寸和全部表情入口，不展示位置或活动控制', () => {
    const onMove = vi.fn(), onReset = vi.fn(), onToggleMotion = vi.fn();
    render(<ExpressionMenu open onClose={vi.fn()} onMove={onMove} onReset={onReset} onToggleMotion={onToggleMotion} motionEnabled={false} />);
    const expressionCount = EXPRESSIONS.menu.reduce((total, group) => total + group.options.length, 0);
    expect(screen.getByRole('button', { name: '变大' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '短发', exact: true })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(expressionCount + 3);
    expect(screen.queryByText('位置与活动')).toBeNull();
    for (const name of ['向上移动', '向下移动', '向左移动', '向右移动', '角色复位', '暂停活动', '恢复活动']) {
      expect(screen.queryByRole('button', { name })).toBeNull();
    }
    expect(onMove).not.toHaveBeenCalled();
    expect(onReset).not.toHaveBeenCalled();
    expect(onToggleMotion).not.toHaveBeenCalled();
  });
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
  it('角色入口隐藏后关闭菜单，聚焦提供的可见后备控件', () => {
    const launcher = document.createElement('button'), input = document.createElement('input');
    document.body.append(launcher, input); launcher.focus();
    const props = { onClose: vi.fn(), onExpression: vi.fn(), onFocusFallback: () => input.focus() };
    const view = render(<ExpressionMenu {...props} open={false} />);
    view.rerender(<ExpressionMenu {...props} open />);
    launcher.style.visibility = 'hidden';
    view.rerender(<ExpressionMenu {...props} open={false} />);
    expect(input).toHaveFocus(); view.unmount(); launcher.remove(); input.remove();
  });
});
