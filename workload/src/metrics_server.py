#!/usr/bin/env python3
"""
Prometheus Metrics Handler Module — Request-Driven

Exposes Prometheus-format metrics and simulates custom metrics that can be
queried by KEDA's Prometheus scaler. The metrics endpoint is accessed via
HTTP GET /metrics on the main workload server.

This module provides both the metrics generation and a simulation of
variable load that can trigger KEDA scaling.
"""

import time
import random
import logging
import math

logger = logging.getLogger('metrics_server')

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed, metrics will be text-only")


class MetricsHandler:
    """Generates Prometheus-format metrics for KEDA Prometheus scaler."""

    def __init__(self, load_intensity=50, registry=None):
        """Initialize metrics handler.

        Args:
            load_intensity: Base load intensity for metric simulation (1-100).
            registry: Optional Prometheus registry (uses default registry if None).
        """
        self.load_intensity = load_intensity
        self._request_count = 0
        self._start_time = time.time()
        self._registry = registry

        if PROMETHEUS_AVAILABLE:
            # Use provided registry or default
            reg = self._registry
            if reg is None:
                from prometheus_client import REGISTRY
                reg = REGISTRY

            # Define Prometheus metrics
            self.workload_requests_total = Counter(
                'workload_requests_total',
                'Total number of HTTP requests processed',
                ['mode'],
                registry=reg
            )
            self.active_requests = Gauge(
                'workload_active_requests',
                'Number of currently active requests',
                registry=reg
            )
            self.queue_depth_simulation = Gauge(
                'workload_queue_depth_simulation',
                'Simulated queue depth for KEDA Prometheus scaling demo',
                registry=reg
            )
            self.computation_time_seconds = Histogram(
                'workload_computation_time_seconds',
                'Time spent on computation per request',
                registry=reg
            )
            self.load_intensity_gauge = Gauge(
                'workload_load_intensity',
                'Current load intensity setting',
                registry=reg
            )

            # Set initial values
            self.load_intensity_gauge.set(load_intensity)
        else:
            # Text-only fallback metrics
            self._metrics_text = ""

        logger.info(f"MetricsHandler initialized (request-driven mode), intensity={load_intensity}")

    def record_request(self, mode='prometheus', computation_time=0):
        """Record a request in the metrics.

        Args:
            mode: Request mode label.
            computation_time: Time spent on computation in seconds.
        """
        self._request_count += 1

        if PROMETHEUS_AVAILABLE:
            self.workload_requests_total.labels(mode=mode).inc()
            if computation_time > 0:
                self.computation_time_seconds.observe(computation_time)
            # Update simulated queue depth based on request count and intensity
            queue_depth = self._calculate_simulated_queue_depth()
            self.queue_depth_simulation.set(queue_depth)

    def _calculate_simulated_queue_depth(self):
        """Calculate simulated queue depth based on request patterns.

        Returns a value that increases with request count and load intensity,
        suitable for triggering KEDA Prometheus scaling.

        Returns:
            float: Simulated queue depth value.
        """
        # Base depth increases with request count
        base_depth = self._request_count * (self.load_intensity / 50.0)

        # Add some realistic variation
        variation = random.uniform(-5, 5)

        # Simulate slow drain (queue doesn't grow forever)
        drain_factor = max(0, 1 - (time.time() - self._start_time) / 3600)

        depth = max(0, base_depth * drain_factor + variation)
        return round(depth, 2)

    def get_metrics_text(self):
        """Get metrics in Prometheus text exposition format.

        Returns:
            str: Metrics in Prometheus format.
        """
        if PROMETHEUS_AVAILABLE:
            return generate_latest().decode('utf-8')
        else:
            return self._get_text_metrics()

    def _get_text_metrics(self):
        """Generate text-only metrics when prometheus_client is not available.

        Returns:
            str: Metrics in approximate Prometheus format.
        """
        queue_depth = self._calculate_simulated_queue_depth()

        return f"""# HELP workload_requests_total Total number of HTTP requests processed
# TYPE workload_requests_total counter
workload_requests_total{{mode="prometheus"}} {self._request_count}
# HELP workload_active_requests Number of currently active requests
# TYPE workload_active_requests gauge
workload_active_requests 1
# HELP workload_queue_depth_simulation Simulated queue depth for KEDA Prometheus scaling demo
# TYPE workload_queue_depth_simulation gauge
workload_queue_depth_simulation {queue_depth}
# HELP workload_load_intensity Current load intensity setting
# TYPE workload_load_intensity gauge
workload_load_intensity {self.load_intensity}
"""

    def get_metric_value(self, metric_name):
        """Get current value of a specific metric (for debugging/testing).

        Args:
            metric_name: Name of the metric to retrieve.

        Returns:
            float or int: Current metric value.
        """
        if metric_name == 'request_count':
            return self._request_count
        elif metric_name == 'queue_depth':
            return self._calculate_simulated_queue_depth()
        elif metric_name == 'load_intensity':
            return self.load_intensity
        elif metric_name == 'uptime_seconds':
            return time.time() - self._start_time
        else:
            return None


# Standalone entry point for testing
if __name__ == '__main__':
    import os
    logging.basicConfig(level=logging.INFO)
    handler = MetricsHandler(
        load_intensity=int(os.environ.get('LOAD_INTENSITY', '50'))
    )

    # Simulate some requests
    for i in range(10):
        handler.record_request(mode='prometheus', computation_time=0.01)
        print(handler.get_metrics_text())
        time.sleep(0.1)
