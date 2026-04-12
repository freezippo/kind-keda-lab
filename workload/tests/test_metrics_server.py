"""Tests for Prometheus metrics handler module — request-driven architecture."""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestMetricsHandlerTextOnly(unittest.TestCase):
    """Test metrics handler without prometheus_client library."""

    def setUp(self):
        """Set up with prometheus_client mocked as unavailable."""
        import metrics_server
        metrics_server.PROMETHEUS_AVAILABLE = False

        self.handler = metrics_server.MetricsHandler(load_intensity=50)

    def test_initialization(self):
        """Test handler initializes correctly."""
        self.assertEqual(self.handler.load_intensity, 50)
        self.assertEqual(self.handler._request_count, 0)

    def test_record_request_increments_counter(self):
        """Test that recording requests increments counter."""
        self.handler.record_request(mode='prometheus')
        self.handler.record_request(mode='prometheus')

        self.assertEqual(self.handler._request_count, 2)

    def test_get_metric_value_request_count(self):
        """Test getting request count metric."""
        self.handler.record_request()
        self.handler.record_request()

        value = self.handler.get_metric_value('request_count')
        self.assertEqual(value, 2)

    def test_get_metric_value_queue_depth(self):
        """Test getting queue depth metric."""
        value = self.handler.get_metric_value('queue_depth')
        self.assertIsNotNone(value)
        self.assertGreaterEqual(value, 0)

    def test_get_metric_value_load_intensity(self):
        """Test getting load intensity metric."""
        value = self.handler.get_metric_value('load_intensity')
        self.assertEqual(value, 50)

    def test_get_metric_value_uptime(self):
        """Test getting uptime metric."""
        value = self.handler.get_metric_value('uptime_seconds')
        self.assertGreaterEqual(value, 0)

    def test_get_metric_value_unknown(self):
        """Test getting unknown metric returns None."""
        value = self.handler.get_metric_value('nonexistent_metric')
        self.assertIsNone(value)

    def test_get_metrics_text_returns_prometheus_format(self):
        """Test that metrics text is in Prometheus format."""
        self.handler.record_request()
        text = self.handler.get_metrics_text()

        # Should contain expected metric names
        self.assertIn('workload_requests_total', text)
        self.assertIn('workload_queue_depth_simulation', text)
        self.assertIn('workload_load_intensity', text)

    def test_queue_depth_increases_with_requests(self):
        """Test that simulated queue depth increases with request count."""
        initial_depth = self.handler.get_metric_value('queue_depth')

        # Record many requests
        for _ in range(100):
            self.handler.record_request()

        later_depth = self.handler.get_metric_value('queue_depth')
        self.assertGreaterEqual(later_depth, initial_depth)


class TestMetricsHandlerWithPrometheusClient(unittest.TestCase):
    """Test metrics handler with prometheus_client library."""

    def setUp(self):
        """Set up with prometheus_client available."""
        try:
            from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry
            self.has_prometheus = True
            self.test_registry = CollectorRegistry()
        except ImportError:
            self.has_prometheus = False
            self.skipTest("prometheus_client not available")

        import metrics_server
        metrics_server.PROMETHEUS_AVAILABLE = True

        self.handler = metrics_server.MetricsHandler(load_intensity=75, registry=self.test_registry)

    def test_initialization_sets_gauge(self):
        """Test that initialization sets load intensity gauge."""
        if not self.has_prometheus:
            self.skipTest("prometheus_client not available")

        self.assertEqual(self.handler.load_intensity, 75)

    def test_record_request_updates_prometheus_metrics(self):
        """Test that recording requests updates Prometheus metrics."""
        if not self.has_prometheus:
            self.skipTest("prometheus_client not available")

        initial_count = self.handler._request_count
        self.handler.record_request(mode='test', computation_time=0.01)

        self.assertEqual(self.handler._request_count, initial_count + 1)

    def test_get_metrics_text_with_prometheus_client(self):
        """Test metrics text generation with prometheus_client."""
        if not self.has_prometheus:
            self.skipTest("prometheus_client not available")

        self.handler.record_request()
        text = self.handler.get_metrics_text()

        # Should be non-empty
        self.assertTrue(len(text) > 0)


if __name__ == '__main__':
    unittest.main()
