import React, { useEffect, useState } from 'react';

// 樱花 Preloader：覆盖 Live2D 模型（16K 纹理）加载期，加载完成淡出后卸载。
// 纯视觉层（只读渲染，不 import 下载核心）；颜色/时长走 global.css token。
//   done —— App 传入，Live2D 就绪后为 true，触发淡出
// 花瓣为数据驱动（PETALS 数组），片数/位置/时长/横向幅度都可在数组里调，不改结构。

const PETALS = [
  { left: '4%', size: 12, dur: 10, delay: 0, sway: 30 },
  { left: '12%', size: 9, dur: 13, delay: 1.5, sway: -36 },
  { left: '22%', size: 11, dur: 11, delay: 0.6, sway: 42 },
  { left: '32%', size: 8, dur: 14, delay: 2.4, sway: -28 },
  { left: '42%', size: 12, dur: 9.5, delay: 0.9, sway: 34 },
  { left: '52%', size: 9, dur: 12.5, delay: 1.9, sway: -40 },
  { left: '62%', size: 11, dur: 10.5, delay: 0.3, sway: 26 },
  { left: '72%', size: 8, dur: 13.5, delay: 2.1, sway: -32 },
  { left: '82%', size: 12, dur: 11.5, delay: 1.1, sway: 38 },
  { left: '92%', size: 9, dur: 10, delay: 0.5, sway: -26 },
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
      <div className="preloader__petals" aria-hidden="true">
        {PETALS.map((p, i) => (
          <span
            key={i}
            className="preloader__petal"
            style={{
              left: p.left,
              width: p.size,
              height: p.size,
              animationDuration: `${p.dur}s`,
              animationDelay: `${p.delay}s`,
              '--sway': `${p.sway}px`,
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
