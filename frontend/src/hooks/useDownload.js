import { useCallback, useEffect } from 'react';
import { startDownload, getJob, fileUrl } from '../api.js';
import { SCENE } from '../state/sceneMachine.js';
import { POLL_MS } from '../state/downloadConfig.js';
import { saveFile } from '../lib/saveFile.js';

// 下载编排 hook：把「发起下载 + 服务端轮询」从 App 下沉到此，App 只负责 dispatch 与场景渲染。
//   直链模式：发起后浏览器原生跳转下载；服务端模式：按 POLL_MS 轮询 job 直到 done/error，
//   done 时自动触发浏览器保存（saveFile），用户无需手动点链接。
// 返回 { startDownload }（供 SelectingScene 下载按钮调用）。
export function useDownload(state, dispatch) {
  const start = useCallback(async () => {
    const { url, selectedFormat, forceServer } = state;
    try {
      const d = await startDownload(url, selectedFormat.format_id, forceServer);
      dispatch({ type: 'START_DOWNLOAD', download: d });
      if (d.mode === 'direct' && d.url) {
        window.location.assign(d.url);
      }
    } catch (e) {
      dispatch({ type: 'DOWNLOAD_FAIL', error: e });
    }
  }, [state, dispatch]);

  useEffect(() => {
    if (state.scene !== SCENE.DOWNLOADING || !state.download || state.download.mode !== 'server') return;
    let timer;
    const tick = async () => {
      try {
        const job = await getJob(state.download.job_id);
        dispatch({ type: 'DOWNLOAD_PROGRESS', job });
        if (job.status === 'done') {
          saveFile(fileUrl(job.id)); // 服务端完成后自动触发浏览器保存
          return;
        }
        if (job.status === 'error') return;
        timer = setTimeout(tick, POLL_MS);
      } catch (e) {
        dispatch({ type: 'DOWNLOAD_FAIL', error: e });
      }
    };
    timer = setTimeout(tick, POLL_MS);
    return () => clearTimeout(timer);
  }, [state.scene, state.download]);

  return { startDownload: start };
}
