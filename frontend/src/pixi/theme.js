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
  accent: cssVar('--accent', '#d6336c'),
  accentHover: cssVar('--accent-hover', '#bd2a5b'),
  accentSoft: cssVar('--accent-soft', '#f8c3cd'),
  accentLilac: cssVar('--accent-lilac', '#996fff'),
  accentPink: cssVar('--accent-pink', '#ff6cae'),
  // 折射五色（跨主题恒定，对齐 global.css --refract-*；PIXI 光点/描边用，必须 hex 否则 hex() 回退白）
  refractCyan: cssVar('--refract-cyan', '#47a9ff'),
  refractViolet: cssVar('--refract-violet', '#996fff'),
  refractPink: cssVar('--refract-pink', '#ff6cae'),
  refractMint: cssVar('--refract-mint', '#53ddb8'),
  refractWarm: cssVar('--refract-warm', '#ffc062'),
};

// PIXI 渲染器底色：对齐 CSS 深色底（--ink-900），画布透明时的兜底色，避免纯黑闪烁（必须 hex）
export const baseColor = cssVar('--ink-900', '#0a0a0f');
