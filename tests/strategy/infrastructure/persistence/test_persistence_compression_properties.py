"""
Property-Based Tests for StateRepository Compression - Data Persistence Optimization

Feature: data-persistence-optimization, Property 6: 压缩往返一致性

Validates: Requirements 3.1, 3.2, 3.5
"""

import json
import sys
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st

# Mock vnpy modules before importing database_factory (avoids __init__.py chain)
for _mod_name in [
    "vnpy", "vnpy.event", "vnpy.trader", "vnpy.trader.setting",
    "vnpy.trader.engine", "vnpy.trader.database", "vnpy_mysql",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Ensure SETTINGS is a real dict for tests
sys.modules["vnpy.trader.setting"].SETTINGS = {}

from src.strategy.infrastructure.persistence.json_serializer import JsonSerializer
from src.strategy.infrastructure.persistence.migration_chain import MigrationChain
from src.strategy.infrastructure.persistence.state_repository import (
    DEFAULT_COMPRESSION_THRESHOLD,
    StateRepository,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def _json_string_strategy():
    """Generate random JSON strings with varying lengths.
    
    This strategy generates JSON strings that:
    - Are below the compression threshold (< 10KB)
    - Are above the compression threshold (> 10KB)
    - Contain various JSON structures (objects, arrays, nested data)
    
    This ensures we test both compressed and uncompressed code paths.
    """
    # Small JSON strings (below threshold)
    small_json = st.builds(
        lambda d: json.dumps(d, ensure_ascii=False),
        st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.text(max_size=100),
                st.booleans(),
                st.none(),
            ),
            min_size=1,
            max_size=50,
        ),
    )
    
    # Large JSON strings (above threshold, ~15-30KB)
    large_json = st.builds(
        lambda items: json.dumps({"data": items}, ensure_ascii=False),
        st.lists(
            st.fixed_dictionaries({
                "id": st.integers(min_value=0, max_value=1_000_000),
                "name": st.text(min_size=10, max_size=100),
                "description": st.text(min_size=50, max_size=500),
                "values": st.lists(
                    st.floats(allow_nan=False, allow_infinity=False),
                    min_size=10,
                    max_size=50,
                ),
                "metadata": st.dictionaries(
                    keys=st.text(min_size=5, max_size=20),
                    values=st.text(min_size=10, max_size=100),
                    min_size=5,
                    max_size=20,
                ),
            }),
            min_size=20,
            max_size=100,
        ),
    )
    
    # Mix of small and large JSON strings
    return st.one_of(small_json, large_json)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repository() -> StateRepository:
    """Create a StateRepository instance for testing compression methods.
    
    Note: We only test the compression/decompression methods, not the full
    save/load cycle which requires database setup.
    """
    serializer = JsonSerializer(MigrationChain())
    # Use a mock database factory since we're only testing compression methods
    database_factory = None  # type: ignore
    logger = None
    
    return StateRepository(
        serializer=serializer,
        database_factory=database_factory,  # type: ignore
        logger=logger,
        compression_threshold=DEFAULT_COMPRESSION_THRESHOLD,
    )


# ===========================================================================
# Property-Based Tests
# ===========================================================================

class TestStateRepositoryCompressionRoundTripProperties:
    """Property 6: 压缩往返一致性
    
    Feature: data-persistence-optimization, Property 6: 压缩往返一致性
    Validates: Requirements 3.1, 3.2, 3.5
    """

    @settings(max_examples=100, deadline=None)
    @given(json_str=_json_string_strategy())
    def test_property_6_compression_round_trip_consistency(
        self, json_str: str
    ):
        """
        **Validates: Requirements 3.1, 3.2, 3.5**
        
        Property 6: 压缩往返一致性
        
        For any valid JSON string, after StateRepository._maybe_compress() 
        followed by StateRepository._maybe_decompress(), the result should be 
        exactly identical to the original JSON string. This ensures compression 
        is lossless.
        
        This property tests both code paths:
        1. Small JSON strings (< 10KB): No compression, direct pass-through
        2. Large JSON strings (> 10KB): zlib compression + base64 encoding
        
        In both cases, the round-trip must preserve the exact original string.
        """
        repository = _make_repository()

        # Compress the JSON string (may or may not actually compress)
        stored_data, was_compressed = repository._maybe_compress(json_str)
        
        # Decompress the stored data
        restored_json = repository._maybe_decompress(stored_data)

        # The restored JSON must be byte-for-byte identical to the original
        assert restored_json == json_str, (
            f"Compression round-trip failed to preserve original JSON string.\n"
            f"Original length: {len(json_str)} bytes\n"
            f"Was compressed: {was_compressed}\n"
            f"Stored data length: {len(stored_data)} bytes\n"
            f"Restored length: {len(restored_json)} bytes\n"
            f"Original (first 200 chars): {json_str[:200]}\n"
            f"Restored (first 200 chars): {restored_json[:200]}"
        )
        
        # Verify byte-level equality
        assert restored_json.encode('utf-8') == json_str.encode('utf-8'), (
            "Restored JSON is string-equal but not byte-equal to original"
        )
        
        # Verify the restored JSON is still valid JSON
        try:
            json.loads(restored_json)
        except json.JSONDecodeError as e:
            pytest.fail(
                f"Restored JSON is not valid JSON after round-trip:\n"
                f"Error: {e}\n"
                f"Restored JSON (first 500 chars): {restored_json[:500]}"
            )

    @settings(max_examples=50, deadline=None)
    @given(json_str=_json_string_strategy())
    def test_compression_idempotency(self, json_str: str):
        """
        Additional property: Compression is idempotent.
        
        Compressing and decompressing multiple times should always yield the 
        same result as doing it once. This verifies the compression logic is 
        stable and doesn't introduce artifacts.
        """
        repository = _make_repository()

        # First round-trip
        stored_1, _ = repository._maybe_compress(json_str)
        restored_1 = repository._maybe_decompress(stored_1)
        
        # Second round-trip on the restored data
        stored_2, _ = repository._maybe_compress(restored_1)
        restored_2 = repository._maybe_decompress(stored_2)

        # Both restored versions must be identical to the original
        assert restored_1 == json_str
        assert restored_2 == json_str
        
        # The stored formats should also be identical
        assert stored_1 == stored_2, (
            "Compression is not idempotent: compressing the same data twice "
            "produced different stored formats"
        )
