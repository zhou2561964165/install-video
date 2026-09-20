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
