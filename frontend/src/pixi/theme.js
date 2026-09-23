// PIXI 侧统一颜色来源：从 CSS :root token 读取，消除 JS/CSS 双源漂移（H-1）。
//
// 单一来源（source of truth）是 global.css 的 :root 语义 token；本模块的 fallback
// 值与 token 当前值保持一致，仅在「无 DOM / CSS 未就绪（如 jsdom 测试）」时兜底。
// 二者任何一侧改动时需同步维护，避免两侧数值再次漂移。

function cssVar(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    if (v) return v;
  } catch (e) {
    /* 无 DOM 或 CSS 未加载：走 fallback */
  }
  return fallback;
}

// '#rrggbb' → 0xrrggbb（PIXI 数值色）；非法输入回退白色，避免 NaN 引发渲染异常
export function hex(color) {
  const n = parseInt(String(color).replace('#', '').trim(), 16);
  return Number.isNaN(n) ? 0xffffff : n;
}

// 0xrrggbb → 'r,g,b'（供 canvas 渐变构造 rgba() 用）
export function rgb(num) {
  return `${(num >> 16) & 255},${(num >> 8) & 255},${num & 255}`;
}

// 语义 token（key 对齐 global.css :root；fallback 即当前值）
export const palette = {
  accent: cssVar('--accent', '#8b3dff'),
  accentHover: cssVar('--accent-hover', '#6f31cc'),
  accentSoft: cssVar('--accent-soft', '#d87cff'),
  accentLilac: cssVar('--accent-lilac', '#9f8fff'),
  accentPink: cssVar('--accent-pink', '#f0a6d0'),
};
