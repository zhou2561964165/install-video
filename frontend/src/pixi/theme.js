// PIXI 侧统一颜色来源：从 CSS :root token 读取，消除 JS/CSS 双源漂移（H-1）。
//
// 单一来源（source of truth）是 styles/tokens.css 的 :root 语义 token；palette fallback
// 对齐浅色语义，仅在「无 DOM / CSS 未就绪（如 jsdom 测试）」时兜底。
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

// 语义 token（key 对齐 tokens.css :root；fallback 为浅色值）
export const palette = {
  accent: cssVar('--accent', '#345ed5'),
  accentHover: cssVar('--accent-hover', '#294bb2'),
  accentSoft: cssVar('--accent-soft', '#b9ccff'),
  accentLilac: cssVar('--accent-lilac', '#996fff'),
  accentPink: cssVar('--accent-pink', '#ff6cae'),
  // 折射五色（跨主题恒定，对齐 global.css --refract-*；PIXI 光点/描边用，必须 hex 否则 hex() 回退白）
  refractCyan: cssVar('--refract-cyan', '#47a9ff'),
  refractViolet: cssVar('--refract-violet', '#996fff'),
  refractPink: cssVar('--refract-pink', '#ff6cae'),
  refractMint: cssVar('--refract-mint', '#53ddb8'),
  refractWarm: cssVar('--refract-warm', '#ffc062'),
};

// 初始化时读取 surface（必须 hex），无 CSS 时用纯白安全兜底；透明画布的可见底色由 CSS 响应主题。
export const baseColor = cssVar('--surface', '#ffffff');
