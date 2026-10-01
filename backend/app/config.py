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
    # v2 账号 + 额度（生产环境务必用环境变量覆盖 JWT_SECRET）
    jwt_secret: str = "dev-secret-change-me-in-production"
    jwt_expire_minutes: int = 10080  # 7 天
    default_quota_limit: int = 10  # 每用户每日下载次数
    password_iterations: int = 100_000  # pbkdf2_hmac 迭代次数

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
            temp_dir=Path(_str("TEMP_DIR", str(_BACKEND_DIR / "tmp"))),
            max_file_size=_int("MAX_FILE_SIZE", 2 * 1024**3),
            ttl_seconds=_int("TTL_SECONDS", 3600),
            db_url=_str("DB_URL", f"sqlite:///{(_BACKEND_DIR / 'jobs.db').as_posix()}"),
            rate_limit_requests=_int("RATE_LIMIT", 30),
            rate_limit_window_seconds=_int("RATE_LIMIT_WINDOW", 60),
            jwt_secret=_str("JWT_SECRET", "dev-secret-change-me-in-production"),
            jwt_expire_minutes=_int("JWT_EXPIRE_MINUTES", 10080),
            default_quota_limit=_int("DEFAULT_QUOTA_LIMIT", 10),
            password_iterations=_int("PASSWORD_ITERATIONS", 100_000),
        )


settings = Settings.from_env()
