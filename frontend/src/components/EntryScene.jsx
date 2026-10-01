import React, { useEffect, useRef, useState } from 'react';
import { unlock, playSfx } from '../audio/audioManager.js';

// 落地页文案/数据：数据驱动，加卡片/步骤/示例只改这里（工程约定 §3 不写死）
const PARSE_POINTS = [
  { title: '多平台识别', desc: 'B站、YouTube、抖音、快手… 粘贴即自动识别来源，无需手动选平台。' },
  { title: '元数据一次到位', desc: '标题、封面、时长、UP主、播放量、字幕一并解析，下载前先看全。' },
  { title: '清晰度自动预选', desc: '列出全部档位与音视频组合，替你挑好最合适的那一条。' },
];

const DOWNLOAD_POINTS = [
  { title: '清晰度分档', desc: '360p 到 4K 逐档可选，1080p 起自动合并音视频，画质不妥协。' },
  { title: '音视频分离', desc: '只想听歌下音频，只想存画面下视频，各取所需互不浪费。' },
  { title: '直链秒下', desc: '支持直链的资源免服务器中转，浏览器原生下载，快且不排队。' },
];

const STEPS = [
  { num: '01', title: '粘贴链接', desc: '把视频链接粘进上方输入框。' },
  { num: '02', title: '选择格式', desc: '挑清晰度与文件类型。' },
  { num: '03', title: '下载保存', desc: '一键保存到本地，完成！' },
];

const EXAMPLES = [
  'https://download.samplelib.com/mp4/sample-5s.mp4',
  'https://www.bilibili.com/video/BV1xx411c7mD',
  'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
];

// 示例 chip 只显示域名，避免长 URL 撑破布局（URL 解析失败时截断兜底）
const exampleLabel = (u) => {
  try { return new URL(u).hostname.replace(/^www\./, ''); } catch { return u.slice(0, 20); }
};

export default function EntryScene({ onSubmit }) {
  const [url, setUrl] = useState('');
  const inputRef = useRef(null);

  const submit = (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    unlock();
    playSfx('paste');
    onSubmit(url.trim());
  };

  // 收尾 CTA：回到顶部并聚焦输入框（reduced-motion 时用瞬时滚动）
  const backToTop = () => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
    inputRef.current?.focus();
  };

  // 滚动聚焦：当前章节锐利展示、上下章节轻微模糊（对齐 pidanai 滚动叙事）
  // 用滚动监听而非 IntersectionObserver：IO 在快速滚动/拖动滚动条时可能跳过中间章节，滚动监听更稳。
  useEffect(() => {
    const sections = Array.from(document.querySelectorAll('.landing > section'));
    if (sections.length < 2) return;
    const seen = new Set();

    // 用 offsetTop 链求「文档坐标」而非 getBoundingClientRect()：后者含 transform，
    // 会与 .is-pending 的 translateY 互相干扰，导致「已进入」判定漂移。
    const docTop = (el) => {
      let y = 0;
      for (let n = el; n; n = n.offsetParent) y += n.offsetTop;
      return y;
    };

    const update = () => {
      const vh = window.innerHeight;
      const mid = vh / 2;
      const scrollTop = window.scrollY || document.documentElement.scrollTop || 0;
      let active = null;
      for (const s of sections) {
        const top = docTop(s) - scrollTop;            // 视口内布局位置（无视 transform）
        const bottom = top + s.offsetHeight;
        if (active === null && top <= mid && bottom >= mid) active = s;
        if (top < vh * 0.9) seen.add(s);              // 顶越过 90% 线即「已进入视口」
      }
      if (active === null) active = sections[0];
      sections.forEach((s) => {
        const isSeen = seen.has(s);
        const isActive = s === active;
        s.classList.toggle('is-pending', !isSeen);
        s.classList.toggle('is-blurred', isSeen && !isActive);
      });
    };

    const onScroll = () => update();
    update(); // 初始检查：覆盖「刷新时已停留在下方」的恢复滚动位置场景
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  return (
    <div data-testid="entry-scene" className="entry-scene">
      <div className="landing">
        <section className="landing-hero" aria-label="粘贴视频链接">
          <div className="landing-hero__content">
            <p className="landing-hero__eyebrow">视频下载 · 多平台</p>
            <h1 className="landing-hero__title">粘贴链接，秒速下载</h1>
            <p className="landing-hero__subtitle">
              B站 · YouTube · 抖音 等平台视频与音频，粘贴即可解析，一键保存到本地。
            </p>
            <form className="landing-form" onSubmit={submit}>
              <input
                ref={inputRef}
                aria-label="视频链接"
                placeholder="https://…"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <button type="submit">解析</button>
            </form>
            <div className="landing-examples">
              <span className="landing-examples__label">试试</span>
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  className="landing-examples__chip"
                  onClick={() => setUrl(ex)}
                >
                  {exampleLabel(ex)}
                </button>
              ))}
            </div>
          </div>
          <div className="landing-hero__scroll" aria-hidden="true">
            <span>向下滚动</span>
          </div>
        </section>

        <section className="landing-chapter" aria-labelledby="parse-title">
          <p className="landing-chapter__eyebrow">一键解析 · 多平台</p>
          <h2 id="parse-title" className="landing-chapter__title">粘贴即解析，秒出结果</h2>
          <p className="landing-chapter__desc">
            不用下载任何软件，也不用先选平台。把链接丢进来，来源识别、元数据、清晰度档位一次算好，
            你要做的只剩「点下载」。
          </p>
          <div className="landing-points">
            {PARSE_POINTS.map((p) => (
              <article key={p.title} className="landing-point">
                <h3 className="landing-point__title">{p.title}</h3>
                <p className="landing-point__desc">{p.desc}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-chapter" aria-labelledby="download-title">
          <p className="landing-chapter__eyebrow">多格式下载</p>
          <h2 id="download-title" className="landing-chapter__title">要视频要音频，随你挑</h2>
          <p className="landing-chapter__desc">按需选择格式与清晰度，想怎么下就怎么下。</p>
          <div className="landing-points">
            {DOWNLOAD_POINTS.map((p) => (
              <article key={p.title} className="landing-point">
                <h3 className="landing-point__title">{p.title}</h3>
                <p className="landing-point__desc">{p.desc}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-chapter" aria-labelledby="howto-title">
          <p className="landing-chapter__eyebrow">三步搞定</p>
          <h2 id="howto-title" className="landing-chapter__title">三步，从链接到本地文件</h2>
          <ol className="landing-steps">
            {STEPS.map((s) => (
              <li key={s.num} className="landing-step">
                <span className="landing-step__num">{s.num}</span>
                <h3 className="landing-step__title">{s.title}</h3>
                <p className="landing-step__desc">{s.desc}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-outro" aria-label="开始下载">
          <p className="landing-chapter__eyebrow">视频下载 · 多平台 · 免安装</p>
          <h2 className="landing-chapter__title">你好，这里是万能视频下载</h2>
          <p className="landing-outro__tagline">从粘贴链接到保存文件，只隔一次点击。现在就把链接交给我。</p>
          <button type="button" className="landing-outro__cta" onClick={backToTop}>
            立即解析
          </button>
        </section>
      </div>
    </div>
  );
}
