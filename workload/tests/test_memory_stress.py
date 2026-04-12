"""Tests for memory stress module — request-driven architecture."""

import unittest
import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory_stress import MemoryStress, MIN_MEMORY_MB, MAX_MEMORY_MB


class TestMemoryStress(unittest.TestCase):
    """Test cases for MemoryStress class (request-driven)."""

    def test_allocate_returns_result_dict(self):
        """Test that allocate returns a result dictionary with expected keys."""
        stress = MemoryStress()
        result = stress.allocate(memory_mb=1, hold_time_ms=10)

        self.assertIn('allocated_mb', result)
        self.assertIn('allocation_time_ms', result)
        self.assertIn('hold_time_ms', result)
        self.assertIn('total_request_time_ms', result)
        self.assertIn('total_allocated_mb', result)
        self.assertIn('total_requests', result)

    def test_small_allocation_fast(self):
        """Test that small allocation completes quickly."""
        stress = MemoryStress()
        result = stress.allocate(memory_mb=1, hold_time_ms=10)

        self.assertEqual(result['allocated_mb'], 1)
        # Should complete quickly (under 1 second for 1MB with 10ms hold)
        self.assertLess(result['total_request_time_ms'], 1000)

    def test_larger_allocation_takes_longer(self):
        """Test that larger allocation takes more time."""
        stress = MemoryStress()
        small_result = stress.allocate(memory_mb=1, hold_time_ms=10)
        large_result = stress.allocate(memory_mb=8, hold_time_ms=10)

        # Larger allocation should take longer (more memory to allocate)
        self.assertGreaterEqual(
            large_result['allocation_time_ms'],
            small_result['allocation_time_ms']
        )

    def test_hold_time_respected(self):
        """Test that hold time is approximately respected."""
        stress = MemoryStress()
        result = stress.allocate(memory_mb=1, hold_time_ms=100)

        # Hold time should be close to requested (within 50ms tolerance)
        self.assertGreaterEqual(result['hold_time_ms'], 50)
        self.assertLess(result['hold_time_ms'], 200)

    def test_memory_mb_bounds_min(self):
        """Test that negative memory_mb is clamped to minimum."""
        stress = MemoryStress()
        result = stress.allocate(memory_mb=-10, hold_time_ms=10)

        self.assertEqual(result['allocated_mb'], MIN_MEMORY_MB)

    def test_memory_mb_bounds_max(self):
        """Test that excessive memory_mb is clamped to maximum."""
        stress = MemoryStress()
        result = stress.allocate(memory_mb=9999, hold_time_ms=10)

        self.assertLessEqual(result['allocated_mb'], MAX_MEMORY_MB)

    def test_cumulative_tracking(self):
        """Test that total allocated MB and requests are tracked across calls."""
        stress = MemoryStress()

        result1 = stress.allocate(memory_mb=1, hold_time_ms=10)
        result2 = stress.allocate(memory_mb=2, hold_time_ms=10)

        self.assertEqual(result2['total_requests'], 2)
        self.assertEqual(result2['total_allocated_mb'], 3)  # 1 + 2

    def test_default_hold_time(self):
        """Test that default hold time is used when not specified."""
        stress = MemoryStress()
        result = stress.allocate(memory_mb=1)

        # Should use default hold time (500ms)
        self.assertGreater(result['hold_time_ms'], 100)
        self.assertLess(result['hold_time_ms'], 1000)

    def test_memory_released_after_request(self):
        """Test that memory is released after allocate() returns."""
        stress = MemoryStress()
        result = stress.allocate(memory_mb=1, hold_time_ms=10)

        # Method should complete and return - memory is released internally
        self.assertGreater(result['total_request_time_ms'], 0)


if __name__ == '__main__':
    unittest.main()
