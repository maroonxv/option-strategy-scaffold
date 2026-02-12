"""JSON 序列化器，支持 DataFrame、datetime、set、Enum、dataclass 等特殊类型。

类型转换规则:
| Python 类型    | JSON 表示                                          | 反序列化还原              |
|---------------|---------------------------------------------------|--------------------------|
| pd.DataFrame  | {"__dataframe__": true, "records": [...]}          | pd.DataFrame(records)    |
| datetime      | {"__datetime__": "ISO 8601 字符串"}                 | datetime.fromisoformat   |
| date          | {"__date__": "ISO 8601 日期字符串"}                  | date.fromisoformat       |
| set           | {"__set__": true, "values": [...]}                 | set(values)              |
| Enum          | {"__enum__": "ClassName.VALUE"}                    | 动态还原                  |
| dataclass     | {"__dataclass__": "module.ClassName", ...fields}   | 动态还原                  |
"""

import dataclasses
import importlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict

import pandas as pd

from src.strategy.infrastructure.persistence.migration_chain import MigrationChain

CURRENT_SCHEMA_VERSION = 1


class _CustomEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，处理 DataFrame、datetime、date、set、Enum、dataclass。"""

    def default(self, o: Any) -> Any:
        if isinstance(o, pd.DataFrame):
            return {"__dataframe__": True, "records": o.to_dict(orient="records")}

        if isinstance(o, datetime):
            return {"__datetime__": o.isoformat()}

        if isinstance(o, date):
            return {"__date__": o.isoformat()}

        if isinstance(o, set):
            return {"__set__": True, "values": sorted(o, key=repr)}

        if isinstance(o, Enum):
            return {"__enum__": f"{type(o).__name__}.{o.name}"}

        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            module = type(o).__module__
            qualname = type(o).__qualname__
            fields = dataclasses.asdict(o)
            return {"__dataclass__": f"{module}.{qualname}", **fields}

        return super().default(o)


def _object_hook(obj: Dict[str, Any]) -> Any:
    """JSON 反序列化 object_hook，还原特殊类型标记。"""

    if obj.get("__dataframe__") is True and "records" in obj:
        records = obj["records"]
        return pd.DataFrame(records) if records else pd.DataFrame()

    if "__datetime__" in obj:
        return datetime.fromisoformat(obj["__datetime__"])

    if "__date__" in obj:
        return date.fromisoformat(obj["__date__"])

    if obj.get("__set__") is True and "values" in obj:
        return set(obj["values"])

    if "__enum__" in obj:
        enum_ref = obj["__enum__"]  # e.g. "SignalType.EXAMPLE_OPEN"
        return _resolve_enum(enum_ref)

    if "__dataclass__" in obj:
        return _resolve_dataclass(obj)

    return obj


def _resolve_enum(enum_ref: str) -> Any:
    """动态还原 Enum 值。

    enum_ref 格式: "ClassName.MEMBER_NAME"
    搜索策略: 在已加载的模块中查找匹配的 Enum 子类。
    """
    parts = enum_ref.split(".", 1)
    if len(parts) != 2:
        return enum_ref

    class_name, member_name = parts

    # 在已导入的模块中搜索
    import sys
    for module in list(sys.modules.values()):
        if module is None:
            continue
        cls = getattr(module, class_name, None)
        if cls is not None and isinstance(cls, type) and issubclass(cls, Enum):
            try:
                return cls[member_name]
            except KeyError:
                continue

    # 找不到时返回原始字符串
    return enum_ref


def _resolve_dataclass(obj: Dict[str, Any]) -> Any:
    """动态还原 dataclass 实例。

    obj 包含 "__dataclass__": "module.ClassName" 以及各字段。
    """
    fqn = obj["__dataclass__"]  # e.g. "src.module.MyClass"
    parts = fqn.rsplit(".", 1)
    if len(parts) != 2:
        return obj

    module_path, class_name = parts
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    except (ImportError, AttributeError):
        return obj

    if not dataclasses.is_dataclass(cls):
        return obj

    fields = {k: v for k, v in obj.items() if k != "__dataclass__"}
    try:
        return cls(**fields)
    except TypeError:
        return obj


class JsonSerializer:
    """JSON 序列化器，支持 DataFrame 和 datetime 等特殊类型。"""

    def __init__(self, migration_chain: MigrationChain) -> None:
        self._migration_chain = migration_chain

    def serialize(self, data: Dict[str, Any]) -> str:
        """序列化为 JSON 字符串。

        - 自动注入 schema_version
        - DataFrame → records 格式 (list of dicts)
        - datetime → ISO 8601 字符串
        - set → list
        - Enum → value
        - dataclass → dict
        """
        payload = {"schema_version": CURRENT_SCHEMA_VERSION, **data}
        return json.dumps(payload, cls=_CustomEncoder, ensure_ascii=False)

    def deserialize(self, json_str: str) -> Dict[str, Any]:
        """从 JSON 字符串反序列化。

        - 检查 schema_version，必要时执行迁移
        - records 格式 → DataFrame
        - ISO 8601 字符串 → datetime
        """
        data = json.loads(json_str, object_hook=_object_hook)

        # 版本迁移
        version = data.get("schema_version", 1)
        if version < CURRENT_SCHEMA_VERSION:
            data = self._migration_chain.migrate(
                data, version, CURRENT_SCHEMA_VERSION
            )
            data["schema_version"] = CURRENT_SCHEMA_VERSION

        return data
