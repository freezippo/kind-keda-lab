"""Tests for CPU stress module — request-driven architecture."""

import unittest
import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cpu_stress import CPUStress


class TestCPUStress(unittest.TestCase):
    """Test cases for CPUStress class (request-driven)."""

    def setUp(self):
        """Set up test fixtures."""
        self.stress = CPUStress()

    def test_execute_returns_result_dict(self):
        """Test that execute returns a result dictionary with expected keys."""
        result = self.stress.execute(load_intensity=10)

        self.assertIn('operations', result)
        self.assertIn('computation_time_ms', result)
        self.assertIn('result', result)
        self.assertIn('total_operations', result)
        self.assertIn('total_computation_time_ms', result)

    def test_low_load_intensity_faster(self):
        """Test that low load intensity completes faster than high intensity."""
        low_result = self.stress.execute(load_intensity=10)
        high_result = self.stress.execute(load_intensity=90)

        # High intensity should take longer
        self.assertGreater(
            high_result['computation_time_ms'],
            low_result['computation_time_ms']
        )

    def test_high_load_intensity_more_operations(self):
        """Test that high load intensity performs more operations."""
        low_result = self.stress.execute(load_intensity=10)
        high_result = self.stress.execute(load_intensity=90)

        self.assertGreater(
            high_result['operations'],
            low_result['operations']
        )

    def test_default_load_intensity(self):
        """Test default load intensity (50) produces reasonable results."""
        result = self.stress.execute()

        self.assertGreater(result['operations'], 0)
        self.assertGreater(result['computation_time_ms'], 0)

    def test_intensity_bounds_min(self):
        """Test that negative intensity is clamped to minimum."""
        result_negative = self.stress.execute(load_intensity=-10)
        result_min = self.stress.execute(load_intensity=1)

        # Both should produce similar (minimum) work
        self.assertEqual(result_negative['operations'], result_min['operations'])

    def test_intensity_bounds_max(self):
        """Test that excessive intensity is clamped to maximum."""
        result_high = self.stress.execute(load_intensity=150)
        result_max = self.stress.execute(load_intensity=100)

        # Both should produce same (maximum) work
        self.assertEqual(result_high['operations'], result_max['operations'])

    def test_cumulative_tracking(self):
        """Test that total operations and time are tracked across calls."""
        stress = CPUStress()

        result1 = stress.execute(load_intensity=10)
        result2 = stress.execute(load_intensity=10)

        self.assertEqual(
            result2['total_operations'],
            result1['operations'] * 2
        )
        self.assertGreater(result2['total_computation_time_ms'], result1['computation_time_ms'])

    def test_computation_time_is_realistic(self):
        """Test that computation time is measurable and realistic."""
        result = self.stress.execute(load_intensity=50)

        # Should complete in reasonable time (< 5 seconds for any intensity)
        self.assertLess(result['computation_time_ms'], 5000)
        # Should take some measurable time (> 0)
        self.assertGreater(result['computation_time_ms'], 0)

    def test_result_is_deterministic_for_same_intensity(self):
        """Test that same intensity produces same number of operations."""
        result1 = self.stress.execute(load_intensity=50)
        result2 = self.stress.execute(load_intensity=50)

        self.assertEqual(result1['operations'], result2['operations'])


if __name__ == '__main__':
    unittest.main()
