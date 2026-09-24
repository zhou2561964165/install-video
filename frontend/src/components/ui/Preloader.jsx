import React, { useEffect, useState } from 'react';

// 折射光点 Preloader：覆盖 Live2D 模型（16K 纹理）加载期，加载完成淡出后卸载。
// 纯视觉层（只读渲染，不 import 下载核心）；颜色/时长走 global.css token。
//   done —— App 传入，Live2D 就绪后为 true，触发淡出
// 光点为数据驱动（SPOTS 数组），片数/位置/时长/横向幅度/折射色都可在数组里调，不改结构。

const SPOTS = [
  { left: '4%', size: 12, dur: 10, delay: 0, sway: 30, color: 'var(--refract-pink)' },
  { left: '12%', size: 9, dur: 13, delay: 1.5, sway: -36, color: 'var(--refract-cyan)' },
  { left: '22%', size: 11, dur: 11, delay: 0.6, sway: 42, color: 'var(--refract-violet)' },
  { left: '32%', size: 8, dur: 14, delay: 2.4, sway: -28, color: 'var(--refract-mint)' },
  { left: '42%', size: 12, dur: 9.5, delay: 0.9, sway: 34, color: 'var(--refract-warm)' },
  { left: '52%', size: 9, dur: 12.5, delay: 1.9, sway: -40, color: 'var(--refract-pink)' },
  { left: '62%', size: 11, dur: 10.5, delay: 0.3, sway: 26, color: 'var(--refract-cyan)' },
  { left: '72%', size: 8, dur: 13.5, delay: 2.1, sway: -32, color: 'var(--refract-violet)' },
  { left: '82%', size: 12, dur: 11.5, delay: 1.1, sway: 38, color: 'var(--refract-mint)' },
  { left: '92%', size: 9, dur: 10, delay: 0.5, sway: -26, color: 'var(--refract-warm)' },
];

export default function Preloader({ done }) {
  const [hide, setHide] = useState(false);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    if (!done) return;
    setHide(true); // 先淡出
    const t = setTimeout(() => setGone(true), 320); // 略大于 --dur(.25s)，淡出完再卸载
    return () => clearTimeout(t);
  }, [done]);

  if (gone) return null;

  return (
    <div className={`preloader${hide ? ' preloader--hide' : ''}`} data-testid="preloader" role="status" aria-label="加载中">
      <div className="preloader__spots" aria-hidden="true">
        {SPOTS.map((s, i) => (
          <span
            key={i}
            className="preloader__spot"
            style={{
              left: s.left,
              width: s.size,
              height: s.size,
              '--spot': s.color,
              animationDuration: `${s.dur}s`,
              animationDelay: `${s.delay}s`,
              '--sway': `${s.sway}px`,
            }}
          />
        ))}
      </div>
      <div className="preloader__inner">
        <svg className="preloader__mark" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
          <path d="M12 2C8.6 5 7 8.8 7 12.4 7 17 9.2 21 12 22c2.8-1 5-5 5-9.6C17 8.8 15.4 5 12 2Z" />
        </svg>
        <h1 className="preloader__title">万能视频下载</h1>
        <div className="preloader__spinner" aria-hidden="true" />
        <p className="preloader__hint">正在唤醒小白…</p>
      </div>
    </div>
  );
}
