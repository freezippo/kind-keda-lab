#!/usr/bin/env python3
"""
Memory Stress Workload Module — Request-Driven

Allocates memory per HTTP request. Each request triggers memory allocation
proportional to the MEMORY_LIMIT_MB parameter. Memory is held for the duration
of the request and released when the request completes.

This module is designed to be called by the main HTTP server — it does NOT
run its own server. Each allocate() call allocates, holds, and releases memory.
"""

import time
import logging

logger = logging.getLogger('memory_stress')

# Constants
CHUNK_SIZE = 1024 * 1024  # 1 MB per chunk
MIN_MEMORY_MB = 1
MAX_MEMORY_MB = 512
DEFAULT_HOLD_TIME_MS = 500


class MemoryStress:
    """Allocates and releases memory on demand per HTTP request."""

    def __init__(self):
        """Initialize memory stress handler."""
        self._total_allocated_mb = 0
        self._total_requests = 0
        logger.info("MemoryStress handler initialized (request-driven mode)")

    def _allocate_chunks(self, memory_mb):
        """Allocate memory in 1 MB chunks.

        Args:
            memory_mb: Amount of memory to allocate in MB.

        Returns:
            list: List of allocated bytearrays.
        """
        buffers = []
        for i in range(memory_mb):
            # Allocate 1 MB chunk and write pattern to ensure actual allocation
            buffer = bytearray(b'\xFF' * CHUNK_SIZE)
            # Write pattern to prevent lazy allocation
            for j in range(0, CHUNK_SIZE, 4096):
                buffer[j:j+8] = i.to_bytes(8, 'little')
            buffers.append(buffer)
        return buffers

    def allocate(self, memory_mb=64, hold_time_ms=None):
        """Allocate memory, hold for specified time, then release.

        Args:
            memory_mb: Amount of memory to allocate in MB (1-512).
            hold_time_ms: How long to hold memory in ms (default: 500).

        Returns:
            dict: Allocation results including size and hold time.
        """
        # Clamp values
        mb = max(MIN_MEMORY_MB, min(MAX_MEMORY_MB, int(memory_mb)))
        hold_ms = max(10, min(10000, int(hold_time_ms or DEFAULT_HOLD_TIME_MS)))

        logger.debug(f"Memory allocation starting: {mb}MB, hold={hold_ms}ms")

        start_time = time.monotonic()

        # Allocate memory
        buffers = self._allocate_chunks(mb)
        alloc_elapsed_ms = (time.monotonic() - start_time) * 1000

        logger.info(f"Memory allocated: {mb}MB in {alloc_elapsed_ms:.2f}ms, holding for {hold_ms}ms")

        # Hold memory for specified time
        hold_start = time.monotonic()
        while (time.monotonic() - hold_start) * 1000 < hold_ms:
            # Touch memory periodically to prevent swapping
            time.sleep(0.01)
            if buffers:
                buffers[0][0:8] = int(time.monotonic()).to_bytes(8, 'little')

        hold_elapsed_ms = (time.monotonic() - hold_start) * 1000

        # Release memory
        del buffers
        total_elapsed_ms = (time.monotonic() - start_time) * 1000

        # Track totals
        self._total_allocated_mb += mb
        self._total_requests += 1

        logger.info(
            f"Memory released: {mb}MB held for {hold_elapsed_ms:.2f}ms, "
            f"total request time={total_elapsed_ms:.2f}ms"
        )

        return {
            'allocated_mb': mb,
            'allocation_time_ms': round(alloc_elapsed_ms, 2),
            'hold_time_ms': round(hold_elapsed_ms, 2),
            'total_request_time_ms': round(total_elapsed_ms, 2),
            'total_allocated_mb': self._total_allocated_mb,
            'total_requests': self._total_requests
        }


# Standalone entry point for testing
if __name__ == '__main__':
    import os
    logging.basicConfig(level=logging.INFO)
    stress = MemoryStress()
    memory_mb = int(os.environ.get('MEMORY_LIMIT_MB', '64'))
    result = stress.allocate(memory_mb)
    print(f"Result: {result}")
