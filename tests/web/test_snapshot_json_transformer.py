"""SnapshotJsonTransformer.resolve_special_markers 单元测试"""

import pytest
from src.web.reader import SnapshotJsonTransformer


class TestResolveSpecialMarkers:
    """测试 resolve_special_markers 方法"""

    # --- 基本类型直接返回 ---

    def test_primitive_string(self):
        assert SnapshotJsonTransformer.resolve_special_markers("hello") == "hello"

    def test_primitive_int(self):
        assert SnapshotJsonTransformer.resolve_special_markers(42) == 42

    def test_primitive_float(self):
        assert SnapshotJsonTransformer.resolve_special_markers(3.14) == 3.14

    def test_primitive_bool(self):
        assert SnapshotJsonTransformer.resolve_special_markers(True) is True

    def test_primitive_none(self):
        assert SnapshotJsonTransformer.resolve_special_markers(None) is None

    # --- __dataframe__ 标记 ---

    def test_dataframe_marker(self):
        obj = {"__dataframe__": True, "records": [{"a": 1}, {"a": 2}]}
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == [{"a": 1}, {"a": 2}]

    def test_dataframe_marker_empty_records(self):
        obj = {"__dataframe__": True, "records": []}
        assert SnapshotJsonTransformer.resolve_special_markers(obj) == []

    def test_dataframe_marker_no_records_key(self):
        obj = {"__dataframe__": True}
        assert SnapshotJsonTransformer.resolve_special_markers(obj) == []

    # --- __datetime__ 标记 ---

    def test_datetime_marker_with_timezone(self):
        obj = {"__datetime__": "2025-01-15T14:29:00+08:00"}
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == "2025-01-15 14:29:00"

    def test_datetime_marker_without_timezone(self):
        obj = {"__datetime__": "2025-01-15T14:29:00"}
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == "2025-01-15 14:29:00"

    def test_datetime_marker_invalid_format(self):
        obj = {"__datetime__": "not-a-date"}
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == "not-a-date"

    # --- __date__ 标记 ---

    def test_date_marker(self):
        obj = {"__date__": "2025-01-15"}
        assert SnapshotJsonTransformer.resolve_special_markers(obj) == "2025-01-15"

    # --- __enum__ 标记 ---

    def test_enum_marker(self):
        obj = {"__enum__": "Direction.LONG"}
        assert SnapshotJsonTransformer.resolve_special_markers(obj) == "Direction.LONG"

    # --- __set__ 标记 ---

    def test_set_marker(self):
        obj = {"__set__": True, "values": [1, 2, 3]}
        assert SnapshotJsonTransformer.resolve_special_markers(obj) == [1, 2, 3]

    def test_set_marker_empty(self):
        obj = {"__set__": True, "values": []}
        assert SnapshotJsonTransformer.resolve_special_markers(obj) == []

    def test_set_marker_no_values_key(self):
        obj = {"__set__": True}
        assert SnapshotJsonTransformer.resolve_special_markers(obj) == []

    # --- __dataclass__ 标记 ---

    def test_dataclass_marker(self):
        obj = {"__dataclass__": "module.ClassName", "a": 1, "b": "hello"}
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == {"a": 1, "b": "hello"}

    def test_dataclass_marker_with_nested_markers(self):
        obj = {
            "__dataclass__": "module.Cls",
            "direction": {"__enum__": "Direction.LONG"},
            "count": 5,
        }
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == {"direction": "Direction.LONG", "count": 5}

    # --- 递归解析 ---

    def test_nested_dict(self):
        obj = {
            "level1": {
                "dt": {"__datetime__": "2025-01-15T10:00:00"},
                "val": 42,
            }
        }
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == {"level1": {"dt": "2025-01-15 10:00:00", "val": 42}}

    def test_list_with_markers(self):
        obj = [
            {"__enum__": "Status.ACTIVE"},
            {"__date__": "2025-01-15"},
            "plain",
        ]
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == ["Status.ACTIVE", "2025-01-15", "plain"]

    def test_dataframe_with_nested_markers(self):
        obj = {
            "__dataframe__": True,
            "records": [
                {"dt": {"__datetime__": "2025-01-15T09:00:00"}, "value": 100},
            ],
        }
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == [{"dt": "2025-01-15 09:00:00", "value": 100}]

    def test_regular_dict_no_markers(self):
        obj = {"name": "test", "count": 3}
        assert SnapshotJsonTransformer.resolve_special_markers(obj) == {"name": "test", "count": 3}

    def test_unknown_marker_preserved(self):
        """未知标记应保留原始值（作为普通 dict 递归解析）"""
        obj = {"__unknown__": "something", "data": 1}
        result = SnapshotJsonTransformer.resolve_special_markers(obj)
        assert result == {"__unknown__": "something", "data": 1}


class TestExtractDeliveryMonth:
    """测试 extract_delivery_month 方法"""

    def test_four_digit_month(self):
        assert SnapshotJsonTransformer.extract_delivery_month("pp2601.DCE") == "2601"

    def test_three_digit_month_补全(self):
        assert SnapshotJsonTransformer.extract_delivery_month("SH601.CZCE") == "2601"

    def test_four_digit_month_shfe(self):
        assert SnapshotJsonTransformer.extract_delivery_month("rb2501.SHFE") == "2501"

    def test_three_digit_month_709(self):
        assert SnapshotJsonTransformer.extract_delivery_month("CF709.CZCE") == "2709"

    def test_no_match_returns_other(self):
        assert SnapshotJsonTransformer.extract_delivery_month("UNKNOWN") == "Other"

    def test_empty_string(self):
        assert SnapshotJsonTransformer.extract_delivery_month("") == "Other"


class TestTransformInstruments:
    """测试 transform_instruments 方法"""

    def test_basic_instrument(self):
        """正常标的数据转换"""
        target_aggregate = {
            "instruments": {
                "rb2501.SHFE": {
                    "bars": {
                        "__dataframe__": True,
                        "records": [
                            {"datetime": "2025-01-15 14:29:00", "open": 3500.0, "close": 3505.0, "low": 3498.0, "high": 3510.0, "volume": 1200},
                            {"datetime": "2025-01-15 14:30:00", "open": 3505.0, "close": 3508.0, "low": 3502.0, "high": 3512.0, "volume": 1500},
                        ]
                    },
                    "indicators": {"hv_20": 0.25, "signal": {"__enum__": "Signal.SELL_PUT"}},
                }
            }
        }
        result = SnapshotJsonTransformer.transform_instruments(target_aggregate)

        assert "rb2501.SHFE" in result
        inst = result["rb2501.SHFE"]
        assert inst["dates"] == ["2025-01-15 14:29:00", "2025-01-15 14:30:00"]
        assert inst["ohlc"] == [
            [3500.0, 3505.0, 3498.0, 3510.0],
            [3505.0, 3508.0, 3502.0, 3512.0],
        ]
        assert inst["volumes"] == [1200, 1500]
        assert inst["last_price"] == 3508.0
        assert inst["delivery_month"] == "2501"
        assert inst["indicators"] == {"hv_20": 0.25, "signal": "Signal.SELL_PUT"}
        assert inst["status"] == {}

    def test_skip_empty_bars(self):
        """bars 为空时跳过该标的"""
        target_aggregate = {
            "instruments": {
                "rb2501.SHFE": {
                    "bars": {"__dataframe__": True, "records": []},
                    "indicators": {},
                }
            }
        }
        result = SnapshotJsonTransformer.transform_instruments(target_aggregate)
        assert result == {}

    def test_empty_instruments(self):
        """instruments 为空时返回空 dict"""
        assert SnapshotJsonTransformer.transform_instruments({}) == {}
        assert SnapshotJsonTransformer.transform_instruments({"instruments": {}}) == {}

    def test_datetime_marker_in_bars(self):
        """bars 中的 datetime 字段为 __datetime__ 标记"""
        target_aggregate = {
            "instruments": {
                "pp2601.DCE": {
                    "bars": {
                        "__dataframe__": True,
                        "records": [
                            {
                                "datetime": {"__datetime__": "2025-01-15T14:29:00+08:00"},
                                "open": 100.0, "close": 105.0, "low": 99.0, "high": 106.0, "volume": 500,
                            }
                        ]
                    },
                    "indicators": {},
                }
            }
        }
        result = SnapshotJsonTransformer.transform_instruments(target_aggregate)
        inst = result["pp2601.DCE"]
        assert inst["dates"] == ["2025-01-15 14:29:00"]
        assert inst["delivery_month"] == "2601"

    def test_multiple_instruments(self):
        """多个标的同时转换"""
        target_aggregate = {
            "instruments": {
                "rb2501.SHFE": {
                    "bars": {"__dataframe__": True, "records": [
                        {"datetime": "2025-01-15 14:00:00", "open": 1.0, "close": 2.0, "low": 0.5, "high": 2.5, "volume": 10}
                    ]},
                    "indicators": {},
                },
                "pp2601.DCE": {
                    "bars": {"__dataframe__": True, "records": [
                        {"datetime": "2025-01-15 14:00:00", "open": 50.0, "close": 55.0, "low": 49.0, "high": 56.0, "volume": 20}
                    ]},
                    "indicators": {},
                },
            }
        }
        result = SnapshotJsonTransformer.transform_instruments(target_aggregate)
        assert len(result) == 2
        assert "rb2501.SHFE" in result
        assert "pp2601.DCE" in result

    def test_last_price_from_last_record(self):
        """last_price 取最后一条记录的 close"""
        target_aggregate = {
            "instruments": {
                "rb2501.SHFE": {
                    "bars": {"__dataframe__": True, "records": [
                        {"datetime": "t1", "open": 1.0, "close": 10.0, "low": 0.5, "high": 11.0, "volume": 1},
                        {"datetime": "t2", "open": 2.0, "close": 20.0, "low": 1.5, "high": 21.0, "volume": 2},
                        {"datetime": "t3", "open": 3.0, "close": 30.0, "low": 2.5, "high": 31.0, "volume": 3},
                    ]},
                    "indicators": {},
                }
            }
        }
        result = SnapshotJsonTransformer.transform_instruments(target_aggregate)
        assert result["rb2501.SHFE"]["last_price"] == 30.0
