import React, { useEffect, useRef, useState } from 'react';
import { unlock, playSfx } from '../audio/audioManager.js';
import VideoIcon from './ui/VideoIcon.jsx';
import LandingFeatures from './ui/LandingFeatures.jsx';

// 落地页文案/数据：数据驱动，加卡片/步骤/示例只改这里（工程约定 §3 不写死）
const PARSE_POINTS = [
  { title: '链接解析', desc: '粘贴支持站点的视频链接，查看来源可提供的视频信息与格式。' },
  { title: '信息预览', desc: '有可用信息时，可查看标题、封面、时长、作者与格式选项。' },
  { title: '按需选择', desc: '解析后预选首个可用格式，也可以自行调整清晰度与保存方式。' },
];

const DOWNLOAD_POINTS = [
  { title: '格式选择', desc: '在来源提供的选项中选择视频清晰度和封装格式。' },
  { title: '原标题保存', desc: '网页默认按视频标题命名，也可选择使用来源直链。' },
  { title: '字幕整理', desc: '可查看、翻译字幕，并为短篇、中篇和长篇生成 AI 内容总结。' },
];

const STEPS = [
  { num: '01', title: '粘贴链接', desc: '输入支持站点的视频链接。' },
  { num: '02', title: '查看解析', desc: '选择可用格式与保存方式。' },
  { num: '03', title: '下载或整理', desc: '保存视频，或读取、翻译字幕并生成内容总结。' },
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

export default function EntryScene({ onSubmit, mascotSlot, initialUrl = '', onUrlChange, focusInput = false, notice = '' }) {
  const [localUrl, setLocalUrl] = useState(initialUrl);
  const url = onUrlChange ? initialUrl : localUrl;
  const setUrl = onUrlChange || setLocalUrl;
  const inputRef = useRef(null);
  useEffect(() => { if (focusInput) inputRef.current?.focus(); }, [focusInput]);

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
        <section className="landing-hero" aria-label="粘贴视频链接" data-ui-follow>
          <div className="landing-hero__content">
            <h1 className="landing-hero__title" data-follow-plane><span className="landing-hero__title-line">把视频，</span><span className="landing-hero__title-line">留在身边</span></h1>
            <form className="landing-form" data-follow-exclude="parse" onSubmit={submit}>
              <input
                ref={inputRef}
                aria-label="视频链接"
                aria-describedby={notice ? 'entry-auth-notice' : undefined}
                placeholder="https://…"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <button type="submit"><VideoIcon name="video" />解析</button>
            </form>
            {notice && <p id="entry-auth-notice" className="landing-form__notice" role="status">{notice}</p>}
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
          <LandingFeatures />
          {mascotSlot}
        </section>

        <section id="features" className="landing-chapter" aria-labelledby="parse-title" data-ui-follow>
          <h2 id="parse-title" className="landing-chapter__title" data-follow-plane>先看清信息，再决定怎么保存</h2>
          <p className="landing-chapter__desc">
            可用的平台信息和格式由视频来源提供；解析后先预选一个格式，你仍可按需调整。
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

        <section className="landing-chapter" aria-labelledby="download-title" data-ui-follow>
          <h2 id="download-title" className="landing-chapter__title" data-follow-plane>下载视频，也整理视频内容</h2>
          <p className="landing-chapter__desc">字幕功能取决于来源是否提供可读取的字幕；总结支持短篇、中篇和有长度上限的长篇内容。</p>
          <div className="landing-points">
            {DOWNLOAD_POINTS.map((p) => (
              <article key={p.title} className="landing-point">
                <h3 className="landing-point__title">{p.title}</h3>
                <p className="landing-point__desc">{p.desc}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="how-it-works" className="landing-chapter" aria-labelledby="howto-title" data-ui-follow>
          <h2 id="howto-title" className="landing-chapter__title" data-follow-plane>三步，完成下载或字幕整理</h2>
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

        <section className="landing-outro" aria-label="开始下载" data-ui-follow>
          <h2 className="landing-chapter__title" data-follow-plane>视频下载与字幕整理</h2>
          <button type="button" className="landing-outro__cta" onClick={backToTop}>
            回到链接输入
          </button>
        </section>
      </div>
    </div>
  );
}
