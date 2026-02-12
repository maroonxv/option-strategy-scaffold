"""
SnapshotJsonTransformer.resolve_special_markers 属性测试

Feature: web-mysql-state-reader
Property 1: Special marker resolution produces only JSON-primitive types
**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 3.4, 4.5**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.web.reader import SnapshotJsonTransformer

# ---------------------------------------------------------------------------
# Marker keys that resolve_special_markers should eliminate
# ---------------------------------------------------------------------------
MARKER_KEYS = frozenset(
    {"__dataframe__", "__datetime__", "__date__", "__enum__", "__set__", "__dataclass__"}
)

# JSON-primitive types allowed in the resolved output
JSON_PRIMITIVE_TYPES = (str, int, float, bool, type(None), list, dict)

# ---------------------------------------------------------------------------
# Hypothesis strategies – generate nested structures with random markers
# ---------------------------------------------------------------------------

# Leaf values that can appear inside marker payloads or plain dicts
_json_primitives = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.text(min_size=0, max_size=30),
)


def _datetime_marker():
    """Generate a __datetime__ marker with a plausible ISO string."""
    return st.builds(
        lambda y, mo, d, h, mi, s: {
            "__datetime__": f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}"
        },
        y=st.integers(min_value=2000, max_value=2030),
        mo=st.integers(min_value=1, max_value=12),
        d=st.integers(min_value=1, max_value=28),
        h=st.integers(min_value=0, max_value=23),
        mi=st.integers(min_value=0, max_value=59),
        s=st.integers(min_value=0, max_value=59),
    )


def _date_marker():
    """Generate a __date__ marker."""
    return st.builds(
        lambda y, mo, d: {"__date__": f"{y:04d}-{mo:02d}-{d:02d}"},
        y=st.integers(min_value=2000, max_value=2030),
        mo=st.integers(min_value=1, max_value=12),
        d=st.integers(min_value=1, max_value=28),
    )


def _enum_marker():
    """Generate an __enum__ marker like 'ClassName.VALUE'."""
    cls = st.sampled_from(["Direction", "Offset", "Status", "Exchange", "Interval"])
    val = st.sampled_from(["LONG", "SHORT", "OPEN", "CLOSE", "ACTIVE", "CANCELLED"])
    return st.builds(lambda c, v: {"__enum__": f"{c}.{v}"}, c=cls, v=val)


def _set_marker(children):
    """Generate a __set__ marker whose values are drawn from *children*."""
    return st.builds(
        lambda vals: {"__set__": True, "values": vals},
        vals=st.lists(children, max_size=5),
    )


def _dataframe_marker(children):
    """Generate a __dataframe__ marker with a list of record dicts."""
    record = st.dictionaries(
        keys=st.sampled_from(["datetime", "open", "close", "low", "high", "volume"]),
        values=children,
        min_size=1,
        max_size=6,
    )
    return st.builds(
        lambda recs: {"__dataframe__": True, "records": recs},
        recs=st.lists(record, max_size=4),
    )


def _dataclass_marker(children):
    """Generate a __dataclass__ marker with arbitrary fields."""
    fields = st.dictionaries(
        keys=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
            min_size=1,
            max_size=8,
        ),
        values=children,
        min_size=0,
        max_size=5,
    )
    return st.builds(
        lambda f: {"__dataclass__": "module.SomeClass", **f},
        f=fields,
    )


def _nested_json(max_depth: int = 3):
    """Recursive strategy producing arbitrarily nested JSON with special markers."""
    if max_depth <= 0:
        return _json_primitives

    children = st.deferred(lambda: _nested_json(max_depth - 1))

    marker = st.one_of(
        _datetime_marker(),
        _date_marker(),
        _enum_marker(),
        _set_marker(children),
        _dataframe_marker(children),
        _dataclass_marker(children),
    )

    plain_dict = st.dictionaries(
        keys=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
            min_size=1,
            max_size=10,
        ),
        values=children,
        max_size=5,
    )

    plain_list = st.lists(children, max_size=5)

    return st.one_of(_json_primitives, marker, plain_dict, plain_list)


# The top-level strategy: always produce a dict or list (non-trivial input)
_nested_structure = st.one_of(
    st.dictionaries(
        keys=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
            min_size=1,
            max_size=10,
        ),
        values=_nested_json(max_depth=3),
        min_size=1,
        max_size=6,
    ),
    st.lists(_nested_json(max_depth=3), min_size=1, max_size=6),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_values_are_json_primitives(obj) -> bool:
    """Return True iff every value in the (possibly nested) structure is a JSON primitive."""
    if isinstance(obj, dict):
        return all(
            isinstance(k, str)
            and _all_values_are_json_primitives(v)
            for k, v in obj.items()
        )
    if isinstance(obj, list):
        return all(_all_values_are_json_primitives(item) for item in obj)
    return isinstance(obj, JSON_PRIMITIVE_TYPES)


def _no_marker_keys(obj) -> bool:
    """Return True iff no dict in the structure contains a marker key."""
    if isinstance(obj, dict):
        if MARKER_KEYS & obj.keys():
            return False
        return all(_no_marker_keys(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_marker_keys(item) for item in obj)
    return True


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestResolveSpecialMarkersProperty:
    """Property 1: Special marker resolution produces only JSON-primitive types

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 3.4, 4.5**
    """

    @given(data=_nested_structure)
    @settings(max_examples=100)
    def test_resolved_output_contains_only_json_primitives(self, data):
        """After resolve_special_markers, every value must be a JSON primitive type."""
        result = SnapshotJsonTransformer.resolve_special_markers(data)
        assert _all_values_are_json_primitives(result), (
            f"Non-JSON-primitive found in resolved output: {result!r}"
        )

    @given(data=_nested_structure)
    @settings(max_examples=100)
    def test_resolved_output_has_no_marker_keys(self, data):
        """After resolve_special_markers, no dict shall contain any marker key."""
        result = SnapshotJsonTransformer.resolve_special_markers(data)
        assert _no_marker_keys(result), (
            f"Marker key still present in resolved output: {result!r}"
        )


# ---------------------------------------------------------------------------
# Property 2: Bars extraction preserves record count and data
# ---------------------------------------------------------------------------


def _bar_record():
    """Generate a single bar record with datetime, open, close, low, high, volume."""
    return st.fixed_dictionaries(
        {
            "datetime": st.text(
                alphabet=st.sampled_from("0123456789-T: "),
                min_size=10,
                max_size=25,
            ),
            "open": st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
            "close": st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
            "low": st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
            "high": st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
            "volume": st.integers(min_value=0, max_value=1_000_000),
        }
    )


def _bar_records_list():
    """Generate a non-empty list of bar records."""
    return st.lists(_bar_record(), min_size=1, max_size=20)


class TestBarsExtractionProperty:
    """Property 2: Bars extraction preserves record count and data

    **Validates: Requirements 3.1, 3.2**
    """

    @given(records=_bar_records_list())
    @settings(max_examples=100)
    def test_bars_extraction_preserves_record_count_and_data(self, records):
        """For any list of bar records, extracting dates/ohlc/volumes SHALL produce
        three lists of equal length matching the input record count, with correct values."""
        vt_symbol = "test2501.SHFE"
        target_aggregate = {
            "instruments": {
                vt_symbol: {
                    "bars": {"__dataframe__": True, "records": records},
                }
            }
        }

        result = SnapshotJsonTransformer.transform_instruments(target_aggregate)

        assert vt_symbol in result, f"Expected {vt_symbol} in result"
        instrument = result[vt_symbol]

        dates = instrument["dates"]
        ohlc = instrument["ohlc"]
        volumes = instrument["volumes"]

        # Length invariant: all three lists match input record count
        assert len(dates) == len(records)
        assert len(ohlc) == len(records)
        assert len(volumes) == len(records)

        # Data invariant: each element matches the corresponding input record
        for i, record in enumerate(records):
            assert ohlc[i] == [
                record["open"],
                record["close"],
                record["low"],
                record["high"],
            ], f"ohlc[{i}] mismatch"
            assert volumes[i] == record["volume"], f"volumes[{i}] mismatch"


# ---------------------------------------------------------------------------
# Property 3: Positions and orders dict-to-list transformation
# ---------------------------------------------------------------------------


def _direction_value():
    """Generate a direction value: either a plain string or an __enum__ marker."""
    plain = st.sampled_from(["Direction.LONG", "Direction.SHORT", "LONG", "SHORT"])
    enum_marker = st.builds(
        lambda v: {"__enum__": v},
        v=st.sampled_from(["Direction.LONG", "Direction.SHORT"]),
    )
    return st.one_of(plain, enum_marker)


def _offset_value():
    """Generate an offset value: either a plain string or an __enum__ marker."""
    plain = st.sampled_from(["Offset.OPEN", "Offset.CLOSE", "OPEN", "CLOSE"])
    enum_marker = st.builds(
        lambda v: {"__enum__": v},
        v=st.sampled_from(["Offset.OPEN", "Offset.CLOSE"]),
    )
    return st.one_of(plain, enum_marker)


def _status_value():
    """Generate a status value: either a plain string or an __enum__ marker."""
    plain = st.sampled_from(
        ["Status.SUBMITTING", "Status.NOTTRADED", "Status.ALLTRADED", "Status.CANCELLED"]
    )
    enum_marker = st.builds(
        lambda v: {"__enum__": v},
        v=st.sampled_from(
            ["Status.SUBMITTING", "Status.NOTTRADED", "Status.ALLTRADED", "Status.CANCELLED"]
        ),
    )
    return st.one_of(plain, enum_marker)


def _position_entry():
    """Generate a single position data dict."""
    return st.fixed_dictionaries(
        {
            "vt_symbol": st.text(
                alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789."),
                min_size=3,
                max_size=20,
            ),
            "direction": _direction_value(),
            "volume": st.one_of(
                st.integers(min_value=0, max_value=10000),
                st.floats(
                    allow_nan=False, allow_infinity=False, min_value=0, max_value=10000
                ),
            ),
            "open_price": st.floats(
                allow_nan=False, allow_infinity=False, min_value=0, max_value=1e6
            ),
            "pnl": st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
        }
    )


def _positions_dict():
    """Generate a positions dictionary {key: position_data}."""
    return st.dictionaries(
        keys=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789._"),
            min_size=1,
            max_size=20,
        ),
        values=_position_entry(),
        min_size=0,
        max_size=10,
    )


def _order_entry():
    """Generate a single order data dict."""
    return st.fixed_dictionaries(
        {
            "vt_orderid": st.text(
                alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789._"),
                min_size=1,
                max_size=20,
            ),
            "vt_symbol": st.text(
                alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789."),
                min_size=3,
                max_size=20,
            ),
            "direction": _direction_value(),
            "offset": _offset_value(),
            "volume": st.one_of(
                st.integers(min_value=0, max_value=10000),
                st.floats(
                    allow_nan=False, allow_infinity=False, min_value=0, max_value=10000
                ),
            ),
            "price": st.floats(
                allow_nan=False, allow_infinity=False, min_value=0, max_value=1e6
            ),
            "status": _status_value(),
        }
    )


def _orders_dict():
    """Generate a pending_orders dictionary {key: order_data}."""
    return st.dictionaries(
        keys=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789._"),
            min_size=1,
            max_size=20,
        ),
        values=_order_entry(),
        min_size=0,
        max_size=10,
    )


POSITION_REQUIRED_FIELDS = {"vt_symbol", "direction", "volume", "price", "pnl"}
ORDER_REQUIRED_FIELDS = {
    "vt_orderid",
    "vt_symbol",
    "direction",
    "offset",
    "volume",
    "price",
    "status",
}


class TestPositionsOrdersTransformProperty:
    """Property 3: Positions and orders dict-to-list transformation

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    """

    @given(positions=_positions_dict())
    @settings(max_examples=100)
    def test_transform_positions_length_and_fields(self, positions):
        """transform_positions SHALL produce a list whose length equals the number
        of entries in the input dict, and each item SHALL contain the required fields."""
        position_aggregate = {"positions": positions}
        result = SnapshotJsonTransformer.transform_positions(position_aggregate)

        assert len(result) == len(positions), (
            f"Expected {len(positions)} positions, got {len(result)}"
        )

        for item in result:
            missing = POSITION_REQUIRED_FIELDS - set(item.keys())
            assert not missing, f"Position item missing fields: {missing}"

    @given(orders=_orders_dict())
    @settings(max_examples=100)
    def test_transform_orders_length_and_fields(self, orders):
        """transform_orders SHALL produce a list whose length equals the number
        of entries in the input dict, and each item SHALL contain the required fields."""
        position_aggregate = {"pending_orders": orders}
        result = SnapshotJsonTransformer.transform_orders(position_aggregate)

        assert len(result) == len(orders), (
            f"Expected {len(orders)} orders, got {len(result)}"
        )

        for item in result:
            missing = ORDER_REQUIRED_FIELDS - set(item.keys())
            assert not missing, f"Order item missing fields: {missing}"


# ---------------------------------------------------------------------------
# Property 4: Full snapshot transform produces all required Frontend_Format fields
# ---------------------------------------------------------------------------

import re as _re


def _datetime_marker_for_snapshot():
    """Generate a __datetime__ marker with a valid ISO datetime string for current_dt."""
    return st.builds(
        lambda y, mo, d, h, mi, s: {
            "__datetime__": f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}"
        },
        y=st.integers(min_value=2000, max_value=2030),
        mo=st.integers(min_value=1, max_value=12),
        d=st.integers(min_value=1, max_value=28),
        h=st.integers(min_value=0, max_value=23),
        mi=st.integers(min_value=0, max_value=59),
        s=st.integers(min_value=0, max_value=59),
    )


def _vt_symbol():
    """Generate a vt_symbol like 'rb2501.SHFE'."""
    prefix = st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
        min_size=1,
        max_size=4,
    )
    digits = st.text(
        alphabet=st.sampled_from("0123456789"),
        min_size=3,
        max_size=4,
    )
    exchange = st.sampled_from(["SHFE", "DCE", "CZCE", "CFFEX", "INE"])
    return st.builds(lambda p, d, e: f"{p}{d}.{e}", p=prefix, d=digits, e=exchange)


def _instrument_with_bars():
    """Generate an instrument entry with non-empty bars (at least one record)."""
    records = st.lists(_bar_record(), min_size=1, max_size=5)
    return st.builds(
        lambda recs: {"bars": {"__dataframe__": True, "records": recs}},
        recs=records,
    )


def _target_aggregate():
    """Generate a target_aggregate with at least one instrument with non-empty bars."""
    instruments = st.dictionaries(
        keys=_vt_symbol(),
        values=_instrument_with_bars(),
        min_size=1,
        max_size=3,
    )
    return st.builds(lambda insts: {"instruments": insts}, insts=instruments)


def _position_aggregate():
    """Generate a position_aggregate with positions and pending_orders dicts."""
    return st.builds(
        lambda pos, ords: {"positions": pos, "pending_orders": ords},
        pos=_positions_dict(),
        ords=_orders_dict(),
    )


def _strategy_name():
    """Generate a random strategy name string."""
    return st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
        min_size=1,
        max_size=20,
    )


def _valid_snapshot():
    """Generate a valid snapshot_json dict with current_dt, target_aggregate, position_aggregate."""
    return st.builds(
        lambda dt, ta, pa: {
            "current_dt": dt,
            "target_aggregate": ta,
            "position_aggregate": pa,
        },
        dt=_datetime_marker_for_snapshot(),
        ta=_target_aggregate(),
        pa=_position_aggregate(),
    )


_TIMESTAMP_PATTERN = _re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_EXPECTED_KEYS = {"timestamp", "variant", "instruments", "positions", "orders"}


class TestFullSnapshotTransformProperty:
    """Property 4: Full snapshot transform produces all required Frontend_Format fields

    **Validates: Requirements 2.2, 2.3, 3.1**
    """

    @given(snapshot=_valid_snapshot(), name=_strategy_name())
    @settings(max_examples=100)
    def test_transform_produces_all_required_fields(self, snapshot, name):
        """For any valid snapshot_json, calling transform SHALL produce a dict
        containing exactly the keys timestamp, variant, instruments, positions, orders,
        where variant equals the input strategy_name and timestamp matches YYYY-MM-DD HH:MM:SS."""
        result = SnapshotJsonTransformer.transform(snapshot, name)

        # Exactly the required keys
        assert set(result.keys()) == _EXPECTED_KEYS, (
            f"Expected keys {_EXPECTED_KEYS}, got {set(result.keys())}"
        )

        # variant equals strategy_name
        assert result["variant"] == name, (
            f"Expected variant={name!r}, got {result['variant']!r}"
        )

        # timestamp matches YYYY-MM-DD HH:MM:SS
        assert _TIMESTAMP_PATTERN.match(result["timestamp"]), (
            f"Timestamp {result['timestamp']!r} does not match YYYY-MM-DD HH:MM:SS"
        )

        # instruments is a dict
        assert isinstance(result["instruments"], dict), (
            f"Expected instruments to be dict, got {type(result['instruments'])}"
        )

        # positions is a list
        assert isinstance(result["positions"], list), (
            f"Expected positions to be list, got {type(result['positions'])}"
        )

        # orders is a list
        assert isinstance(result["orders"], list), (
            f"Expected orders to be list, got {type(result['orders'])}"
        )
