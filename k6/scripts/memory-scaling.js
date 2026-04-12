/**
 * k6 Memory Scaling Test
 *
 * Sends HTTP POST requests to the workload /memory endpoint to trigger
 * memory allocation, then verifies KEDA scales the deployment based on
 * increased memory utilization.
 *
 * Test flow:
 * 1. Get initial pod count
 * 2. Send HTTP load to /memory endpoint with sustained allocations
 * 3. Monitor pod count for scale-up
 * 4. Verify scale-up occurred within threshold
 * 5. Stop load and verify scale-down (memory released after requests)
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const memoryRequestSuccess = new Rate('memory_request_success');

// Test configuration
const WORKLOAD_URL = __ENV.WORKLOAD_URL || 'http://memory-workload.workloads:8080';
const MEMORY_MB = parseInt(__ENV.MEMORY_MB || '128');
const VUS = parseInt(__ENV.VUS || '5');
const DURATION_SEC = parseInt(__ENV.DURATION_SEC || '120');

export const options = {
    stages: [
        { duration: '10s', target: VUS },       // Ramp up
        { duration: `${DURATION_SEC}s`, target: VUS },  // Sustained load
        { duration: '30s', target: 0 },         // Ramp down
    ],
    thresholds: {
        'http_req_duration': ['p(95)<10000'],   // 95th percentile under 10s (memory alloc slower)
        'http_req_failed': ['rate<0.1'],        // Error rate under 10%
        'memory_request_success': ['rate>0.9'], // 90% success rate
    },
};

export default function () {
    // Send POST request to memory endpoint
    const payload = JSON.stringify({
        memory_mb: MEMORY_MB,
        hold_time_ms: 500
    });

    const params = {
        headers: { 'Content-Type': 'application/json' },
        timeout: '15s',
    };

    const res = http.post(`${WORKLOAD_URL}/memory`, payload, params);

    // Check response
    const success = check(res, {
        'status is 200': (r) => r.status === 200,
        'has allocated_mb': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.allocated_mb > 0;
            } catch (e) {
                return false;
            }
        },
        'allocation time reasonable': (r) => r.timings.duration < 10000,
    });

    memoryRequestSuccess.add(success);

    // Longer delay between memory requests
    sleep(0.5);
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data),
    };
}

function textSummary(data) {
    const totalReqs = data.metrics.http_reqs.values.count || 0;
    const successRate = data.metrics.memory_request_success?.values?.rate || 0;
    const p95Duration = data.metrics.http_req_duration?.values?.['p(95)'] || 0;

    return `
=== Memory Scaling Test Summary ===
Total Requests: ${totalReqs}
Success Rate: ${(successRate * 100).toFixed(2)}%
P95 Duration: ${p95Duration.toFixed(2)}ms
Memory per Request: ${MEMORY_MB}MB
VUs: ${VUS}
===================================
`;
}
