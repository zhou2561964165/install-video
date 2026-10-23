import math
import os
import re
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
    # Opt-in free-space reserve; a filesystem quota remains the hard disk boundary.
    download_min_free_bytes: int = 0
    ttl_seconds: int = 3600
    db_url: str = field(default_factory=lambda: f"sqlite:///{(_BACKEND_DIR / 'jobs.db').as_posix()}")
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    network_retries: int = 2
    network_retry_backoff_seconds: float = 0.5
    # Interactive metadata extraction has its own finite I/O budget; downloads retain their policy.
    parse_socket_timeout_seconds: int = 15
    parse_extractor_retries: int = 0
    # Optional operator-owned Netscape jar, read afresh for Bilibili requests only.
    bilibili_cookie_file: str = ""
    bilibili_api_enabled: bool = False
    bilibili_api_download_timeout_seconds: int = 180
    # v2 账号 + 额度（生产环境务必用环境变量覆盖 JWT_SECRET）
    jwt_secret: str = "dev-secret-change-me-in-production"
    jwt_expire_minutes: int = 10080  # 7 天
    default_quota_limit: int = 10  # 每用户每日下载次数
    password_iterations: int = 100_000  # pbkdf2_hmac 迭代次数
    # Pricing is intentionally disabled until explicitly configured. Secrets are never public.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    stripe_billing_mode: str = ""
    stripe_price_label: str = ""
    stripe_public_origin: str = ""
    stripe_vip_duration_days: int = 30
    stripe_timeout_seconds: int = 15
    membership_free_max_height: int = 720
    membership_unlimited_downloads: bool = True
    # v3 字幕 + LLM（OpenAI-compatible；留空表示未配置，仅字幕读取可用）
    subtitle_max_bytes: int = 5 * 1024 * 1024
    subtitle_timeout_seconds: int = 30
    subtitle_max_cues: int = 10000
    mindmap_max_source_chars: int = 60000
    mindmap_max_output_tokens: int = 4096
    mindmap_max_nodes: int = 64
    mindmap_max_depth: int = 4
    asr_model: str = 'tiny'
    asr_model_path: str = ''
    asr_download_root: Path = field(default_factory=lambda: _BACKEND_DIR / 'tmp' / 'asr-models')
    asr_device: str = 'cpu'
    asr_compute_type: str = 'int8'
    asr_vad_filter: bool = False
    asr_max_concurrent: int = 1
    asr_max_duration_seconds: int = 1800
    asr_max_bytes: int = 128 * 1024 * 1024
    asr_timeout_seconds: int = 900
    # H-009: bounded per-process content reuse; download keys persist in SQLite.
    subtitle_cache_ttl_seconds: int = 900
    insight_result_cache_ttl_seconds: int = 3600
    insight_cache_max_entries: int = 128
    insight_cache_max_bytes: int = 16 * 1024 * 1024
    insight_cache_max_inflight: int = 16
    insight_cache_max_waiters: int = 32
    insight_cache_wait_seconds: int = 360
    download_idempotency_ttl_seconds: int = 86400
    download_idempotency_direct_ttl_seconds: int = 300
    download_idempotency_max_entries: int = 10000
    # Public summary availability; independent of experimental pipeline capacity.
    summary_max_source_chars: int = 60_000
    summary_long_threshold_chars: int = 20_000
    llm_long_summary_model: str = "deepseek-v4-pro"
    llm_long_summary_max_input_chars: int = 60_000
    llm_long_summary_max_output_tokens: int = 16_384
    llm_long_summary_timeout_seconds: int = 300
    llm_long_summary_max_concurrent: int = 1
    llm_provider: str = "openai-compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 90
    llm_max_input_chars: int = 60_000
    llm_summary_chunk_chars: int = 20_000
    llm_summary_max_chunks: int = 16
    llm_summary_max_output_tokens: int = 4096
    llm_summary_length_mode: str = "adaptive"
    llm_summary_generation_mode: str = "single"
    llm_summary_output_token_ceiling: int | None = None
    llm_summary_point_ceiling: int = 14
    llm_summary_response_format: str = "auto"
    llm_summary_thinking_mode: str = "auto"
    llm_summary_max_point_chars: int = 240
    llm_summary_source_context_chars: int = 1200
    llm_summary_notes_language: str = "source"
    llm_summary_source_context_mode: str = "auto"
    llm_summary_fidelity_mode: str = "off"
    llm_summary_review_max_output_tokens: int = 4096
    llm_summary_subject_checks_max_output_tokens: int = 8192
    llm_summary_strategy: str = "legacy"
    llm_summary_facts_max_source_chars: int = 40_000
    llm_summary_facts_chunk_chars: int = 8_000
    llm_summary_facts_max_per_chunk: int = 12
    llm_summary_facts_max_evidence_sentences: int = 128
    llm_summary_facts_max_summary_chars: int = 800
    llm_summary_facts_compose_max_output_tokens: int = 0
    llm_summary_facts_audit_max_output_tokens: int = 0
    llm_summary_format_retries: int = 1
    llm_summary_semantic_retries: int = 1
    llm_summary_max_extra_calls: int = 2
    llm_summary_quality_contract: str = "compat"

    def __post_init__(self) -> None:
        if type(self.bilibili_api_enabled) is not bool:
            raise ValueError('bilibili_api_enabled must be boolean')
        if (type(self.bilibili_api_download_timeout_seconds) is not int
                or not 30 <= self.bilibili_api_download_timeout_seconds <= 3600):
            raise ValueError('bilibili_api_download_timeout_seconds must be between 30 and 3600')
        if type(self.download_min_free_bytes) is not int or self.download_min_free_bytes < 0:
            raise ValueError('download_min_free_bytes must be a non-negative integer')
        if self.stripe_billing_mode not in {"", "payment", "subscription"}:
            raise ValueError("stripe_billing_mode must be empty, payment or subscription")
        if (type(self.stripe_vip_duration_days) is not int or type(self.stripe_timeout_seconds) is not int
                or not 1 <= self.stripe_vip_duration_days <= 3660 or not 1 <= self.stripe_timeout_seconds <= 60):
            raise ValueError("Stripe duration or timeout outside bounds")
        if type(self.membership_free_max_height) is not int or not 1 <= self.membership_free_max_height <= 720:
            raise ValueError("membership_free_max_height must be an integer between 1 and 720")
        if type(self.membership_unlimited_downloads) is not bool:
            raise ValueError("membership_unlimited_downloads must be boolean")
        for name, maximum in (
            ('subtitle_max_cues', 50000), ('mindmap_max_source_chars', 60000),
            ('mindmap_max_output_tokens', 4096), ('mindmap_max_nodes', 64),
            ('mindmap_max_depth', 4), ('asr_max_concurrent', 4),
            ('asr_max_duration_seconds', 7200), ('asr_max_bytes', 512 * 1024 * 1024),
            ('asr_timeout_seconds', 3600),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f'{name} must be an integer between 1 and {maximum}')
        if self.asr_model not in {'tiny', 'base', 'small', 'medium', 'large-v3', 'turbo'}:
            raise ValueError('asr_model must name a supported faster-whisper model')
        if self.asr_device not in {'cpu', 'cuda', 'auto'}:
            raise ValueError('asr_device must be cpu, cuda or auto')
        if self.asr_compute_type not in {'int8', 'float16', 'float32', 'int8_float16', 'default'}:
            raise ValueError('unsupported asr_compute_type')
        if type(self.asr_vad_filter) is not bool:
            raise ValueError('asr_vad_filter must be boolean')
        for name, maximum, minimum in (
            ('subtitle_cache_ttl_seconds', 86400, 0),
            ('insight_result_cache_ttl_seconds', 604800, 0),
            ('insight_cache_max_entries', 10000, 1),
            ('insight_cache_max_bytes', 512 * 1024 * 1024, 1),
            ('insight_cache_max_inflight', 128, 1),
            ('insight_cache_max_waiters', 256, 1),
            ('insight_cache_wait_seconds', 900, 1),
            ('download_idempotency_ttl_seconds', 604800, 1),
            ('download_idempotency_direct_ttl_seconds', 3600, 1),
            ('download_idempotency_max_entries', 100000, 1),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f'{name} must be an integer between {minimum} and {maximum}')
        for name, maximum in (("summary_long_threshold_chars", 60_000),
                              ("llm_long_summary_max_input_chars", 60_000),
                              ("llm_long_summary_max_output_tokens", 65_536),
                              ("llm_long_summary_timeout_seconds", 900),
                              ("llm_long_summary_max_concurrent", 32)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be an integer between 1 and {maximum}")
        if (type(self.llm_long_summary_model) is not str
                or re.fullmatch(r"deepseek-v[4-9][0-9]*-pro", self.llm_long_summary_model) is None):
            raise ValueError("llm_long_summary_model must be a DeepSeek v4+ Pro model")
        if type(self.llm_summary_notes_language) is not str or self.llm_summary_notes_language not in {"source", "output"}:
            raise ValueError("llm_summary_notes_language must be source or output")
        if type(self.llm_summary_source_context_mode) is not str or self.llm_summary_source_context_mode not in {"auto", "boundary"}:
            raise ValueError("llm_summary_source_context_mode must be auto or boundary")
        if type(self.llm_summary_fidelity_mode) is not str or self.llm_summary_fidelity_mode not in {"off", "long", "review", "checks", "subject_checks"}:
            raise ValueError("llm_summary_fidelity_mode must be off, long, review, checks or subject_checks")
        if (type(self.llm_summary_review_max_output_tokens) is not int
                or not 1 <= self.llm_summary_review_max_output_tokens <= 65536):
            raise ValueError("llm_summary_review_max_output_tokens must be an integer between 1 and 65536")
        if (type(self.llm_summary_subject_checks_max_output_tokens) is not int
                or not 1 <= self.llm_summary_subject_checks_max_output_tokens <= 65536):
            raise ValueError("llm_summary_subject_checks_max_output_tokens must be an integer between 1 and 65536")
        if (type(self.summary_max_source_chars) is not int
                or not 1 <= self.summary_max_source_chars <= 1_000_000):
            raise ValueError("summary_max_source_chars must be an integer between 1 and 1000000")
        if type(self.llm_summary_generation_mode) is not str or self.llm_summary_generation_mode not in {"single", "staged"}:
            raise ValueError("llm_summary_generation_mode must be single or staged")
        if type(self.llm_summary_length_mode) is not str or self.llm_summary_length_mode not in {"adaptive", "fixed"}:
            raise ValueError("llm_summary_length_mode must be adaptive or fixed")
        if type(self.llm_summary_max_output_tokens) is not int or not 1 <= self.llm_summary_max_output_tokens <= 65536:
            raise ValueError("llm_summary_max_output_tokens must be an integer between 1 and 65536")
        if self.llm_summary_output_token_ceiling is None:
            self.llm_summary_output_token_ceiling = max(8192, self.llm_summary_max_output_tokens)
        if (type(self.llm_summary_output_token_ceiling) is not int
                or not 1 <= self.llm_summary_output_token_ceiling <= 65536
                or self.llm_summary_output_token_ceiling < self.llm_summary_max_output_tokens):
            raise ValueError("llm_summary_output_token_ceiling must cover the base budget and be <= 65536")
        if type(self.llm_summary_point_ceiling) is not int or not 7 <= self.llm_summary_point_ceiling <= 32:
            raise ValueError("llm_summary_point_ceiling must be an integer between 7 and 32")
        if self.network_retries < 0:
            raise ValueError("network_retries must be >= 0")
        if type(self.parse_socket_timeout_seconds) is not int or not 1 <= self.parse_socket_timeout_seconds <= 60:
            raise ValueError("parse_socket_timeout_seconds must be an integer between 1 and 60")
        if type(self.parse_extractor_retries) is not int or not 0 <= self.parse_extractor_retries <= 2:
            raise ValueError("parse_extractor_retries must be an integer between 0 and 2")
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
        if (type(self.llm_summary_quality_contract) is not str
                or self.llm_summary_quality_contract not in {"compat", "compact"}):
            raise ValueError("llm_summary_quality_contract must be compat or compact")
        for name, maximum in (("llm_summary_facts_max_source_chars", 1_000_000),
                              ("llm_summary_facts_chunk_chars", 1_000_000),
                              ("llm_summary_facts_max_per_chunk", 48),
                              ("llm_summary_facts_max_evidence_sentences", 256),
                              ("llm_summary_facts_max_summary_chars", 4000)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be an integer between 1 and {maximum}")
        for name in ("llm_summary_facts_compose_max_output_tokens", "llm_summary_facts_audit_max_output_tokens"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 65536:
                raise ValueError(f"{name} must be an integer between 0 and 65536")
        for name in ("llm_summary_format_retries", "llm_summary_semantic_retries", "llm_summary_max_extra_calls"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 2:
                raise ValueError(f"{name} must be an integer between 0 and 2")

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
            download_min_free_bytes=_int("DOWNLOAD_MIN_FREE_BYTES", 0),
            ttl_seconds=_int("TTL_SECONDS", 3600),
            db_url=_str("DB_URL", f"sqlite:///{(_BACKEND_DIR / 'jobs.db').as_posix()}"),
            rate_limit_requests=_int("RATE_LIMIT", 30),
            rate_limit_window_seconds=_int("RATE_LIMIT_WINDOW", 60),
            network_retries=_int("NETWORK_RETRIES", 2),
            network_retry_backoff_seconds=_float("NETWORK_RETRY_BACKOFF_SECONDS", 0.5),
            parse_socket_timeout_seconds=_int("PARSE_SOCKET_TIMEOUT_SECONDS", 15),
            parse_extractor_retries=_int("PARSE_EXTRACTOR_RETRIES", 0),
            bilibili_cookie_file=_str("BILIBILI_COOKIE_FILE", "").strip(),
            bilibili_api_enabled=_str('BILIBILI_API_ENABLED', 'false').lower() in {'1', 'true', 'yes'},
            bilibili_api_download_timeout_seconds=_int('BILIBILI_API_DOWNLOAD_TIMEOUT_SECONDS', 180),
            jwt_secret=_str("JWT_SECRET", "dev-secret-change-me-in-production"),
            jwt_expire_minutes=_int("JWT_EXPIRE_MINUTES", 10080),
            default_quota_limit=_int("DEFAULT_QUOTA_LIMIT", 10),
            password_iterations=_int("PASSWORD_ITERATIONS", 100_000),
            stripe_secret_key=_str("STRIPE_SECRET_KEY", ""),
            stripe_webhook_secret=_str("STRIPE_WEBHOOK_SECRET", ""),
            stripe_price_id=_str("STRIPE_PRICE_ID", "").strip() or _str("STRIPE_PRICE_ID_MONTHLY", "").strip(),
            stripe_billing_mode=_str("STRIPE_BILLING_MODE", ""),
            stripe_price_label=_str("STRIPE_PRICE_LABEL", ""),
            stripe_public_origin=_str("STRIPE_PUBLIC_ORIGIN", "").strip() or _str("FRONTEND_URL", "").strip(),
            stripe_vip_duration_days=_int("STRIPE_VIP_DURATION_DAYS", 30),
            stripe_timeout_seconds=_int("STRIPE_TIMEOUT_SECONDS", 15),
            membership_free_max_height=_int("MEMBERSHIP_FREE_MAX_HEIGHT", 720),
            membership_unlimited_downloads=_str("MEMBERSHIP_UNLIMITED_DOWNLOADS", "true").lower() in {"1", "true", "yes"},
            subtitle_max_bytes=_int("SUBTITLE_MAX_BYTES", 5 * 1024 * 1024),
            subtitle_timeout_seconds=_int("SUBTITLE_TIMEOUT_SECONDS", 30),
            subtitle_max_cues=_int('SUBTITLE_MAX_CUES', 10000),
            mindmap_max_source_chars=_int('MINDMAP_MAX_SOURCE_CHARS', 60000),
            mindmap_max_output_tokens=_int('MINDMAP_MAX_OUTPUT_TOKENS', 4096),
            mindmap_max_nodes=_int('MINDMAP_MAX_NODES', 64),
            mindmap_max_depth=_int('MINDMAP_MAX_DEPTH', 4),
            asr_model=_str('ASR_MODEL', 'tiny'),
            asr_model_path=_str('ASR_MODEL_PATH', ''),
            asr_download_root=Path(_str('ASR_DOWNLOAD_ROOT', str(_BACKEND_DIR / 'tmp' / 'asr-models'))),
            asr_device=_str('ASR_DEVICE', 'cpu'),
            asr_compute_type=_str('ASR_COMPUTE_TYPE', 'int8'),
            asr_vad_filter=_str('ASR_VAD_FILTER', 'false').lower() in {'1', 'true', 'yes'},
            asr_max_concurrent=_int('ASR_MAX_CONCURRENT', 1),
            asr_max_duration_seconds=_int('ASR_MAX_DURATION_SECONDS', 1800),
            asr_max_bytes=_int('ASR_MAX_BYTES', 128 * 1024 * 1024),
            asr_timeout_seconds=_int('ASR_TIMEOUT_SECONDS', 900),
            subtitle_cache_ttl_seconds=_int('SUBTITLE_CACHE_TTL_SECONDS', 900),
            insight_result_cache_ttl_seconds=_int('INSIGHT_RESULT_CACHE_TTL_SECONDS', 3600),
            insight_cache_max_entries=_int('INSIGHT_CACHE_MAX_ENTRIES', 128),
            insight_cache_max_bytes=_int('INSIGHT_CACHE_MAX_BYTES', 16 * 1024 * 1024),
            insight_cache_max_inflight=_int('INSIGHT_CACHE_MAX_INFLIGHT', 16),
            insight_cache_max_waiters=_int('INSIGHT_CACHE_MAX_WAITERS', 32),
            insight_cache_wait_seconds=_int('INSIGHT_CACHE_WAIT_SECONDS', 360),
            download_idempotency_ttl_seconds=_int('DOWNLOAD_IDEMPOTENCY_TTL_SECONDS', 86400),
            download_idempotency_direct_ttl_seconds=_int('DOWNLOAD_IDEMPOTENCY_DIRECT_TTL_SECONDS', 300),
            download_idempotency_max_entries=_int('DOWNLOAD_IDEMPOTENCY_MAX_ENTRIES', 10000),
            summary_max_source_chars=_int("SUMMARY_MAX_SOURCE_CHARS", 60_000),
            summary_long_threshold_chars=_int("SUMMARY_LONG_THRESHOLD_CHARS", 20_000),
            llm_long_summary_model=_str("LLM_LONG_SUMMARY_MODEL", "deepseek-v4-pro"),
            llm_long_summary_max_input_chars=_int("LLM_LONG_SUMMARY_MAX_INPUT_CHARS", 60_000),
            llm_long_summary_max_output_tokens=_int("LLM_LONG_SUMMARY_MAX_OUTPUT_TOKENS", 16_384),
            llm_long_summary_timeout_seconds=_int("LLM_LONG_SUMMARY_TIMEOUT_SECONDS", 300),
            llm_long_summary_max_concurrent=_int("LLM_LONG_SUMMARY_MAX_CONCURRENT", 1),
            llm_provider=_str("LLM_PROVIDER", "openai-compatible"),
            llm_base_url=_str("LLM_BASE_URL", ""),
            llm_api_key=_str("LLM_API_KEY", ""),
            llm_model=_str("LLM_MODEL", ""),
            llm_timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 90),
            llm_max_input_chars=_int("LLM_MAX_INPUT_CHARS", 60_000),
            llm_summary_chunk_chars=_int("LLM_SUMMARY_CHUNK_CHARS", 20_000),
            llm_summary_max_chunks=_int("LLM_SUMMARY_MAX_CHUNKS", 16),
            llm_summary_max_output_tokens=_int("LLM_SUMMARY_MAX_OUTPUT_TOKENS", 4096),
            llm_summary_length_mode=_str("LLM_SUMMARY_LENGTH_MODE", "adaptive"),
            llm_summary_generation_mode=_str("LLM_SUMMARY_GENERATION_MODE", "single"),
            llm_summary_output_token_ceiling=(
                _int("LLM_SUMMARY_OUTPUT_TOKEN_CEILING", 8192)
                if os.getenv("LLM_SUMMARY_OUTPUT_TOKEN_CEILING") is not None else None
            ),
            llm_summary_point_ceiling=_int("LLM_SUMMARY_POINT_CEILING", 14),
            llm_summary_response_format=_str("LLM_SUMMARY_RESPONSE_FORMAT", "auto"),
            llm_summary_thinking_mode=_str("LLM_SUMMARY_THINKING_MODE", "auto"),
            llm_summary_max_point_chars=_int("LLM_SUMMARY_MAX_POINT_CHARS", 240),
            llm_summary_source_context_chars=_int("LLM_SUMMARY_SOURCE_CONTEXT_CHARS", 1200),
            llm_summary_notes_language=_str("LLM_SUMMARY_NOTES_LANGUAGE", "source"),
            llm_summary_source_context_mode=_str("LLM_SUMMARY_SOURCE_CONTEXT_MODE", "auto"),
            llm_summary_fidelity_mode=_str("LLM_SUMMARY_FIDELITY_MODE", "off"),
            llm_summary_review_max_output_tokens=_int("LLM_SUMMARY_REVIEW_MAX_OUTPUT_TOKENS", 4096),
            llm_summary_subject_checks_max_output_tokens=_int("LLM_SUMMARY_SUBJECT_CHECKS_MAX_OUTPUT_TOKENS", 8192),
            llm_summary_strategy=_str("LLM_SUMMARY_STRATEGY", "legacy"),
            llm_summary_facts_max_source_chars=_int("LLM_SUMMARY_FACTS_MAX_SOURCE_CHARS", 40_000),
            llm_summary_facts_chunk_chars=_int("LLM_SUMMARY_FACTS_CHUNK_CHARS", 8_000),
            llm_summary_facts_max_per_chunk=_int("LLM_SUMMARY_FACTS_MAX_PER_CHUNK", 12),
            llm_summary_facts_max_evidence_sentences=_int("LLM_SUMMARY_FACTS_MAX_EVIDENCE_SENTENCES", 128),
            llm_summary_facts_max_summary_chars=_int("LLM_SUMMARY_FACTS_MAX_SUMMARY_CHARS", 800),
            llm_summary_facts_compose_max_output_tokens=_int("LLM_SUMMARY_FACTS_COMPOSE_MAX_OUTPUT_TOKENS", 0),
            llm_summary_facts_audit_max_output_tokens=_int("LLM_SUMMARY_FACTS_AUDIT_MAX_OUTPUT_TOKENS", 0),
            llm_summary_format_retries=_int("LLM_SUMMARY_FORMAT_RETRIES", 1),
            llm_summary_semantic_retries=_int("LLM_SUMMARY_SEMANTIC_RETRIES", 1),
            llm_summary_max_extra_calls=_int("LLM_SUMMARY_MAX_EXTRA_CALLS", 2),
            llm_summary_quality_contract=_str("LLM_SUMMARY_QUALITY_CONTRACT", "compat"),
        )


settings = Settings.from_env()
