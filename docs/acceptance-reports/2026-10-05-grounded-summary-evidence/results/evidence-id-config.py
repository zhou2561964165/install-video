import math
import os
from dataclasses import dataclass, field
from pathlib import Path

# 后端根目录（backend/）。默认路径锚定到这里，保证无论从哪个工作目录启动
# uvicorn，temp_dir / db_url 都落在仓库内、且被 .gitignore 覆盖（backend/tmp/、*.db）。
_BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    ffmpeg_path: str = "ffmpeg"
    max_concurrent_downloads: int = 3
    temp_dir: Path = field(default_factory=lambda: _BACKEND_DIR / "tmp")
    max_file_size: int = 2 * 1024 * 1024 * 1024  # 2 GB
    ttl_seconds: int = 3600
    db_url: str = field(default_factory=lambda: f"sqlite:///{(_BACKEND_DIR / 'jobs.db').as_posix()}")
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    network_retries: int = 2
    network_retry_backoff_seconds: float = 0.5
    # v2 账号 + 额度（生产环境务必用环境变量覆盖 JWT_SECRET）
    jwt_secret: str = "dev-secret-change-me-in-production"
    jwt_expire_minutes: int = 10080  # 7 天
    default_quota_limit: int = 10  # 每用户每日下载次数
    password_iterations: int = 100_000  # pbkdf2_hmac 迭代次数
    # v3 字幕 + LLM（OpenAI-compatible；留空表示未配置，仅字幕读取可用）
    subtitle_max_bytes: int = 5 * 1024 * 1024
    subtitle_timeout_seconds: int = 30
    llm_provider: str = "openai-compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 90
    llm_max_input_chars: int = 60_000
    llm_summary_chunk_chars: int = 20_000
    llm_summary_max_chunks: int = 16
    llm_summary_max_output_tokens: int = 4096
    llm_summary_response_format: str = "auto"
    llm_summary_thinking_mode: str = "auto"
    llm_summary_max_point_chars: int = 240
    llm_summary_source_context_chars: int = 1200
    llm_summary_strategy: str = "legacy"
    llm_summary_facts_max_source_chars: int = 40_000
    llm_summary_facts_max_per_chunk: int = 12
    llm_summary_facts_max_evidence_sentences: int = 32

    def __post_init__(self) -> None:
        if self.network_retries < 0:
            raise ValueError("network_retries must be >= 0")
        if (
            not math.isfinite(self.network_retry_backoff_seconds)
            or self.network_retry_backoff_seconds < 0
        ):
            raise ValueError("network_retry_backoff_seconds must be finite and >= 0")
        if self.llm_summary_response_format not in {"auto", "text", "json_object", "json_schema", "strict_tool"}:
            raise ValueError("llm_summary_response_format must be auto, text, json_object, json_schema or strict_tool")
        if self.llm_summary_thinking_mode not in {"auto", "enabled", "disabled"}:
            raise ValueError("llm_summary_thinking_mode must be auto, enabled or disabled")
        if self.llm_summary_max_point_chars < 1:
            raise ValueError("llm_summary_max_point_chars must be >= 1")
        if self.llm_summary_source_context_chars < 0:
            raise ValueError("llm_summary_source_context_chars must be >= 0")
        if self.llm_summary_strategy not in {"auto", "legacy", "facts"}:
            raise ValueError("llm_summary_strategy must be auto, legacy or facts")
        for name, maximum in (("llm_summary_facts_max_source_chars", 1_000_000),
                              ("llm_summary_facts_max_per_chunk", 48),
                              ("llm_summary_facts_max_evidence_sentences", 64)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be an integer between 1 and {maximum}")

    @classmethod
    def from_env(cls) -> "Settings":
        def _int(name: str, default: int) -> int:
            v = os.environ.get(name)
            return int(v) if v else default

        def _float(name: str, default: float) -> float:
            v = os.environ.get(name)
            return float(v) if v else default

        def _str(name: str, default: str) -> str:
            return os.environ.get(name) or default

        return cls(
            ffmpeg_path=_str("FFMPEG_PATH", "ffmpeg"),
            max_concurrent_downloads=_int("MAX_CONCURRENT", 3),
            temp_dir=Path(_str("TEMP_DIR", str(_BACKEND_DIR / "tmp"))),
            max_file_size=_int("MAX_FILE_SIZE", 2 * 1024**3),
            ttl_seconds=_int("TTL_SECONDS", 3600),
            db_url=_str("DB_URL", f"sqlite:///{(_BACKEND_DIR / 'jobs.db').as_posix()}"),
            rate_limit_requests=_int("RATE_LIMIT", 30),
            rate_limit_window_seconds=_int("RATE_LIMIT_WINDOW", 60),
            network_retries=_int("NETWORK_RETRIES", 2),
            network_retry_backoff_seconds=_float("NETWORK_RETRY_BACKOFF_SECONDS", 0.5),
            jwt_secret=_str("JWT_SECRET", "dev-secret-change-me-in-production"),
            jwt_expire_minutes=_int("JWT_EXPIRE_MINUTES", 10080),
            default_quota_limit=_int("DEFAULT_QUOTA_LIMIT", 10),
            password_iterations=_int("PASSWORD_ITERATIONS", 100_000),
            subtitle_max_bytes=_int("SUBTITLE_MAX_BYTES", 5 * 1024 * 1024),
            subtitle_timeout_seconds=_int("SUBTITLE_TIMEOUT_SECONDS", 30),
            llm_provider=_str("LLM_PROVIDER", "openai-compatible"),
            llm_base_url=_str("LLM_BASE_URL", ""),
            llm_api_key=_str("LLM_API_KEY", ""),
            llm_model=_str("LLM_MODEL", ""),
            llm_timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 90),
            llm_max_input_chars=_int("LLM_MAX_INPUT_CHARS", 60_000),
            llm_summary_chunk_chars=_int("LLM_SUMMARY_CHUNK_CHARS", 20_000),
            llm_summary_max_chunks=_int("LLM_SUMMARY_MAX_CHUNKS", 16),
            llm_summary_max_output_tokens=_int("LLM_SUMMARY_MAX_OUTPUT_TOKENS", 4096),
            llm_summary_response_format=_str("LLM_SUMMARY_RESPONSE_FORMAT", "auto"),
            llm_summary_thinking_mode=_str("LLM_SUMMARY_THINKING_MODE", "auto"),
            llm_summary_max_point_chars=_int("LLM_SUMMARY_MAX_POINT_CHARS", 240),
            llm_summary_source_context_chars=_int("LLM_SUMMARY_SOURCE_CONTEXT_CHARS", 1200),
            llm_summary_strategy=_str("LLM_SUMMARY_STRATEGY", "legacy"),
            llm_summary_facts_max_source_chars=_int("LLM_SUMMARY_FACTS_MAX_SOURCE_CHARS", 40_000),
            llm_summary_facts_max_per_chunk=_int("LLM_SUMMARY_FACTS_MAX_PER_CHUNK", 12),
            llm_summary_facts_max_evidence_sentences=_int("LLM_SUMMARY_FACTS_MAX_EVIDENCE_SENTENCES", 32),
        )


settings = Settings.from_env()
