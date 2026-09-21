import React, { useEffect, useState } from 'react';

export default function Danmaku({ text, onDone }) {
  const [id] = useState(() => Math.random());
  useEffect(() => {
    const t = setTimeout(onDone, 3000);
    return () => clearTimeout(t);
  }, [onDone]);
  return <div className="danmaku" key={id} style={{ top: `${10 + (id * 17) % 60}%` }}>{text}</div>;
}
