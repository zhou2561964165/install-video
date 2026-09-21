import React, { useState } from 'react';

export default function EntryScene({ onSubmit }) {
  const [url, setUrl] = useState('');
  const submit = (e) => {
    e.preventDefault();
    if (url.trim()) onSubmit(url.trim());
  };
  return (
    <div data-testid="entry-scene">
      <h1>粘贴视频链接</h1>
      <form onSubmit={submit}>
        <input
          aria-label="视频链接"
          placeholder="https://…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button type="submit">解析</button>
      </form>
    </div>
  );
}
