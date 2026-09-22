import React from 'react';
import { MODELS } from '../../pixi/mascotConfig.js';

export default function About() {
  return (
    <footer className="about">
      {MODELS.map((m) => (
        <p key={m.id}>「{m.name}」—— 人物绘制：{m.credit.artist} · 建模：{m.credit.modeler}</p>
      ))}
      <p>模型遵循作者使用规则：非商用、不二传二改。</p>
    </footer>
  );
}
