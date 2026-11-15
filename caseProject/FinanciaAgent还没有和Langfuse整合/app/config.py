from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 当前.env文件的绝对路径
# 当前项目的绝对路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 会自动从环境变量和 .env 文件读取配置。
class Settings(BaseSettings):
    """Pydantic 环境配置模型；字段名自动对应大写环境变量。"""
    app_env: str = "development"
    app_version: str = "finqa-agent-0.1.0"


    database_url: str = "sqlite:///./data/agent.db"
    checkpoint_db_path: str = "./data/checkpoints.db"
    store_db_path: str = "./data/store.db"


    frontend_origin: str = "http://127.0.0.1:5173"
    # SSE 采用有界内存队列；心跳保持空闲连接，断连会取消本轮 Agent。
    sse_queue_size: int = Field(default=32, ge=1, le=1024)
    sse_heartbeat_seconds: float = Field(default=10.0, ge=0.1, le=60)


    log_level: str = "INFO"
    log_dir: str = "./logs"
    log_max_bytes: int = 10_485_760
    log_backup_count: int = 5



    main_model_provider: str = "deepseek"
    main_model: str = "deepseek-flash"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    zhipu_model: str = ""

    reviewer_model_provider: str = "zhipu"
    reviewer_model: str = "glm-5.3-flash"



    langfuse_enabled: bool = False
    langfuse_host: str = "http://127.0.0.1:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_environment: str = "development"
    langfuse_release: str = "local-dev"
    ##
    langfuse_prompt_management_enabled: bool = True
    langfuse_prompt_label: str = "production"
    langfuse_prompt_cache_ttl_seconds: int = 300
    langfuse_main_prompt_name: str = "finqa/agents/main"
    langfuse_researcher_prompt_name: str = "finqa/agents/researcher"
    langfuse_reviewer_prompt_name: str = "finqa/agents/reviewer"



    finqa_data_dir: str = "./data/finqa"
    finqa_default_split: str = "sample"


    # 三层上限分别约束图步骤、模型调用和工具调用，防止 Agent 循环消耗 Token。
    max_agent_steps: int = 200
    max_model_calls: int = 20
    max_tool_calls: int = 40
    ##
    main_max_calculations: int = 16
    researcher_max_model_calls: int = 20
    researcher_max_report_calls: int = 6
    researcher_max_search_calls: int = 6
    reviewer_max_model_calls: int = 16
    reviewer_max_calculations: int = 24



    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolve_path(self, value: str) -> Path:
        """将 .env 中的相对路径解析为项目绝对路径。"""
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def data_dir(self) -> Path:
        """返回原始 FinQA JSON 数据目录。"""
        return self.resolve_path(self.finqa_data_dir)

    @property
    def checkpoint_path(self) -> Path:
        """返回 LangGraph Checkpointer SQLite 文件路径。"""
        return self.resolve_path(self.checkpoint_db_path)

    @property
    def store_path(self) -> Path:
        """返回会话目录 Store SQLite 文件路径。"""
        return self.resolve_path(self.store_db_path)

    @property
    def logs_path(self) -> Path:
        """返回结构化运行日志目录。"""
        return self.resolve_path(self.log_dir)


@lru_cache
def get_settings() -> Settings:
    """进程内缓存配置，避免每次 Agent 调用重复读取 `.env`。"""
    # 只在创建 Settings() 实例时读取一次；你修改 .env 后，通常需要重启 FastAPI 服务
    return Settings()##===================================
if __name__ == "__main__":
    settings = get_settings()##===================================
    print("项目目录：", PROJECT_ROOT)
    print("主模型：", settings.main_model)
    print("会话库：", settings.checkpoint_path)

