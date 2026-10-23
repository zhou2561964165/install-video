import React from 'react';
import { LANDING_FEATURES, LANDING_HIGHLIGHTS } from '../../state/landingFeatures.js';

export default function LandingFeatures() {
  return (
    <section id="capabilities" className="landing-capabilities" aria-label="下载与内容整理功能一览">
      <dl className="landing-capabilities__highlights">
        {LANDING_HIGHLIGHTS.map(item => <div key={item.value}>
          <dt>{item.label}</dt><dd>{item.value}</dd>
        </div>)}
      </dl>
      <div className="landing-capabilities__card">
        <table className="landing-capabilities__table" aria-label="本站视频下载与内容整理功能一览">
          <thead><tr><th scope="col">功能一览</th><th scope="col">本站支持</th><th scope="col">使用体验</th></tr></thead>
          <tbody>{LANDING_FEATURES.map(row => <tr key={row.name} data-featured={row.featured || undefined}>
            <th scope="row">{row.name}</th>
            <td>{row.supported && <svg className="landing-capabilities__check" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 4 4L19 6" /></svg>}<span>{row.value}</span></td>
            <td>{row.detail}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}
