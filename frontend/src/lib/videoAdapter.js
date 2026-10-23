// 解析结果归一化/格式化：把后端 ParseResponse 映射为前端展示友好结构。
// 纯函数、无副作用，便于单测与复用；后续 AI 总结等能力在此透传原始字段即可。

export function formatDuration(seconds) {
  if (seconds == null) return '';
  const total = Math.round(Number(seconds));
  if (!Number.isFinite(total) || total < 0) return '';
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function formatViewCount(count) {
  if (count == null) return '';
  const n = Number(count);
  if (!Number.isFinite(n) || n < 0) return '';
  if (n >= 100000000) return `${(n / 100000000).toFixed(1)}亿`;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return n.toLocaleString();
}

// 格式列表的辅助行文案（参考站：ext + 含音频/仅视频）。has_audio 缺省按含音频（后端默认 True）。
export function formatMetaLine(format) {
  const ext = (format?.ext || 'mp4').toUpperCase();
  const audio = format?.has_audio === false ? '仅视频' : '含音频';
  return `${ext} · ${audio}`;
}

export function normalizeParse(raw) {
  const r = raw || {};
  return {
    ...r,
    durationLabel: formatDuration(r.duration),
    viewCountLabel: formatViewCount(r.view_count),
    formats: (r.formats || []).map((f) => ({
      ...f,
      ...(f.height === 2160 && !/4k/i.test(f.label || '') ? { label: `4K · ${f.label || '2160p'}` } : {}),
      metaLine: formatMetaLine(f),
    })),
  };
}
