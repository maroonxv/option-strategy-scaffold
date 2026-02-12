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
