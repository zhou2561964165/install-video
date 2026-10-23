import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { startDownload, getJob, getFile } from '../api.js';
import { SCENE } from '../state/sceneMachine.js';
import { POLL_MS } from '../state/downloadConfig.js';
import { saveFile } from '../lib/saveFile.js';

function createSubmissionKey() {
  if (globalThis.crypto.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function isUncertainSubmission(error) {
  return !error?.error_type || ['network', 'idempotency_in_progress', 'idempotency_uncertain'].includes(error.error_type);
}

// 下载编排独占请求、Blob URL 与保存副作用；完成页只读取状态和调用回调。
export function useDownload(state, dispatch, sessionKey = '') {
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const lifetime = useRef({ epoch: 0, mounted: false, blocked: false, requests: new Set(), file: null, saving: false, starting: false, automatic: new Set() });
  const identity = useRef(sessionKey);
  // Cancel/RESET only stop the client: a lost response may already have queued a job.
  // Once uncertain, keep the key through pre-receipt rejections until an authoritative receipt or a new payload/session.
  const submission = useRef(null);

  const cancel = useCallback(() => {
    const life = lifetime.current;
    if (life.starting && submission.current) submission.current.uncertain = true;
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
    return () => { lifetime.current.mounted = false; submission.current = null; cancel(); };
  }, [cancel]);

  useLayoutEffect(() => {
    if (identity.current !== sessionKey) {
      identity.current = sessionKey;
      submission.current = null;
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
    let attempt;
    try {
      const fingerprint = JSON.stringify([sessionKey, state.url, state.selectedFormat.format_id, state.forceServer]);
      if (!submission.current || submission.current.fingerprint !== fingerprint) {
        submission.current = { fingerprint, key: createSubmissionKey(), uncertain: false };
      }
      attempt = submission.current;
      const d = await startDownload(state.url, state.selectedFormat.format_id, state.forceServer, controller.signal, attempt.key);
      if (!current()) return;
      if (submission.current === attempt) submission.current = null;
      dispatch({ type: 'START_DOWNLOAD', download: d });
      if (d.mode === 'direct' && d.url) window.location.assign(d.url);
    } catch (error) {
      if (current()) {
        if (submission.current === attempt && attempt) {
          if (error?.idempotency_complete === true) submission.current = null;
          else if (isUncertainSubmission(error)) attempt.uncertain = true;
          // A later middleware/DB rejection cannot disprove an earlier accepted request.
          else if (!attempt.uncertain || ['idempotency_expired', 'idempotency_conflict'].includes(error.error_type)) submission.current = null;
        }
        dispatch({ type: 'DOWNLOAD_FAIL', error });
      }
    } finally {
      life.requests.delete(controller);
      if (life.epoch === epoch) life.starting = false;
    }
  }, [state.scene, state.url, state.selectedFormat, state.forceServer, sessionKey, dispatch]);

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
