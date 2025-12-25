"""
Configuration for UGC Ad Factory

Loads environment variables and provides typed configuration.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # ComfyUI Configuration
    comfyui_host: str = "localhost"
    comfyui_port: int = 8188

    @property
    def comfyui_url(self) -> str:
        return f"http://{self.comfyui_host}:{self.comfyui_port}"

    # KeyAI Sora 2 Pro Configuration
    keyai_api_key: str = ""
    keyai_api_url: str = "https://api.kie.ai/api/v1"

    # Google Cloud Storage
    gcp_project: str = "parallel-universe-prod"
    gcs_bucket: str = "ugc-ad-assets"
    google_application_credentials: str | None = None

    # LLM Configuration
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"

    # Service Configuration
    ugc_service_port: int = 8090
    ugc_service_host: str = "0.0.0.0"

    # Rendering Configuration
    comfyui_concurrency: int = 4  # Max parallel ComfyUI jobs
    keyai_concurrency: int = 10  # Max parallel KeyAI jobs
    max_retries: int = 2  # Retry failed renders
    keyai_timeout: int = 300  # 5 min timeout per video task

    # QC Configuration
    qc_min_duration: float = 9.0  # seconds
    qc_max_duration: float = 17.0  # seconds
    qc_pass_threshold: float = 0.7

    # Default generation settings
    default_variations: int = 20
    max_variations: int = 30

    # Paths
    @property
    def base_dir(self) -> Path:
        return Path(__file__).parent

    @property
    def templates_dir(self) -> Path:
        return self.base_dir / "templates"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra env vars from parent project


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience exports
settings = get_settings()
