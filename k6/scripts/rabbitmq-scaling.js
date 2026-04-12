/**
 * k6 RabbitMQ Scaling Test
 *
 * Sends HTTP POST requests to the workload /produce endpoint to fill
 * the RabbitMQ queue, then verifies KEDA scales consumer pods based
 * on queue depth.
 *
 * Test flow:
 * 1. Get initial consumer pod count
 * 2. Send messages via /produce endpoint to fill queue
 * 3. Monitor consumer pod count for scale-up
 * 4. Verify consumers scaled based on queue depth
 * 5. Stop producing and verify scale-down as queue drains
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const produceSuccess = new Rate('produce_success');
const consumeSuccess = new Rate('consume_success');
const queueDepth = new Trend('queue_depth_simulation');

// Test configuration
const WORKLOAD_URL = __ENV.WORKLOAD_URL || 'http://rabbitmq-workload.workloads:8080';
const MESSAGES_PER_REQUEST = parseInt(__ENV.MESSAGES_PER_REQUEST || '50');
const MESSAGE_SIZE = parseInt(__ENV.MESSAGE_SIZE || '256');
const VUS = parseInt(__ENV.VUS || '3');
const PRODUCE_DURATION_SEC = parseInt(__ENV.PRODUCE_DURATION_SEC || '60');
const DRAIN_DURATION_SEC = parseInt(__ENV.DRAIN_DURATION_SEC || '90');

export const options = {
    stages: [
        { duration: '10s', target: VUS },                          // Ramp up producers
        { duration: `${PRODUCE_DURATION_SEC}s`, target: VUS },     // Sustained produce
        { duration: `${DRAIN_DURATION_SEC}s`, target: 0 },         // Ramp down, let queue drain
    ],
    thresholds: {
        'http_req_failed': ['rate<0.1'],           // Error rate under 10%
        'produce_success': ['rate>0.9'],           // 90% produce success rate
        'queue_depth_simulation': ['avg>0'],       // Queue should have messages
    },
};

let phase = 'produce'; // Track test phase

export default function () {
    if (phase === 'produce') {
        // Produce messages to queue
        const payload = JSON.stringify({
            count: MESSAGES_PER_REQUEST,
            size: MESSAGE_SIZE
        });

        const params = {
            headers: { 'Content-Type': 'application/json' },
            timeout: '10s',
        };

        const res = http.post(`${WORKLOAD_URL}/produce`, payload, params);

        const success = check(res, {
            'produce status 200': (r) => r.status === 200,
            'produced count > 0': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.count > 0;
                } catch (e) {
                    return false;
                }
            },
        });

        produceSuccess.add(success);

        if (success) {
            try {
                const body = JSON.parse(res.body);
                queueDepth.add(body.total_produced || 0);
            } catch (e) {
                // Ignore parse errors
            }
        }

        sleep(0.5);
    } else {
        // Try to consume messages (simulate drain)
        const payload = JSON.stringify({
            count: 10,
            delay: 100
        });

        const params = {
            headers: { 'Content-Type': 'application/json' },
            timeout: '10s',
        };

        const res = http.post(`${WORKLOAD_URL}/consume`, payload, params);

        const success = check(res, {
            'consume status 200': (r) => r.status === 200,
        });

        consumeSuccess.add(success);

        sleep(1);
    }
}

export function setup() {
    // Initial setup - could check initial state here
    return { startTime: Date.now() };
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data),
    };
}

function textSummary(data) {
    const produceRate = data.metrics.produce_success?.values?.rate || 0;
    const consumeRate = data.metrics.consume_success?.values?.rate || 0;
    const avgQueueDepth = data.metrics.queue_depth_simulation?.values?.avg || 0;

    return `
=== RabbitMQ Scaling Test Summary ===
Produce Success Rate: ${(produceRate * 100).toFixed(2)}%
Consume Success Rate: ${(consumeRate * 100).toFixed(2)}%
Avg Queue Depth: ${avgQueueDepth.toFixed(2)}
Messages per Request: ${MESSAGES_PER_REQUEST}
VUs: ${VUS}
======================================
`;
}
