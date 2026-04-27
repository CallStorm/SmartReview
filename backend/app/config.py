from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from fixed paths so `alembic` (cwd=backend/) still sees repo-root `.env`.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _BACKEND_DIR.parent

_ENV_FILES = tuple(
    p
    for p in (_ROOT_DIR / ".env", _BACKEND_DIR / ".env")
    if p.is_file()
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES if _ENV_FILES else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mysql_user: str = "root"
    mysql_password: str = "rootpassword"
    mysql_host: str = "10.73.2.118"
    mysql_port: int = 3306
    mysql_db: str = "review"

    jwt_secret: str = "40p4jmG0Id_VPCGLsKijqd5FyGpk7aCyG9zjiob5NDw"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    minio_endpoint: str = "10.73.2.118:9000"
    minio_access_key: str = "rag_flow"
    minio_secret_key: str = "infini_rag_flow"
    minio_bucket: str = "review"
    minio_secure: bool = False

    admin_bootstrap: bool = False
    admin_username: str = ""
    admin_password: str = ""
    admin_phone: str = "00000000000"

    # Dify 知识库（可通过环境变量预置；管理员也可在「设置」中覆盖写入数据库）
    dify_base_url: str = ""
    dify_api_key: str = ""

    # 大模型（可选；数据库「设置」优先覆盖非空字段）
    default_llm_provider: str = ""
    volcengine_base_url: str = ""
    volcengine_api_key: str = ""
    volcengine_endpoint_id: str = ""
    minimax_base_url: str = ""
    minimax_api_key: str = ""
    minimax_model: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"

    # OnlyOffice（可在「设置」中覆盖；此处为未配置界面时的兜底）
    onlyoffice_docs_url: str = ""
    onlyoffice_jwt_secret: str = ""
    onlyoffice_callback_base_url: str = ""
    onlyoffice_editor_lang: str = "zh"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
