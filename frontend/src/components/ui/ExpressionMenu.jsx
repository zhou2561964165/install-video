import { useEffect, useRef, useState } from 'react';
import { EXPRESSIONS } from '../../pixi/mascotConfig.js';

// 角色换装/表情菜单：只读 mascotConfig.js 的 EXPRESSIONS.menu 渲染（数据驱动，不写死选项）。
//   open          —— 是否打开（常驻挂载，open 只切 CSS 类，关闭重开不丢选择）
//   onClose       —— 关闭回调（点遮罩 / Escape / 关闭按钮）
//   onExpression  —— (paramId, value) 写参数：1 开 / 0 关（App 接到 mascot.setExpression）
// 分组语义：single = 组内互斥；toggle = 开关；multi = 独立复选。选中态只靠 active 对象本地持有，
// 视觉层不感知下载状态，只负责把「点了哪个」交给 onExpression。
export default function ExpressionMenu({ open, onClose, onExpression, onScale, onFocusFallback,
  canCustomize = true }) {
  const [active, setActive] = useState({});   // paramId → true（当前激活的参数）
  const menuRef = useRef(null);
  const closeRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const focusFallbackRef = useRef(onFocusFallback);
  focusFallbackRef.current = onFocusFallback;

  // Escape 关闭
  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement;
    closeRef.current?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') onCloseRef.current();
      if (e.key !== 'Tab') return;
      const buttons = Array.from(menuRef.current.querySelectorAll('button:not(:disabled)'));
      const first = buttons[0], last = buttons[buttons.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      const style = previousFocus?.isConnected ? getComputedStyle(previousFocus) : null;
      if (style && style.visibility !== 'hidden' && style.display !== 'none' && !previousFocus.closest('[hidden], [inert]')) previousFocus.focus();
      else focusFallbackRef.current?.();
    };
  }, [open]);

  function handleClick(group, option) {
    const { mode, options } = group;
    const { paramId } = option;
    if (mode === 'single') {
      if (active[paramId]) return;   // 已选中：保持，不取消到空
      options.forEach((o) => { if (active[o.paramId]) onExpression(o.paramId, 0); });
      onExpression(paramId, 1);
      setActive((prev) => {
        const next = { ...prev };
        options.forEach((o) => { delete next[o.paramId]; });
        next[paramId] = true;
        return next;
      });
    } else {
      const nextVal = !active[paramId];
      onExpression(paramId, nextVal ? 1 : 0);
      setActive((prev) => {
        const next = { ...prev };
        if (nextVal) next[paramId] = true; else delete next[paramId];
        return next;
      });
    }
  }

  return (
    <>
      {open && <div className="expression-menu-backdrop" onClick={onClose} aria-hidden="true" />}
      <aside
        ref={menuRef}
        className={`expression-menu${open ? ' expression-menu--open' : ''}`}
        role="dialog"
        aria-label={canCustomize ? '角色换装' : '角色控制'}
        aria-hidden={!open}
        aria-modal={open || undefined}
        inert={!open ? '' : undefined}
      >
        <button ref={closeRef} type="button" className="expression-menu__close" onClick={onClose} aria-label="关闭菜单">×</button>
        {canCustomize && <section className="expression-menu__group">
          <h3 className="expression-menu__label">尺寸</h3>
          <div className="expression-menu__scale">
            <button type="button" className="expression-menu__pill" onClick={() => onScale?.(1)}>变大</button>
            <button type="button" className="expression-menu__pill" onClick={() => onScale?.(-1)}>变小</button>
          </div>
        </section>}
        {canCustomize && EXPRESSIONS.menu.map((group) => (
          <section key={group.key} className="expression-menu__group">
            <h3 className="expression-menu__label">{group.label}</h3>
            <div className="expression-menu__options">
              {group.options.map((option) => {
                const on = !!active[option.paramId];
                return (
                  <button
                    key={option.paramId}
                    type="button"
                    className={`expression-menu__pill${on ? ' is-active' : ''}`}
                    aria-pressed={on}
                    onClick={() => handleClick(group, option)}
                  >
                    {option.name}
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </aside>
    </>
  );
}
