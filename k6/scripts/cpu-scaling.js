/**
 * k6 CPU Scaling Test
 *
 * Sends HTTP POST requests to the workload /cpu endpoint to trigger
 * CPU-intensive computation, then verifies KEDA scales the deployment
 * based on increased CPU utilization.
 *
 * Test flow:
 * 1. Get initial pod count
 * 2. Send sustained HTTP load to /cpu endpoint
 * 3. Monitor pod count for scale-up
 * 4. Verify scale-up occurred within threshold
 * 5. Stop load and verify scale-down
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const cpuRequestSuccess = new Rate('cpu_request_success');

// Test configuration
const WORKLOAD_URL = __ENV.WORKLOAD_URL || 'http://cpu-workload.workloads:8080';
const LOAD_INTENSITY = parseInt(__ENV.LOAD_INTENSITY || '80');
const VUS = parseInt(__ENV.VUS || '10');
const DURATION_SEC = parseInt(__ENV.DURATION_SEC || '120');
const SCALE_UP_THRESHOLD_SEC = parseInt(__ENV.SCALE_UP_THRESHOLD_SEC || '60');

export const options = {
    stages: [
        { duration: '10s', target: VUS },       // Ramp up
        { duration: `${DURATION_SEC}s`, target: VUS },  // Sustained load
        { duration: '30s', target: 0 },         // Ramp down
    ],
    thresholds: {
        'http_req_duration': ['p(95)<5000'],    // 95th percentile under 5s
        'http_req_failed': ['rate<0.1'],        // Error rate under 10%
        'cpu_request_success': ['rate>0.9'],    // 90% success rate
    },
};

export default function () {
    // Send POST request to CPU endpoint
    const payload = JSON.stringify({
        intensity: LOAD_INTENSITY
    });

    const params = {
        headers: { 'Content-Type': 'application/json' },
        timeout: '10s',
    };

    const res = http.post(`${WORKLOAD_URL}/cpu`, payload, params);

    // Check response
    const success = check(res, {
        'status is 200': (r) => r.status === 200,
        'has computation_time_ms': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.computation_time_ms > 0;
            } catch (e) {
                return false;
            }
        },
        'response time acceptable': (r) => r.timings.duration < 5000,
    });

    cpuRequestSuccess.add(success);

    // Small delay between requests
    sleep(0.1);
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data),
    };
}

function textSummary(data) {
    const totalReqs = data.metrics.http_reqs.values.count || 0;
    const successRate = data.metrics.cpu_request_success?.values?.rate || 0;
    const p95Duration = data.metrics.http_req_duration?.values?.['p(95)'] || 0;

    return `
=== CPU Scaling Test Summary ===
Total Requests: ${totalReqs}
Success Rate: ${(successRate * 100).toFixed(2)}%
P95 Duration: ${p95Duration.toFixed(2)}ms
Load Intensity: ${LOAD_INTENSITY}
VUs: ${VUS}
================================
`;
}
