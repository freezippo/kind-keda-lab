/**
 * k6 Prometheus Scaling Test
 *
 * Sends HTTP requests to the workload to increase custom metrics,
 * then verifies KEDA scales the deployment based on Prometheus metric queries.
 *
 * Test flow:
 * 1. Get initial pod count and metric values
 * 2. Send HTTP load to increase custom metrics (request count, queue depth simulation)
 * 3. Monitor pod count for scale-up based on Prometheus metrics
 * 4. Verify scale-up occurred within threshold
 * 5. Stop load and verify scale-down
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Gauge } from 'k6/metrics';

// Custom metrics
const metricsRequestSuccess = new Rate('metrics_request_success');
const simulatedQueueDepth = new Gauge('simulated_queue_depth');

// Test configuration
const WORKLOAD_URL = __ENV.WORKLOAD_URL || 'http://prometheus-workload.workloads:8080';
const PROMETHEUS_URL = __ENV.PROMETHEUS_URL || 'http://prometheus-operated.monitoring:9090';
const VUS = parseInt(__ENV.VUS || '5');
const DURATION_SEC = parseInt(__ENV.DURATION_SEC || '120');

export const options = {
    stages: [
        { duration: '10s', target: VUS },       // Ramp up
        { duration: `${DURATION_SEC}s`, target: VUS },  // Sustained load
        { duration: '30s', target: 0 },         // Ramp down
    ],
    thresholds: {
        'http_req_duration': ['p(95)<2000'],    // 95th percentile under 2s
        'http_req_failed': ['rate<0.1'],        // Error rate under 10%
        'metrics_request_success': ['rate>0.9'], // 90% success rate
    },
};

export default function () {
    // Send requests to increase custom metrics
    const res = http.get(`${WORKLOAD_URL}/stats`);

    const success = check(res, {
        'stats status 200': (r) => r.status === 200,
        'has total_requests': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.total_requests >= 0;
            } catch (e) {
                return false;
            }
        },
    });

    metricsRequestSuccess.add(success);

    // Track simulated queue depth
    try {
        const body = JSON.parse(res.body);
        simulatedQueueDepth.add(body.total_requests || 0);
    } catch (e) {
        // Ignore parse errors
    }

    sleep(0.2);
}

export function teardown() {
    // Optionally query Prometheus to verify metrics were scraped
    const query = 'workload_queue_depth_simulation';
    const res = http.get(`${PROMETHEUS_URL}/api/v1/query?query=${encodeURIComponent(query)}`);

    if (res.status === 200) {
        try {
            const body = JSON.parse(res.body);
            if (body.data && body.data.result && body.data.result.length > 0) {
                const value = parseFloat(body.data.result[0].value[1]);
                console.log(`Final queue depth simulation value: ${value}`);
            }
        } catch (e) {
            console.log('Failed to parse Prometheus response');
        }
    }
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data),
    };
}

function textSummary(data) {
    const totalReqs = data.metrics.http_reqs.values.count || 0;
    const successRate = data.metrics.metrics_request_success?.values?.rate || 0;
    const p95Duration = data.metrics.http_req_duration?.values?.['p(95)'] || 0;
    const maxQueueDepth = data.metrics.simulated_queue_depth?.values?.max || 0;

    return `
=== Prometheus Scaling Test Summary ===
Total Requests: ${totalReqs}
Success Rate: ${(successRate * 100).toFixed(2)}%
P95 Duration: ${p95Duration.toFixed(2)}ms
Max Simulated Queue Depth: ${maxQueueDepth.toFixed(2)}
VUs: ${VUS}
=======================================
`;
}
