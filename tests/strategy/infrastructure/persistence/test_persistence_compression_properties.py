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
    COMPRESSION_PREFIX,
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


# ===========================================================================
# Unit Tests for Boundary Conditions
# ===========================================================================

class TestStateRepositoryCompressionBoundaryConditions:
    """Unit tests for compression boundary conditions.
    
    Validates: Requirements 3.4
    
    These tests verify specific edge cases and boundary conditions:
    1. Compressed data larger than original → keep original uncompressed
    2. Empty strings and strings below threshold → no compression
    3. ZLIB: prefix detection works correctly
    """

    def test_compressed_data_larger_than_original_keeps_original(self):
        """
        **Validates: Requirements 3.4**
        
        When compressed data is larger than the original data, the repository
        should keep the original uncompressed data instead.
        
        This can happen with small, already-compressed, or random data that
        doesn't compress well.
        """
        repository = _make_repository()
        
        # Create a JSON string that doesn't compress well
        # Random-looking data with high entropy
        json_str = json.dumps({
            "data": "x" * 15000  # Repetitive data that compresses well
        })
        
        # First verify this data DOES compress well (sanity check)
        stored_1, was_compressed_1 = repository._maybe_compress(json_str)
        assert was_compressed_1, "Test setup failed: data should compress well"
        
        # Now test with data that doesn't compress well
        # Use a string of random hex characters (high entropy)
        import random
        random_hex = ''.join(random.choice('0123456789abcdef') for _ in range(15000))
        json_str_random = json.dumps({"data": random_hex})
        
        stored_2, was_compressed_2 = repository._maybe_compress(json_str_random)
        
        # If compression made it larger, should keep original
        if not was_compressed_2:
            # Verify the stored data is the original
            assert stored_2 == json_str_random
            assert not stored_2.startswith(COMPRESSION_PREFIX)
        else:
            # If it did compress, verify it's actually smaller
            assert len(stored_2) < len(json_str_random)

    def test_empty_string_not_compressed(self):
        """
        **Validates: Requirements 3.4**
        
        Empty strings should not be compressed.
        """
        repository = _make_repository()
        
        json_str = ""
        stored, was_compressed = repository._maybe_compress(json_str)
        
        assert not was_compressed, "Empty string should not be compressed"
        assert stored == json_str, "Empty string should be returned as-is"
        assert not stored.startswith(COMPRESSION_PREFIX)

    def test_small_string_below_threshold_not_compressed(self):
        """
        **Validates: Requirements 3.4**
        
        Strings smaller than the compression threshold (10KB) should not be
        compressed, regardless of their content.
        """
        repository = _make_repository()
        
        # Create a small JSON string (well below 10KB threshold)
        small_json = json.dumps({
            "id": 123,
            "name": "test",
            "values": [1, 2, 3, 4, 5]
        })
        
        assert len(small_json.encode('utf-8')) < DEFAULT_COMPRESSION_THRESHOLD
        
        stored, was_compressed = repository._maybe_compress(small_json)
        
        assert not was_compressed, "Small string should not be compressed"
        assert stored == small_json, "Small string should be returned as-is"
        assert not stored.startswith(COMPRESSION_PREFIX)

    def test_string_at_threshold_boundary_not_compressed(self):
        """
        **Validates: Requirements 3.4**
        
        Strings exactly at the threshold should not be compressed (threshold
        is exclusive: compress only if > threshold).
        """
        repository = _make_repository()
        
        # Create a JSON string exactly at the threshold
        # Adjust content to hit exactly 10KB
        target_size = DEFAULT_COMPRESSION_THRESHOLD
        base_json = {"data": ""}
        base_size = len(json.dumps(base_json).encode('utf-8'))
        padding_needed = target_size - base_size
        
        json_str = json.dumps({"data": "x" * padding_needed})
        actual_size = len(json_str.encode('utf-8'))
        
        # Adjust if needed to hit exactly the threshold
        while actual_size < target_size:
            padding_needed += 1
            json_str = json.dumps({"data": "x" * padding_needed})
            actual_size = len(json_str.encode('utf-8'))
        
        while actual_size > target_size:
            padding_needed -= 1
            json_str = json.dumps({"data": "x" * padding_needed})
            actual_size = len(json_str.encode('utf-8'))
        
        assert actual_size == target_size, f"Expected {target_size}, got {actual_size}"
        
        stored, was_compressed = repository._maybe_compress(json_str)
        
        assert not was_compressed, "String at threshold should not be compressed"
        assert stored == json_str

    def test_string_just_above_threshold_is_compressed(self):
        """
        **Validates: Requirements 3.4**
        
        Strings just above the threshold should be compressed (if compression
        actually reduces size).
        """
        repository = _make_repository()
        
        # Create a JSON string just above the threshold with compressible content
        target_size = DEFAULT_COMPRESSION_THRESHOLD + 100
        json_str = json.dumps({"data": "x" * target_size})
        
        assert len(json_str.encode('utf-8')) > DEFAULT_COMPRESSION_THRESHOLD
        
        stored, was_compressed = repository._maybe_compress(json_str)
        
        # Repetitive data should compress well
        assert was_compressed, "Large compressible string should be compressed"
        assert stored.startswith(COMPRESSION_PREFIX)
        assert len(stored) < len(json_str), "Compressed data should be smaller"

    def test_zlib_prefix_detection_for_compressed_data(self):
        """
        **Validates: Requirements 3.4**
        
        The ZLIB: prefix should be correctly detected and used for compressed
        data.
        """
        repository = _make_repository()
        
        # Create a large compressible JSON string
        json_str = json.dumps({"data": "x" * 15000})
        
        stored, was_compressed = repository._maybe_compress(json_str)
        
        if was_compressed:
            # Verify prefix is present
            assert stored.startswith(COMPRESSION_PREFIX), (
                "Compressed data should have ZLIB: prefix"
            )
            
            # Verify decompression works
            restored = repository._maybe_decompress(stored)
            assert restored == json_str
            
            # Verify the prefix is exactly "ZLIB:"
            assert stored[:5] == "ZLIB:"
            
            # Verify the rest is valid base64
            import base64
            try:
                base64.b64decode(stored[5:])
            except Exception as e:
                pytest.fail(f"Data after ZLIB: prefix is not valid base64: {e}")

    def test_zlib_prefix_detection_for_uncompressed_data(self):
        """
        **Validates: Requirements 3.4**
        
        Uncompressed data should not have the ZLIB: prefix, and decompression
        should return it as-is.
        """
        repository = _make_repository()
        
        # Create a small JSON string (won't be compressed)
        json_str = json.dumps({"id": 123, "name": "test"})
        
        stored, was_compressed = repository._maybe_compress(json_str)
        
        assert not was_compressed
        assert not stored.startswith(COMPRESSION_PREFIX), (
            "Uncompressed data should not have ZLIB: prefix"
        )
        
        # Decompression should return it as-is
        restored = repository._maybe_decompress(stored)
        assert restored == json_str
        assert restored == stored

    def test_manual_zlib_prefix_in_data_is_handled_correctly(self):
        """
        **Validates: Requirements 3.4**
        
        If the original JSON data happens to start with "ZLIB:", the system
        should handle it correctly (this is an edge case but worth testing).
        """
        repository = _make_repository()
        
        # Create JSON that starts with "ZLIB:" in its content
        json_str = json.dumps({"message": "ZLIB: this is not compressed"})
        
        # This is small, so won't be compressed
        stored, was_compressed = repository._maybe_compress(json_str)
        
        assert not was_compressed
        # The stored data should be the original JSON
        assert stored == json_str
        
        # Decompression should handle this correctly
        # Since the data doesn't start with "ZLIB:" at the storage level,
        # it should be returned as-is
        restored = repository._maybe_decompress(stored)
        assert restored == json_str
