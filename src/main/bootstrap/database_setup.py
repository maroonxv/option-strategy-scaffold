"""
database_setup.py - VnPy 数据库配置注入

通过 DatabaseFactory 统一管理数据库初始化。
"""
import logging

from src.main.bootstrap.database_factory import DatabaseFactory
from src.strategy.infrastructure.persistence.exceptions import (
    DatabaseConfigError,
    DatabaseConnectionError,
)

logger = logging.getLogger(__name__)


def setup_vnpy_database() -> bool:
    """
    通过 DatabaseFactory 初始化数据库连接。

    Returns:
        True 如果初始化成功，False 如果配置不完整
    """
    try:
        factory = DatabaseFactory.get_instance()
        factory.initialize(eager=True)
        return True
    except DatabaseConfigError as e:
        logger.warning(f"数据库配置不完整: {e}")
        return False
    except DatabaseConnectionError as e:
        logger.error(f"数据库连接失败: {e}")
        raise
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise
