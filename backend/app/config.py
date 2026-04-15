"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: MiroFish/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=True)


class Config:
    """Flask配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    
    # Zep配置
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    # Master kill-switch for all Zep Cloud API calls.
    # Defaults to True only when a ZEP_API_KEY is actually present.
    USE_ZEP = os.environ.get('USE_ZEP', '').strip().lower()
    # Resolved later after class body – see _resolve_use_zep()

    # 图谱后端提供方: zep | hivemind
    GRAPH_PROVIDER = os.environ.get('GRAPH_PROVIDER', 'zep').strip().lower()
    
    # HIVEMIND配置（当 GRAPH_PROVIDER=hivemind 时使用）
    HIVEMIND_API_URL = os.environ.get('HIVEMIND_API_URL', '').rstrip('/')
    HIVEMIND_API_KEY = os.environ.get('HIVEMIND_API_KEY')
    # HIVEMIND 图谱构建期是否同步每个chunk到 /api/memories
    # 关闭可避免构建任务被网络延迟拖慢
    HIVEMIND_SYNC_EPISODES = os.environ.get('HIVEMIND_SYNC_EPISODES', 'false').lower() == 'true'
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 50  # 默认重叠大小
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Tavily Web Search配置（可选 — CSI Research Engine web exploration）
    TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY', '')

    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def zep_enabled(cls) -> bool:
        """Return True only when Zep Cloud calls should be made."""
        # Explicit env var takes precedence
        raw = os.environ.get('USE_ZEP', '').strip().lower()
        if raw in ('true', '1', 'yes'):
            return True
        if raw in ('false', '0', 'no'):
            return False
        # Auto-detect: enabled only when an API key is actually set
        return bool(cls.ZEP_API_KEY)

    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")

        if cls.GRAPH_PROVIDER not in {'zep', 'hivemind'}:
            errors.append("GRAPH_PROVIDER 只能是 zep 或 hivemind")

        # Only require ZEP_API_KEY when Zep is actually enabled
        if cls.GRAPH_PROVIDER == 'zep' and cls.zep_enabled() and not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY 未配置 (GRAPH_PROVIDER=zep)")

        if cls.GRAPH_PROVIDER == 'hivemind':
            if not cls.HIVEMIND_API_URL:
                errors.append("HIVEMIND_API_URL 未配置 (GRAPH_PROVIDER=hivemind)")
            if not cls.HIVEMIND_API_KEY:
                errors.append("HIVEMIND_API_KEY 未配置 (GRAPH_PROVIDER=hivemind)")
        return errors
