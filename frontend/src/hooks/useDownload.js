import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { startDownload, getJob, getFile } from '../api.js';
import { SCENE } from '../state/sceneMachine.js';
import { POLL_MS } from '../state/downloadConfig.js';
import { saveFile } from '../lib/saveFile.js';

// 下载编排独占请求、Blob URL 与保存副作用；完成页只读取状态和调用回调。
export function useDownload(state, dispatch, sessionKey = '') {
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const lifetime = useRef({ epoch: 0, mounted: false, blocked: false, requests: new Set(), file: null, saving: false, starting: false, automatic: new Set() });
  const identity = useRef(sessionKey);

  const cancel = useCallback(() => {
    const life = lifetime.current;
    life.epoch += 1;
    life.blocked = true;
    for (const controller of life.requests) controller.abort();
    life.requests.clear();
    if (life.file) URL.revokeObjectURL(life.file.url);
    life.file = null;
    life.saving = false;
    life.starting = false;
    life.automatic.clear();
    if (life.mounted) { setSaveBusy(false); setSaveError(null); }
  }, []);

  useLayoutEffect(() => {
    lifetime.current.mounted = true;
    lifetime.current.blocked = false;
    return () => { lifetime.current.mounted = false; cancel(); };
  }, [cancel]);

  useLayoutEffect(() => {
    if (identity.current !== sessionKey) {
      identity.current = sessionKey;
      cancel();
      dispatch({ type: 'RESET' });
    }
  }, [sessionKey, cancel, dispatch]);

  useLayoutEffect(() => {
    if (state.scene === SCENE.ENTRY || state.scene === SCENE.PARSING) {
      cancel();
      lifetime.current.blocked = false;
    }
  }, [state.scene, state.url, cancel]);

  const start = useCallback(async () => {
    const life = lifetime.current;
    if (!life.mounted || life.starting || state.scene !== SCENE.SELECTING || !state.selectedFormat) return;
    life.blocked = false;
    life.starting = true;
    const epoch = life.epoch;
    const controller = new AbortController();
    life.requests.add(controller);
    const current = () => life.mounted && !life.blocked && life.epoch === epoch && !controller.signal.aborted;
    try {
      const d = await startDownload(state.url, state.selectedFormat.format_id, state.forceServer, controller.signal);
      if (!current()) return;
      dispatch({ type: 'START_DOWNLOAD', download: d });
      if (d.mode === 'direct' && d.url) window.location.assign(d.url);
    } catch (error) {
      if (current()) dispatch({ type: 'DOWNLOAD_FAIL', error });
    } finally {
      life.requests.delete(controller);
      if (life.epoch === epoch) life.starting = false;
    }
  }, [state.scene, state.url, state.selectedFormat, state.forceServer, dispatch]);

  const save = useCallback(async () => {
    const life = lifetime.current;
    const jobId = state.job?.id;
    if (!life.mounted || life.blocked || life.saving || state.scene !== SCENE.DONE || !jobId) return;
    life.saving = true;
    setSaveBusy(true);
    setSaveError(null);
    const epoch = life.epoch;
    const controller = new AbortController();
    life.requests.add(controller);
    const current = () => life.mounted && !life.blocked && life.epoch === epoch && !controller.signal.aborted;
    try {
      if (!life.file || life.file.jobId !== jobId) {
        const { blob, filename } = await getFile(jobId, controller.signal);
        if (!current()) return;
        if (life.file) URL.revokeObjectURL(life.file.url);
        life.file = { jobId, url: URL.createObjectURL(blob), filename };
      }
      if (current()) saveFile(life.file.url, life.file.filename);
    } catch (error) {
      if (current()) setSaveError({ error_type: error?.error_type || 'network', error: error?.error || error?.message || '保存文件失败，请重试' });
    } finally {
      life.requests.delete(controller);
      if (current()) { life.saving = false; setSaveBusy(false); }
    }
  }, [state.scene, state.job?.id]);

  useEffect(() => {
    const life = lifetime.current;
    const jobId = state.job?.id;
    if (life.blocked || state.scene !== SCENE.DONE || !jobId || life.automatic.has(jobId)) return;
    life.automatic.add(jobId);
    void save();
  }, [state.scene, state.job?.id, sessionKey, save]);

  useEffect(() => {
    const life = lifetime.current;
    if (life.blocked || state.scene !== SCENE.DOWNLOADING || state.download?.mode !== 'server') return;
    const epoch = life.epoch;
    const controller = new AbortController();
    life.requests.add(controller);
    let timer;
    let active = true;
    const current = () => active && life.mounted && !life.blocked && life.epoch === epoch && !controller.signal.aborted;
    const tick = async () => {
      if (!current()) return;
      try {
        const job = await getJob(state.download.job_id, controller.signal);
        if (!current()) return;
        dispatch({ type: 'DOWNLOAD_PROGRESS', job });
        if (job.status === 'done' || job.status === 'error') return;
        timer = setTimeout(tick, POLL_MS);
      } catch (error) {
        if (current()) dispatch({ type: 'DOWNLOAD_FAIL', error });
      }
    };
    timer = setTimeout(tick, POLL_MS);
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
      life.requests.delete(controller);
    };
  }, [state.scene, state.download, sessionKey, dispatch]);

  return { startDownload: start, save, saveBusy, saveError, cancel };
}
