"""
recorder_patch.py - 数据录制路径补丁

职责:
将 VnPy 的 data_recorder_setting.json 路径重定向到项目 config/general/ 目录。
合并自 child_process.py._patch_data_recorder_setting_path() 和
run_recorder.py._patch_data_recorder_setting_path() 的公共逻辑。
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def patch_data_recorder_setting_path() -> None:
    """
    将 VnPy 的 data_recorder_setting.json 路径重定向到项目 config/general/ 目录。
    如果目标文件不存在，自动创建空 JSON 文件。
    """
    import vnpy.trader.utility as vnpy_utility

    original_get_file_path = vnpy_utility.get_file_path
    config_path = PROJECT_ROOT / "config" / "general" / "data_recorder_setting.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists() or config_path.stat().st_size == 0:
        config_path.write_text("{}", encoding="utf-8")

    def patched_get_file_path(filename: str):
        if filename == "data_recorder_setting.json":
            return config_path
        return original_get_file_path(filename)

    vnpy_utility.get_file_path = patched_get_file_path
    logger.info(f"已重定向 data_recorder_setting.json 到: {config_path}")
