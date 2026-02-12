"""Schema 版本迁移链

每个迁移函数只负责一个版本的升级（N → N+1），保持单一职责。
迁移链是有序的，从低版本依次执行到高版本。
注册后的迁移函数不可修改，保证向后兼容。
"""

from typing import Any, Callable, Dict

MigrationFn = Callable[[Dict[str, Any]], Dict[str, Any]]


class MigrationChain:
    """Schema 版本迁移链"""

    def __init__(self) -> None:
        self._migrations: Dict[int, MigrationFn] = {}

    def register(self, from_version: int, fn: MigrationFn) -> None:
        """注册从 from_version 到 from_version+1 的迁移函数。

        Args:
            from_version: 源版本号
            fn: 迁移函数，接受旧版本数据字典，返回新版本数据字典

        Raises:
            ValueError: 如果该版本的迁移函数已注册
        """
        if from_version in self._migrations:
            raise ValueError(
                f"Migration from version {from_version} already registered"
            )
        self._migrations[from_version] = fn

    def migrate(
        self, data: Dict[str, Any], from_version: int, to_version: int
    ) -> Dict[str, Any]:
        """依次执行迁移链，从 from_version 迁移到 to_version。

        Args:
            data: 待迁移的数据字典
            from_version: 当前数据的版本号
            to_version: 目标版本号

        Returns:
            迁移后的数据字典

        Raises:
            ValueError: 如果 from_version >= to_version 或缺少中间版本的迁移函数
        """
        if from_version >= to_version:
            return data

        result = data
        for version in range(from_version, to_version):
            if version not in self._migrations:
                raise ValueError(
                    f"Missing migration from version {version} to {version + 1}"
                )
            result = self._migrations[version](result)

        return result
