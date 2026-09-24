// 浏览器原生保存：临时 <a download> 点击后移除。
// 与 window.location.assign（跳转下载）不同，<a download> 不离开当前页；filename 为空时
// 浏览器回退到响应头 Content-Disposition（后端 /api/file 已带真实文件名 + 扩展名）。
export function saveFile(url, filename = '') {
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || '';
    a.rel = 'noopener';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch {
    // 无下载实现的环境（jsdom 等）静默忽略，不影响状态流转
  }
}
