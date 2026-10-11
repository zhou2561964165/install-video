// 浏览器原生保存：临时 <a download> 点击后移除。
// 调用方负责 Blob URL 的创建与释放，并传入已解析的响应文件名。
export function saveFile(url, filename = '') {
  const a = document.createElement('a');
  try {
    a.href = url;
    a.download = filename || '';
    a.rel = 'noopener';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
  } finally {
    a.remove();
  }
}
