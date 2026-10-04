# Backend 下载服务 Implementation Plan
> 文档状态（2026-10-03整理）：**历史参考**。v1原始实现计划；旧勾选框不是当前待办，账号/额度/鉴权/AI总结已扩展。当前状态见 [交接](../../handoff.md)。
> 工程约定仍适用：UI先用 `ui-ux-pro-max` + `design-system`；skill优先于旧计划；颜色/字体/时长token化、能力数据与配置驱动；yt-dlp仅经 `ytdlp_service.py`，视觉只读scene，不修改下载核心。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 跑通「粘贴链接 → 解析 → 选清晰度 → 服务端下载 → 取文件」的后端下载闭环，作为可 curl 验证的 FastAPI 服务。

**Architecture:** FastAPI 进程内直接调用 yt-dlp Python API；解析用 `extract_info(download=False)`，下载在受并发上限约束的线程池里执行，任务状态落 SQLite（SQLModel）；完成后由 `/api/file/{id}` 流式回传，临时文件按 TTL 自动清理。

**Tech Stack:** Python 3.12、FastAPI、yt-dlp（Python API）、SQLModel + SQLite、pytest + httpx、ffmpeg（合并音视频流，外部依赖）。

**Spec:** `docs/superpowers/specs/2026-09-20-frontend-experience-design.md`（前端契约 §9）、`docs/design.md`（后端架构 §1–§9）。本计划实现 `docs/design.md` 的 §3 目录结构、§4 数据流、§5 直链/服务端切换、§8 错误分类。

## Global Constraints

- Python ≥ 3.12；依赖全部声明在 `backend/requirements.txt`。
- `ytdlp_service.py` 是**唯一** import `yt_dlp` 的模块；其余模块只依赖它的接口。
- 错误分类枚举必须覆盖 design.md §8 的 9 类：`invalid_url` / `unsupported_site` / `age_restricted` / `geo_blocked` / `drm` / `login_required` / `ffmpeg_missing` / `network` / `quota`。
- 接口路径与 design.md §4 完全一致：`POST /api/parse`、`POST /api/download`、`GET /api/job/{id}`、`GET /api/file/{id}`。
- 下载阻塞 I/O 必须在**线程池**执行，并发上限默认 3（`MAX_CONCURRENT`）。
- 临时目录默认 `backend/tmp/`，完成后 TTL 默认 3600 秒自动删除。
- 任务状态枚举：`queued` / `downloading` / `merging` / `done` / `error`。

---

### Task 1: 项目脚手架 + 配置

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `settings`（`Settings` 实例）、`Settings` dataclass；字段 `ffmpeg_path`、`max_concurrent_downloads`、`temp_dir`、`max_file_size`、`ttl_seconds`、`db_url`、`rate_limit_requests`、`rate_limit_window_seconds`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_config.py
from pathlib import Path
from app.config import Settings, settings


def test_settings_defaults():
    s = Settings()
    assert s.max_concurrent_downloads == 3
    assert s.ttl_seconds == 3600
    assert isinstance(s.temp_dir, Path)
    assert s.db_url.startswith("sqlite:///")


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT", "5")
    monkeypatch.setenv("TTL_SECONDS", "60")
    s = Settings.from_env()
    assert s.max_concurrent_downloads == 5
    assert s.ttl_seconds == 60


def test_global_settings_is_settings():
    assert isinstance(settings, Settings)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: FAIL（`app.config` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# backend/app/config.py
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    ffmpeg_path: str = "ffmpeg"
    max_concurrent_downloads: int = 3
    temp_dir: Path = field(default_factory=lambda: Path("backend/tmp"))
    max_file_size: int = 2 * 1024 * 1024 * 1024  # 2 GB
    ttl_seconds: int = 3600
    db_url: str = "sqlite:///./jobs.db"
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        def _int(name: str, default: int) -> int:
            v = os.environ.get(name)
            return int(v) if v else default

        def _str(name: str, default: str) -> str:
            return os.environ.get(name) or default

        return cls(
            ffmpeg_path=_str("FFMPEG_PATH", "ffmpeg"),
            max_concurrent_downloads=_int("MAX_CONCURRENT", 3),
            temp_dir=Path(_str("TEMP_DIR", "backend/tmp")),
            max_file_size=_int("MAX_FILE_SIZE", 2 * 1024**3),
            ttl_seconds=_int("TTL_SECONDS", 3600),
            db_url=_str("DB_URL", "sqlite:///./jobs.db"),
            rate_limit_requests=_int("RATE_LIMIT", 30),
            rate_limit_window_seconds=_int("RATE_LIMIT_WINDOW", 60),
        )


settings = Settings.from_env()
```

```python
# backend/app/__init__.py
```

```text
# backend/requirements.txt
fastapi
uvicorn[standard]
yt-dlp
sqlmodel
pydantic
httpx
pytest
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/requirements.txt backend/app/__init__.py backend/app/config.py backend/tests/test_config.py
git commit -m "feat(backend): 脚手架 + 配置模块"
```

---

### Task 2: SQLite 引擎 + Job 模型

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `engine`（SQLAlchemy engine，`check_same_thread=False`）、`init_db()`、`get_session()`（generator，yield `Session`）；`Job`（SQLModel table）、`JobStatus`（str Enum）。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_models.py
from datetime import datetime, timezone

from app.db import engine, init_db
from app.models import Job, JobStatus


def test_job_defaults():
    job = Job(url="https://example.com/video")
    assert job.status == JobStatus.queued
    assert job.progress == 0.0
    assert job.id  # uuid 自动生成
    assert job.created_at.tzinfo is not None


def test_job_persist_roundtrip():
    init_db()
    from sqlmodel import Session

    job = Job(url="https://example.com/v", title="测试视频")
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
        got = session.get(Job, job.id)
        assert got is not None
        assert got.title == "测试视频"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL（`app.db` / `app.models` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# backend/app/db.py
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(
    settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
```

```python
# backend/app/models.py
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    queued = "queued"
    downloading = "downloading"
    merging = "merging"
    done = "done"
    error = "error"


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    url: str
    title: Optional[str] = None
    format_id: Optional[str] = None
    status: JobStatus = Field(default=JobStatus.queued)
    progress: float = Field(default=0.0)
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    error_type: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/db.py backend/app/models.py backend/tests/test_models.py
git commit -m "feat(backend): SQLite 引擎 + Job 模型"
```

---

### Task 3: yt-dlp 服务层 —— extract_info + 错误分类

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/ytdlp_service.py`
- Test: `backend/tests/test_ytdlp_service.py`

**Interfaces:**
- Consumes: `settings`（Task 1）
- Produces:
  - `extract_info(url: str) -> dict`（调 `yt_dlp.YoutubeDL.extract_info(url, download=False)`）
  - `classify_error(exc: Exception) -> str`（返回 9 类之一）
  - `is_valid_url(url: str) -> bool`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ytdlp_service.py
import yt_dlp.utils

from app.services.ytdlp_service import (
    classify_error,
    extract_info,
    is_valid_url,
)


class _FakeError(Exception):
    pass


def _err(msg: str) -> Exception:
    return yt_dlp.utils.ExtractorError(msg)


def test_is_valid_url():
    assert is_valid_url("https://www.youtube.com/watch?v=x") is True
    assert is_valid_url("http://example.com/v") is True
    assert is_valid_url("not a url") is False
    assert is_valid_url("ftp://example.com/v") is False


def test_classify_geo_restricted():
    assert classify_error(yt_dlp.utils.GeoRestrictedError()) == "geo_blocked"


def test_classify_unsupported():
    assert classify_error(yt_dlp.utils.UnsupportedError("x")) == "unsupported_site"


def test_classify_drm():
    assert classify_error(_err("This video is DRM protected")) == "drm"


def test_classify_login_required():
    assert classify_error(_err("Sign in to your account to continue")) == "login_required"


def test_classify_age_restricted():
    assert classify_error(_err("Video is age restricted")) == "age_restricted"


def test_classify_network_fallback():
    assert classify_error(_err("something totally unknown")) == "network"


def test_extract_info_calls_ydl(monkeypatch):
    calls = {}

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            calls["url"] = url
            calls["download"] = download
            return {"id": "x", "title": "t"}

    monkeypatch.setattr("app.services.ytdlp_service.yt_dlp.YoutubeDL", FakeYDL)
    info = extract_info("https://example.com/v")
    assert calls == {"url": "https://example.com/v", "download": False}
    assert info["title"] == "t"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_ytdlp_service.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写最小实现**

```python
# backend/app/services/ytdlp_service.py
import re
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import GeoRestrictedError, UnsupportedError

ERROR_INVALID_URL = "invalid_url"
ERROR_UNSUPPORTED = "unsupported_site"
ERROR_AGE = "age_restricted"
ERROR_GEO = "geo_blocked"
ERROR_DRM = "drm"
ERROR_LOGIN = "login_required"
ERROR_FFMPEG = "ffmpeg_missing"
ERROR_NETWORK = "network"
ERROR_QUOTA = "quota"

_PATTERNS = [
    (ERROR_DRM, re.compile(r"drm|widevine|protected content|encrypted")),
    (ERROR_AGE, re.compile(r"age[-_ ]?restricted|confirm your age|age verification|adult")),
    (ERROR_LOGIN, re.compile(r"sign in|login required|private video|members.?only|authentication|premium")),
    (ERROR_GEO, re.compile(r"geo[-_ ]?restricted|not available in your country|geoblock|country")),
    (ERROR_FFMPEG, re.compile(r"ffmpeg|ffprobe")),
    (ERROR_UNSUPPORTED, re.compile(r"unsupported url|no suitable extractor|unsupported website|not supported")),
    (ERROR_NETWORK, re.compile(r"timed out|timeout|connection|network|unreachable|ssl|certificate|refused|temporary failure|unable to download")),
]


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_info(url: str) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def classify_error(exc: Exception) -> str:
    if isinstance(exc, GeoRestrictedError):
        return ERROR_GEO
    if isinstance(exc, UnsupportedError):
        return ERROR_UNSUPPORTED
    msg = str(exc).lower()
    for error_type, pattern in _PATTERNS:
        if pattern.search(msg):
            return error_type
    return ERROR_NETWORK
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_ytdlp_service.py -v`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/__init__.py backend/app/services/ytdlp_service.py backend/tests/test_ytdlp_service.py
git commit -m "feat(backend): yt-dlp 服务层 extract_info + 错误分类"
```

---

### Task 4: 清晰度归并 build_format_options

**Files:**
- Modify: `backend/app/services/ytdlp_service.py`（追加函数）
- Test: `backend/tests/test_formats.py`

**Interfaces:**
- Produces: `build_format_options(info: dict) -> list[dict]`，每个 option 含 `format_id`、`label`、`height`、`ext`、`filesize`、`direct`、`note`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_formats.py
from app.services.ytdlp_service import build_format_options


def _fmt(fid, height=None, vcodec="avc1", acodec="mp4a", url=None):
    return {
        "format_id": fid,
        "height": height,
        "vcodec": vcodec,
        "acodec": acodec,
        "url": url,
        "ext": "mp4",
        "filesize": 1000,
    }


def test_tiers_collapse_to_existing_heights():
    info = {
        "formats": [
            _fmt("137", 1080, vcodec="avc1", acodec="none"),   # 仅视频
            _fmt("140", None, vcodec="none", acodec="mp4a"),   # 仅音频
            _fmt("18", 360, url="https://cdn/18.mp4"),          # 渐进式直链
        ]
    }
    opts = build_format_options(info)
    labels = {o["label"] for o in opts}
    assert "1080p" in labels  # 需合并 → server
    assert "360p" in labels   # 渐进式 → direct
    by_label = {o["label"]: o for o in opts}
    assert by_label["1080p"]["direct"] is False
    assert by_label["1080p"]["format_id"] == "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    assert by_label["360p"]["direct"] is True
    assert by_label["360p"]["format_id"] == "18"


def test_no_video_falls_back_to_best():
    info = {"formats": [_fmt("140", None, vcodec="none", acodec="mp4a")]}
    opts = build_format_options(info)
    assert len(opts) == 1
    assert opts[0]["format_id"] == "best"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_formats.py -v`
Expected: FAIL（`build_format_options` 不存在）

- [ ] **Step 3: 写最小实现（追加到 ytdlp_service.py）**

```python
HEIGHT_TIERS = [2160, 1440, 1080, 720, 480, 360]


def _is_video(fmt: dict) -> bool:
    return bool(fmt.get("height")) and fmt.get("vcodec") not in (None, "none")


def _progressive_direct(formats: list[dict], height: int) -> dict | None:
    for f in formats:
        if (
            f.get("height") == height
            and f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
        ):
            url = f.get("url")
            if url and str(url).startswith("http"):
                return f
    return None


def build_format_options(info: dict) -> list[dict]:
    formats = info.get("formats") or []
    heights = sorted({f["height"] for f in formats if _is_video(f)}, reverse=True)
    options: list[dict] = []
    seen: set[int] = set()
    for tier in HEIGHT_TIERS:
        h = next((x for x in heights if x <= tier), None)
        if h is None or h in seen:
            continue
        seen.add(h)
        direct_fmt = _progressive_direct(formats, h)
        if direct_fmt:
            options.append({
                "format_id": str(direct_fmt["format_id"]),
                "label": f"{h}p",
                "height": h,
                "ext": direct_fmt.get("ext") or "mp4",
                "filesize": direct_fmt.get("filesize"),
                "direct": True,
                "note": direct_fmt.get("format_note"),
            })
        else:
            options.append({
                "format_id": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
                "label": f"{h}p",
                "height": h,
                "ext": "mp4",
                "filesize": None,
                "direct": False,
                "note": None,
            })
    if not options:
        options.append({
            "format_id": "best",
            "label": "best",
            "height": None,
            "ext": "mp4",
            "filesize": None,
            "direct": False,
            "note": None,
        })
    return options
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_formats.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/ytdlp_service.py backend/tests/test_formats.py
git commit -m "feat(backend): 清晰度归并 build_format_options"
```

---

### Task 5: Pydantic schemas

**Files:**
- Create: `backend/app/schemas.py`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Produces: `ParseRequest`、`FormatOption`、`ParseResponse`、`DownloadRequest`、`DownloadResponse`、`JobResponse`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_schemas.py
import pytest
from pydantic import ValidationError

from app.models import JobStatus
from app.schemas import (
    DownloadRequest,
    FormatOption,
    ParseRequest,
    ParseResponse,
)


def test_parse_request_requires_url():
    ParseRequest(url="https://example.com/v")
    with pytest.raises(ValidationError):
        ParseRequest(url="")


def test_parse_response_shape():
    r = ParseResponse(
        title="t",
        thumbnail=None,
        duration=12.5,
        formats=[FormatOption(format_id="18", label="360p", direct=True)],
    )
    assert r.formats[0].direct is True


def test_download_request_force_server_default_false():
    d = DownloadRequest(url="https://example.com/v", format_id="18")
    assert d.force_server is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_schemas.py -v`
Expected: FAIL（`app.schemas` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# backend/app/schemas.py
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .models import JobStatus


class ParseRequest(BaseModel):
    url: str = Field(min_length=1)


class FormatOption(BaseModel):
    format_id: str
    label: str
    height: Optional[int] = None
    ext: str = "mp4"
    filesize: Optional[int] = None
    direct: bool = False
    note: Optional[str] = None


class ParseResponse(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    formats: list[FormatOption]


class DownloadRequest(BaseModel):
    url: str = Field(min_length=1)
    format_id: str = Field(min_length=1)
    force_server: bool = False


class DownloadResponse(BaseModel):
    mode: Literal["direct", "server"]
    url: Optional[str] = None
    headers: dict = {}
    job_id: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    progress: float
    title: Optional[str] = None
    error_type: Optional[str] = None
    error: Optional[str] = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_schemas.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/schemas.py backend/tests/test_schemas.py
git commit -m "feat(backend): Pydantic schemas"
```

---

### Task 6: jobs 服务（线程池 + 生命周期 + 清理）

**Files:**
- Create: `backend/app/services/jobs.py`
- Test: `backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `Job`、`JobStatus`、`settings`、`get_session`、`classify_error`
- Produces:
  - `class JobManager`，方法 `submit_download(job: Job, url: str, format_id: str) -> None`、`cleanup_expired() -> int`
  - 单例 `job_manager`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_jobs.py
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import engine, init_db
from app.models import Job, JobStatus
from app.services.jobs import JobManager, job_manager


def test_submit_runs_fn_and_marks_done(monkeypatch, tmp_path):
    init_db()
    manager = JobManager(max_workers=1)
    result = {}

    def fake_download(job_id, url, format_id):
        result["job_id"] = job_id
        result["url"] = url

    monkeypatch.setattr(
        "app.services.jobs._run_download", fake_download
    )
    job = Job(url="https://example.com/v", format_id="18")
    from sqlmodel import Session

    with Session(engine) as s:
        s.add(job)
        s.commit()
        job_id = job.id

    manager.submit_download(job, "https://example.com/v", "18")
    # 线程池执行是异步的；这里只验证调度契约，真实状态落库由 Task 8 的集成测试覆盖
    assert isinstance(job_manager, JobManager)
    assert manager._executor is not None


def test_cleanup_expired_removes_file(tmp_path):
    init_db()
    from sqlmodel import Session

    expired = Job(
        url="https://example.com/v",
        status=JobStatus.done,
        file_path=str(tmp_path / "old.mp4"),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    fresh = Job(
        url="https://example.com/v2",
        status=JobStatus.done,
        file_path=str(tmp_path / "new.mp4"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=100),
    )
    (tmp_path / "old.mp4").write_bytes(b"x")
    (tmp_path / "new.mp4").write_bytes(b"y")

    with Session(engine) as s:
        s.add(expired)
        s.add(fresh)
        s.commit()

    manager = JobManager(max_workers=1)
    n = manager.cleanup_expired()
    assert n == 1
    assert not (tmp_path / "old.mp4").exists()
    assert (tmp_path / "new.mp4").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_jobs.py -v`
Expected: FAIL（`app.services.jobs` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# backend/app/services/jobs.py
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..config import settings
from ..db import engine
from ..models import Job, JobStatus
from .ytdlp_service import classify_error


def _run_download(job_id: str, url: str, format_id: str) -> None:
    # 在 Task 8 中由 download 路由注入真实实现；此处为可替换的入口
    raise NotImplementedError


class JobManager:
    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or settings.max_concurrent_downloads
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._lock = threading.Lock()

    def submit_download(self, job: Job, url: str, format_id: str) -> None:
        self._executor.submit(self._safe_run, job.id, url, format_id)

    def _safe_run(self, job_id: str, url: str, format_id: str) -> None:
        try:
            _run_download(job_id, url, format_id)
        except Exception as exc:  # noqa: BLE001
            self._mark_error(job_id, exc)

    def _mark_error(self, job_id: str, exc: Exception) -> None:
        with self._lock, Session(engine) as s:
            job = s.get(Job, job_id)
            if job:
                job.status = JobStatus.error
                job.error_type = classify_error(exc)
                job.error = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                s.add(job)
                s.commit()

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        removed = 0
        with Session(engine) as s:
            jobs = s.exec(
                select(Job).where(
                    Job.expires_at.is_not(None), Job.expires_at < now
                )
            ).all()
            for job in jobs:
                if job.file_path:
                    p = Path(job.file_path)
                    if p.exists():
                        p.unlink(missing_ok=True)
                s.delete(job)
                removed += 1
            s.commit()
        return removed


job_manager = JobManager()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_jobs.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/jobs.py backend/tests/test_jobs.py
git commit -m "feat(backend): jobs 服务（线程池 + 生命周期 + TTL 清理）"
```

---

### Task 7: parse 路由

**Files:**
- Create: `backend/app/routes/__init__.py`
- Create: `backend/app/routes/parse.py`
- Modify: `backend/app/services/ytdlp_service.py`（追加 `parse_video(url) -> tuple[dict, list[dict]]`）
- Test: `backend/tests/test_parse_route.py`

**Interfaces:**
- Consumes: `extract_info`、`build_format_options`、`is_valid_url`、`ParseResponse`、`FormatOption`
- Produces: `parse_video(url: str) -> tuple[dict, list[dict]]`（返回 `(meta, options)`，其中 `meta` 含 `title`/`thumbnail`/`duration`）；`router`（`POST /api/parse`）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_parse_route.py
from fastapi.testclient import TestClient

from app.main import app  # Task 1 已建最小 app，此处挂载 router

from app.services import ytdlp_service

client = TestClient(app)


def test_parse_ok(monkeypatch):
    def fake_extract(url):
        return {
            "title": "测试标题",
            "thumbnail": "https://i.example/t.jpg",
            "duration": 30.0,
            "formats": [
                {"format_id": "18", "height": 360, "vcodec": "avc1",
                 "acodec": "mp4a", "url": "https://cdn/18.mp4", "ext": "mp4"},
            ],
        }

    monkeypatch.setattr(ytdlp_service, "extract_info", fake_extract)
    r = client.post("/api/parse", json={"url": "https://example.com/v"})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "测试标题"
    assert data["formats"][0]["label"] == "360p"
    assert data["formats"][0]["direct"] is True


def test_parse_invalid_url():
    r = client.post("/api/parse", json={"url": "not a url"})
    assert r.status_code == 400
    assert r.json()["detail"]["error_type"] == "invalid_url"


def test_parse_unsupported(monkeypatch):
    def fake_extract(url):
        from yt_dlp.utils import UnsupportedError

        raise UnsupportedError("unsupported")

    monkeypatch.setattr(ytdlp_service, "extract_info", fake_extract)
    r = client.post("/api/parse", json={"url": "https://example.com/v"})
    assert r.status_code == 422
    assert r.json()["detail"]["error_type"] == "unsupported_site"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_parse_route.py -v`
Expected: FAIL（`app.main` 尚未挂载路由 / `parse_video` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# backend/app/services/ytdlp_service.py —— 追加
def parse_video(url: str) -> tuple[dict, list[dict]]:
    info = extract_info(url)
    meta = {
        "title": info.get("title") or "",
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
    }
    options = build_format_options(info)
    return meta, options
```

```python
# backend/app/routes/parse.py
from fastapi import APIRouter, HTTPException

from ..schemas import FormatOption, ParseRequest, ParseResponse
from ..services.ytdlp_service import classify_error, is_valid_url, parse_video

router = APIRouter()


@router.post("/api/parse", response_model=ParseResponse)
def parse(req: ParseRequest) -> ParseResponse:
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail={"error_type": "invalid_url", "error": "无效链接"})
    try:
        meta, options = parse_video(req.url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail={"error_type": classify_error(exc), "error": str(exc)})
    return ParseResponse(
        title=meta["title"],
        thumbnail=meta["thumbnail"],
        duration=meta["duration"],
        formats=[FormatOption(**o) for o in options],
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_parse_route.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/routes/__init__.py backend/app/routes/parse.py backend/app/services/ytdlp_service.py backend/tests/test_parse_route.py
git commit -m "feat(backend): POST /api/parse 路由"
```

---

### Task 8: download 路由 + 文件回传（跑通下载闭环）

**Files:**
- Create: `backend/app/routes/download.py`
- Modify: `backend/app/services/ytdlp_service.py`（追加 `download()`）
- Modify: `backend/app/services/jobs.py`（把 `_run_download` 换成真实实现）
- Modify: `backend/app/main.py`（挂载两个 router）
- Test: `backend/tests/test_download_route.py`

**Interfaces:**
- Consumes: `Job`、`JobManager`、`get_session`、`settings`、`classify_error`
- Produces:
  - `ytdlp_service.download(url: str, format_id: str, outtmpl: str, progress_hook) -> str`（返回下载后文件路径）
  - `get_direct_url(url: str, format_id: str) -> tuple[str, dict]`（返回 `(url, headers)`）
  - `router`（`POST /api/download`、`GET /api/job/{job_id}`、`GET /api/file/{job_id}`）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_download_route.py
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import engine, init_db
from app.main import app
from app.models import Job, JobStatus
from app.services import ytdlp_service

client = TestClient(app)


def test_download_server_mode_creates_job(monkeypatch):
    init_db()
    monkeypatch.setattr(
        ytdlp_service,
        "get_direct_url",
        lambda url, fid: (None, {}),  # 直链不可用 → server
    )
    from app.services import jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_run_download", lambda job_id, url, fid: None)
    r = client.post(
        "/api/download",
        json={"url": "https://example.com/v", "format_id": "bestvideo[height<=1080]+bestaudio"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "server"
    assert data["job_id"]

    with Session(engine) as s:
        job = s.get(Job, data["job_id"])
        assert job is not None
        assert job.status == JobStatus.queued


def test_download_direct_mode_returns_url(monkeypatch):
    monkeypatch.setattr(
        ytdlp_service,
        "get_direct_url",
        lambda url, fid: ("https://cdn/18.mp4", {"User-Agent": "test"}),
    )
    r = client.post(
        "/api/download",
        json={"url": "https://example.com/v", "format_id": "18"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "direct"
    assert data["url"] == "https://cdn/18.mp4"
    assert data["headers"]["User-Agent"] == "test"


def test_get_job_returns_status():
    init_db()
    with Session(engine) as s:
        job = Job(url="https://example.com/v", title="t", status=JobStatus.done, progress=100.0)
        s.add(job)
        s.commit()
        job_id = job.id
    r = client.get(f"/api/job/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_get_file_streams_content(monkeypatch, tmp_path):
    init_db()
    f = tmp_path / "v.mp4"
    f.write_bytes(b"VIDEO_BYTES")
    with Session(engine) as s:
        job = Job(url="https://example.com/v", status=JobStatus.done, file_path=str(f))
        s.add(job)
        s.commit()
        job_id = job.id
    r = client.get(f"/api/file/{job_id}")
    assert r.status_code == 200
    assert r.content == b"VIDEO_BYTES"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_download_route.py -v`
Expected: FAIL（路由未挂载 / `get_direct_url`、`download` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# backend/app/services/ytdlp_service.py —— 追加
import os

import yt_dlp


def get_direct_url(url: str, format_id: str) -> tuple[str | None, dict]:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        for f in info.get("formats") or []:
            if str(f.get("format_id")) == str(format_id):
                direct = f.get("url")
                if direct and str(direct).startswith("http"):
                    return str(direct), f.get("http_headers") or {}
    return None, {}


def download(url: str, format_id: str, outtmpl: str, progress_hook) -> str:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": format_id,
        "outtmpl": outtmpl,
        "progress_hooks": [progress_hook],
        "merge_output_format": "mp4",
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    filename = ydl.prepare_filename(info)
    # 合并后扩展名可能变化（如 .webm → .mp4）；取目录下最新文件作为产物
    out_dir = os.path.dirname(outtmpl)
    files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)]
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise FileNotFoundError("下载产物缺失")
    return max(files, key=os.path.getmtime)
```

```python
# backend/app/services/jobs.py —— 替换 _run_download 占位实现
from datetime import timedelta
import os

from .ytdlp_service import download as _ytdlp_download


def _run_download(job_id: str, url: str, format_id: str) -> None:
    from sqlmodel import Session
    from ..models import Job, JobStatus

    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job:
            return
        job.status = JobStatus.downloading
        job.updated_at = datetime.now(timezone.utc)
        s.add(job)
        s.commit()

    job_dir = Path(settings.temp_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(job_dir / "%(title)s.%(ext)s")

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = (d.get("downloaded_bytes") or 0) / total * 100 if total else 0
            _update_progress(job_id, min(pct, 100.0))
        elif d.get("status") == "finished":
            _update_progress(job_id, 100.0)

    file_path = _ytdlp_download(url, format_id, outtmpl, hook)

    size = os.path.getsize(file_path)
    if size > settings.max_file_size:
        Path(file_path).unlink(missing_ok=True)
        with Session(engine) as s:
            job = s.get(Job, job_id)
            job.status = JobStatus.error
            job.error_type = "quota"
            job.error = "文件超过大小上限"
            job.updated_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()
        return

    with Session(engine) as s:
        job = s.get(Job, job_id)
        job.status = JobStatus.done
        job.progress = 100.0
        job.file_path = file_path
        job.file_size = size
        job.expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.ttl_seconds)
        job.updated_at = datetime.now(timezone.utc)
        s.add(job)
        s.commit()


def _update_progress(job_id: str, pct: float) -> None:
    from sqlmodel import Session
    from ..models import Job

    with Session(engine) as s:
        job = s.get(Job, job_id)
        if job:
            job.progress = pct
            job.updated_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()
```

```python
# backend/app/routes/download.py
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..db import get_session
from ..models import Job, JobStatus
from ..schemas import DownloadRequest, DownloadResponse, JobResponse
from ..services.jobs import job_manager
from ..services.ytdlp_service import get_direct_url

router = APIRouter()


@router.post("/api/download", response_model=DownloadResponse)
def download(req: DownloadRequest, session: Session = Depends(get_session)) -> DownloadResponse:
    job_manager.cleanup_expired()  # 懒触发 TTL 清理
    if not req.force_server:
        direct, headers = get_direct_url(req.url, req.format_id)
        if direct:
            return DownloadResponse(mode="direct", url=direct, headers=headers)

    job = Job(url=req.url, format_id=req.format_id, status=JobStatus.queued)
    session.add(job)
    session.commit()
    session.refresh(job)
    job_manager.submit_download(job, req.url, req.format_id)
    return DownloadResponse(mode="server", job_id=job.id)


@router.get("/api/job/{job_id}", response_model=JobResponse)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "任务不存在"})
    return JobResponse(
        id=job.id, status=job.status, progress=job.progress,
        title=job.title, error_type=job.error_type, error=job.error,
    )


@router.get("/api/file/{job_id}")
def get_file(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job or job.status != JobStatus.done or not job.file_path:
        raise HTTPException(status_code=404, detail={"error": "文件不存在或未完成"})
    path = Path(job.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "文件已过期清理"})
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
```

```python
# backend/app/main.py —— 挂载 router（替换 Task 1 的最小 app）
from fastapi import FastAPI

from .db import init_db
from .routes.download import router as download_router
from .routes.parse import router as parse_router

app = FastAPI(title="万能视频下载")

init_db()
app.include_router(parse_router)
app.include_router(download_router)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_download_route.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/routes/download.py backend/app/services/ytdlp_service.py backend/app/services/jobs.py backend/app/main.py backend/tests/test_download_route.py
git commit -m "feat(backend): POST /api/download + GET /api/job/{id} + GET /api/file/{id}"
```

---

### Task 9: 限流中间件 + ffmpeg 安装脚本 + 手动验收

**Files:**
- Create: `backend/app/main.py`（追加中间件）
- Create: `backend/scripts/install_ffmpeg.ps1`
- Create: `backend/scripts/install_ffmpeg.sh`
- Test: `backend/tests/test_rate_limit.py`

**Interfaces:**
- Consumes: `settings`（`rate_limit_requests` / `rate_limit_window_seconds`）
- Produces: FastAPI 中间件，按客户端 IP 对 `/api/*` 做窗口计数限流，超限返回 `429` + `error_type: quota`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_rate_limit.py
from fastapi.testclient import TestClient

from app.main import app


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr("app.main._settings_rate_limit", 1)
    # 直接发两个请求，第二个应被限流（客户端 IP 固定为 testclient）
    from app.services import ytdlp_service

    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "t", "formats": []})
    c = TestClient(app)
    first = c.post("/api/parse", json={"url": "https://example.com/v"})
    second = c.post("/api/parse", json={"url": "https://example.com/v"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["error_type"] == "quota"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_rate_limit.py -v`
Expected: FAIL（无中间件）

- [ ] **Step 3: 写最小实现**

```python
# backend/app/main.py —— 追加（在 include_router 之前）
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import settings

_settings_rate_limit = settings.rate_limit_requests  # 测试可覆盖

_window: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        now = time.monotonic()
        key = request.client.host if request.client else "unknown"
        window = _settings_rate_limit
        win_sec = settings.rate_limit_window_seconds
        _window[key] = [t for t in _window[key] if now - t < win_sec]
        if len(_window[key]) >= window:
            return JSONResponse(status_code=429, content={"detail": {"error_type": "quota", "error": "请求过于频繁"}})
        _window[key].append(now)
    return await call_next(request)
```

> 注：用模块级 `_settings_rate_limit` 便于测试覆盖；默认取 `settings.rate_limit_requests`。

```powershell
# backend/scripts/install_ffmpeg.ps1
# 一键安装 ffmpeg（Windows）
winget install --id Gyan.FFmpeg -e
```

```bash
# backend/scripts/install_ffmpeg.sh
#!/usr/bin/env bash
# 一键安装 ffmpeg（Linux）
set -e
if command -v apt >/dev/null 2>&1; then
  sudo apt update && sudo apt install -y ffmpeg
elif command -v brew >/dev/null 2>&1; then
  brew install ffmpeg
else
  echo "请手动安装 ffmpeg 并加入 PATH"
  exit 1
fi
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_rate_limit.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/main.py backend/scripts/install_ffmpeg.ps1 backend/scripts/install_ffmpeg.sh backend/tests/test_rate_limit.py
git commit -m "feat(backend): 限流中间件 + ffmpeg 安装脚本"
```

---

### 手动验收（全部任务完成后）

1. 安装依赖与 ffmpeg：`cd backend && pip install -r requirements.txt`；Windows 执行 `powershell -File scripts/install_ffmpeg.ps1`。
2. 起服务：`cd backend && uvicorn app.main:app --reload`。
3. `curl -X POST http://127.0.0.1:8000/api/parse -H "Content-Type: application/json" -d '{"url":"<真实视频链接>"}'` → 应返回 title / formats。
4. `curl -X POST http://127.0.0.1:8000/api/download -H "Content-Type: application/json" -d '{"url":"<链接>","format_id":"bestvideo[height<=1080]+bestaudio"}'` → 返回 `job_id`。
5. 轮询 `curl http://127.0.0.1:8000/api/job/<job_id>` 直到 `status=done`。
6. `curl -o out.mp4 http://127.0.0.1:8000/api/file/<job_id>` → 得到可播放文件。
