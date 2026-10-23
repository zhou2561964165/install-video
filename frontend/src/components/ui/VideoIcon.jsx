import React from 'react';

// 与已有 SVG 线性图标保持一致；图标仅装饰，操作名称由相邻文本提供。
const PATHS = {
  check: 'm5 12 4 4L20 5',
  video: 'M15 10l5-3v10l-5-3M5 6h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4',
  summary: 'm12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3Z',
  subtitle: 'M5 3h10l4 4v14H5ZM9 11h6m-6 4h6M14 3v5h5',
  translation: 'M3 5h12M9 3v2m-3 3c1 5 4 8 8 10m-2-10c-1 5-4 8-9 10m12 3 4-12 4 12m-6-4h5',
  transcription: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0ZM5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8',
  mindmap: 'M3 10h6v4H3ZM15 3h6v4h-6Zm0 14h6v4h-6ZM9 12h3m0-7v14m0-14h3m-3 14h3',
  settings: 'M6 3v5m0 4v9M12 3v9m0 4v5M18 3v3m0 4v11M3 8h6m0 4h6m0-6h6',
};
export default function VideoIcon({ name = 'video' }) {
  return <svg className="video-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name] || PATHS.video} /></svg>;
}
