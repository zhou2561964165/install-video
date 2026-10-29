"""Lazy local faster-whisper adapter; no cloud fallback or implicit retries."""
import importlib.util
import math
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from .asr_errors import ASRError
from .outbound_httpx import ControlledHttpError
from .outbound_policy import OutboundError
from . import ytdlp_service

_admission_lock = threading.Lock()
_model_lock = threading.Lock()
_active = 0
_loaded = None
_loaded_profile = None


@dataclass(frozen=True)
class Transcription:
    title: str
    language: str
    text: str
    segments: list[dict]
    provider: str
    model: str


def profile() -> dict:
    return {name: str(value) if isinstance(value, Path) else value
            for name, value in vars(settings).items() if name.startswith('asr_')}


def capabilities() -> dict:
    available = importlib.util.find_spec('faster_whisper') is not None
    reason = None
    if not available:
        reason = '本地转写依赖未安装，请安装 asr 可选依赖。'
    elif settings.asr_model_path and not Path(settings.asr_model_path).is_dir():
        available = False
        reason = '本地转写模型尚未就绪，请检查模型配置。'
    return {'available': available, 'model': settings.asr_model,
            'max_duration_seconds': settings.asr_max_duration_seconds,
            'max_bytes': settings.asr_max_bytes, 'reason': reason}


def _get_model():
    global _loaded, _loaded_profile
    selected = (settings.asr_model_path or settings.asr_model,
                str(settings.asr_download_root), settings.asr_device, settings.asr_compute_type)
    with _model_lock:
        if _loaded is None or _loaded_profile != selected:
            from faster_whisper import WhisperModel
            _loaded = WhisperModel(selected[0], device=settings.asr_device,
                                   compute_type=settings.asr_compute_type,
                                   download_root=str(settings.asr_download_root),
                                   local_files_only=bool(settings.asr_model_path), cpu_threads=4)
            _loaded_profile = selected
        return _loaded


def _check_audio_duration(path: Path, started: float):
    # Decode incrementally before inference, including streams with false/missing duration.
    import av
    duration = 0.0
    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise ASRError('transcription_invalid_audio', '来源文件没有可解码音轨')
        for frame in container.decode(audio=0):
            if time.monotonic() - started > settings.asr_timeout_seconds:
                raise ASRError('transcription_timeout', '音频处理超过时间限制')
            duration += frame.samples / frame.sample_rate
            if duration > settings.asr_max_duration_seconds:
                raise ASRError('transcription_duration', '实际音频时长超过转写上限')
    if duration <= 0:
        raise ASRError('transcription_invalid_audio', '音频内容为空')


def transcribe_video(url: str, language: str | None = None) -> Transcription:
    global _active
    capability = capabilities()
    if not capability['available']:
        raise ASRError('transcription_unavailable', capability['reason'])
    with _admission_lock:
        if _active >= settings.asr_max_concurrent:
            raise ASRError('transcription_busy', '本地音频转写繁忙，请稍后重试')
        _active += 1
    started = time.monotonic()
    try:
        settings.temp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='asr-', dir=settings.temp_dir) as directory:
            audio, title = ytdlp_service.fetch_transcription_audio(url, Path(directory))
            _check_audio_duration(audio, started)
            model = _get_model()
            if time.monotonic() - started > settings.asr_timeout_seconds:
                raise ASRError('transcription_timeout', '模型加载超过本次转写时间限制，请稍后重试')
            segments, info = model.transcribe(str(audio), language=language, beam_size=1,
                                             vad_filter=settings.asr_vad_filter, condition_on_previous_text=False)
            output = []
            for segment in segments:
                if (time.monotonic() - started > settings.asr_timeout_seconds
                        or len(output) >= settings.subtitle_max_cues):
                    raise ASRError('transcription_capacity', '转写超过处理时间或字幕段数上限')
                start, end, text = segment.start, segment.end, segment.text.strip()
                if (type(start) not in {int, float} or type(end) not in {int, float}
                        or not math.isfinite(start) or not math.isfinite(end)
                        or not 0 <= start < end <= settings.asr_max_duration_seconds + 1
                        or (output and start < output[-1]['start'])):
                    raise ASRError('transcription_invalid', '转写返回了无效时间轴')
                if text:
                    output.append({'start': start, 'end': end, 'text': text})
            if not output:
                raise ASRError('transcription_empty', '未识别到可用语音')
            return Transcription(title, info.language, '\n'.join(s['text'] for s in output),
                                 output, 'faster-whisper', settings.asr_model)
    except (OutboundError, ControlledHttpError):
        raise
    except ASRError:
        raise
    except Exception:
        raise ASRError('transcription_failed', '本地音频转写失败，请检查模型和来源文件') from None
    finally:
        with _admission_lock:
            _active -= 1
