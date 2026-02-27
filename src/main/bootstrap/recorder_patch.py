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
    支持从 TOML 格式转换为 JSON 格式供 VnPy 使用。
    """
    import sys
    import json
    import vnpy.trader.utility as vnpy_utility
    
    # Python 3.11+ 内置 tomllib，之前版本使用 tomli
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    original_get_file_path = vnpy_utility.get_file_path
    toml_path = PROJECT_ROOT / "config" / "general" / "data_recorder_setting.toml"
    json_path = PROJECT_ROOT / "config" / "general" / "data_recorder_setting.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果 TOML 文件存在，从 TOML 转换为 JSON
    if toml_path.exists():
        try:
            with open(toml_path, "rb") as f:
                toml_data = tomllib.load(f)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(toml_data, f, ensure_ascii=False, indent=2)
            logger.info(f"已从 TOML 转换配置: {toml_path} -> {json_path}")
        except Exception as e:
            logger.error(f"转换 TOML 配置失败: {e}")
            if not json_path.exists():
                json_path.write_text("{}", encoding="utf-8")
    elif not json_path.exists() or json_path.stat().st_size == 0:
        # 如果 TOML 和 JSON 都不存在，创建空 JSON
        json_path.write_text("{}", encoding="utf-8")

    def patched_get_file_path(filename: str):
        if filename == "data_recorder_setting.json":
            return json_path
        return original_get_file_path(filename)

    vnpy_utility.get_file_path = patched_get_file_path
    logger.info(f"已重定向 data_recorder_setting.json 到: {json_path}")
