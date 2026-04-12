#!/usr/bin/env python3
"""
CPU Stress Workload Module — Request-Driven

Generates CPU-intensive computation per HTTP request. Each request triggers
a configurable amount of CPU work proportional to the load intensity parameter.

This module is designed to be called by the main HTTP server — it does NOT
run its own server. Each execute() call performs CPU work and returns results.
"""

import time
import logging
import math

logger = logging.getLogger('cpu_stress')


class CPUStress:
    """Generates CPU-intensive computation on demand per HTTP request."""

    def __init__(self):
        """Initialize CPU stress handler."""
        self._total_operations = 0
        self._total_computation_time = 0.0
        logger.info("CPUStress handler initialized (request-driven mode)")

    def _compute_intensive(self, iterations):
        """Perform CPU-intensive computation.

        Args:
            iterations: Number of iterations to compute.

        Returns:
            int: Result of computation (to prevent compiler optimization).
        """
        result = 0
        for i in range(iterations):
            # Mix of operations to prevent compiler/interpreter optimization
            result += math.sqrt(i) * math.sin(i) * math.cos(i)
            result += math.log(i + 1) if i > 0 else 0
        return result

    def execute(self, load_intensity=50):
        """Execute CPU-intensive computation based on load intensity.

        Args:
            load_intensity: CPU load intensity 1-100 (default: 50).
                           Higher values = more CPU work per request.

        Returns:
            dict: Computation results including time and operation count.
        """
        # Clamp intensity to valid range
        intensity = max(1, min(100, int(load_intensity)))

        # Map intensity 1-100 to iterations 10,000 - 1,000,000
        # This provides measurable CPU load without overwhelming the container
        iterations = int(10000 + (intensity / 100.0) * 990000)

        logger.debug(f"CPU computation starting: intensity={intensity}, iterations={iterations}")

        start_time = time.monotonic()

        # Perform CPU-intensive work
        result = self._compute_intensive(iterations)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Track totals
        self._total_operations += iterations
        self._total_computation_time += elapsed_ms

        logger.info(
            f"CPU computation completed: intensity={intensity}, "
            f"iterations={iterations}, time={elapsed_ms:.2f}ms"
        )

        return {
            'operations': iterations,
            'computation_time_ms': round(elapsed_ms, 2),
            'result': round(result, 4),
            'total_operations': self._total_operations,
            'total_computation_time_ms': round(self._total_computation_time, 2)
        }


# Standalone entry point for testing
if __name__ == '__main__':
    import os
    logging.basicConfig(level=logging.INFO)
    stress = CPUStress()
    intensity = int(os.environ.get('LOAD_INTENSITY', '50'))
    result = stress.execute(intensity)
    print(f"Result: {result}")
