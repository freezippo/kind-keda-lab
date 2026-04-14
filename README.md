# Kind-KEDA Lab

A local Kubernetes lab environment for learning and testing **KEDA (Kubernetes Event-driven Autoscaling)** with real workloads, event sources, and test automation.

## Overview

This project provisions a complete kind (Kubernetes in Docker) cluster with:

- **KEDA** — Event-driven autoscaler that scales workloads to/from zero based on external events
- **RabbitMQ** — Message queue for queue-depth-based scaling
- **Prometheus** — Metrics collection and scraping for metric-based scaling
- **metrics-server** — Kubernetes Metrics API for CPU/memory-based HPAs
- **Testkube** — Test orchestration platform running k6 load tests as TestWorkflows
- **Python Workloads** — Multi-mode HTTP workloads (CPU, memory, RabbitMQ, Prometheus modes)

## Architecture

### Cluster Overview

```mermaid
graph TB
    subgraph kind-keda-lab["kind-keda-lab Cluster"]
        subgraph lab["lab Namespace"]
            cpu[CPU Workload<br/>Deployment]
            mem[Memory Workload<br/>Deployment]
            rmq_producer[RabbitMQ Producer<br/>Deployment]
            rmq_consumer[RabbitMQ Consumer<br/>Deployment 1-10 replicas]
            prom[Prometheus Workload<br/>Deployment]
        end

        subgraph keda["KEDA Operators"]
            so_cpu[CPU ScaledObject<br/>Target: 50% CPU]
            so_mem[Memory ScaledObject<br/>Target: 256Mi]
            so_rmq[RabbitMQ ScaledObject<br/>Target: 10 messages]
            so_prom[Prometheus ScaledObject<br/>Target: Custom metric]
        end

        subgraph infra["Infrastructure"]
            rabbitmq[(RabbitMQ<br/>default namespace)]
            prometheus[Prometheus<br/>prometheus namespace]
            metrics[metrics-server<br/>kube-system namespace]
            testkube[Testkube<br/>testkube namespace]
        end
    end

    cpu -->|CPU metrics| metrics
    mem -->|Memory metrics| metrics
    prom -->|HTTP scrape| prometheus

    so_cpu -.->|HPA| cpu
    so_mem -.->|HPA| mem
    so_rmq -.->|HPA| rmq_consumer
    so_prom -.->|HPA| prom

    rmq_producer -->|AMQP| rabbitmq
    rmq_consumer -->|AMQP| rabbitmq
    so_rmq -->|Queue depth| rabbitmq
    so_prom -->|Metric query| prometheus

    testkube -.->|k6 load| cpu
    testkube -.->|k6 load| mem
    testkube -.->|HTTP POST| rmq_producer
    testkube -.->|HTTP load| prom
```

### KEDA Scaling Flow

```mermaid
sequenceDiagram
    participant Load as k6 Load Generator<br/>(Testkube)
    participant Workload as Workload Pod<br/>(lab namespace)
    participant Metrics as Metrics Source<br/>(metrics-server/RabbitMQ/Prometheus)
    participant KEDA as KEDA Operator
    participant HPA as Kubernetes HPA
    participant Scale as Scale Target<br/>(Deployment)

    Load->>Workload: HTTP requests / messages
    Workload->>Metrics: Generate CPU/memory/queue activity

    loop Polling (every 15s)
        KEDA->>Metrics: Query metrics
        Metrics-->>KEDA: Current utilization
    end

    alt Threshold exceeded
        KEDA->>HPA: Update replica count
        HPA->>Scale: Scale up deployment
        Scale-->>Scale: Create new pods (1 → 10)
    else Below threshold (cooldown 300s)
        KEDA->>HPA: Reduce replica count
        HPA->>Scale: Scale down deployment
        Scale-->>Scale: Terminate excess pods (10 → 1)
    end
```

### Component Interactions by Scaler Type

```mermaid
flowchart LR
    subgraph CPU["CPU Scaling"]
        k6_cpu[k6 Load] -->|POST /cpu<br/>intensity: 80| cpu_deploy[cpu-workload]
        cpu_deploy -->|High CPU| ms[metrics-server]
        ms -->|CPU > 50%| keda_cpu[KEDA CPU Scaler]
        keda_cpu -->|Scale| cpu_deploy
    end

    subgraph Memory["Memory Scaling"]
        k6_mem[k6 Load] -->|POST /memory<br/>memory_mb: 256| mem_deploy[memory-workload]
        mem_deploy -->|High Memory| ms2[metrics-server]
        ms2 -->|Memory > 256Mi| keda_mem[KEDA Memory Scaler]
        keda_mem -->|Scale| mem_deploy
    end

    subgraph RabbitMQ["RabbitMQ Scaling"]
        k6_rmq[k6 Load] -->|POST /produce<br/>count: 100| producer[rabbitmq-producer]
        producer -->|Publish| rmq[(RabbitMQ<br/>task-queue)]
        rmq -->|10+ messages| keda_rmq[KEDA RabbitMQ Scaler]
        keda_rmq -->|Scale| consumer[rabbitmq-consumer 1-10]
        consumer -->|Consume| rmq
    end

    subgraph Prometheus["Prometheus Scaling"]
        k6_prom[k6 Load] -->|HTTP load| prom_deploy[prometheus-workload]
        prom_deploy -->|Expose /metrics| prom_svc[Prometheus]
        prom_svc -->|Query metric| keda_prom[KEDA Prometheus Scaler]
        keda_prom -->|Scale| prom_deploy
    end
```

### Setup Process Flow

```mermaid
flowchart TD
    A[./setup.sh] --> B{Pre-flight Checks}
    B -->|Docker| C[Check Docker running]
    B -->|kind| D[Check kind installed]
    B -->|Helm| E[Check Helm installed]
    B -->|kubectl| F[Check kubectl installed]
    B -->|Memory| G[Check 8GB+ RAM]

    C --> H[Phase 1: Create kind Cluster]
    D --> H
    E --> H
    F --> H
    G --> H

    H --> I[Phase 2: Install KEDA]
    I --> J[Phase 3: Install RabbitMQ]
    J --> K[Phase 4: Install metrics-server]
    K --> L[Phase 5: Install Prometheus]
    L --> M[Phase 6: Install Testkube]
    M --> N[Phase 7: Build & Load Workload Image]
    N --> O[Phase 8: Deploy Workload Manifests]
    O --> P[Phase 9: Apply Testkube TestWorkflows]
    P --> Q{Setup Complete}

    Q --> R[./verify.sh]
    R --> S[Run Scaling Tests]
```

### RabbitMQ Auto-Consumer Pattern

```mermaid
flowchart TD
    subgraph Producer["rabbitmq-producer (1 replica)"]
        API[HTTP Server :8080]
        API -->|POST /produce| PROD[Produce Messages]
        PROD -->|Publish N messages| QUEUE[(RabbitMQ<br/>task-queue)]
    end

    subgraph Consumer["rabbitmq-consumer (1-10 replicas)"]
        API2[HTTP Server :8080]
        API2 -->|POST /consume| MAN[Manual Consume]

        BG[Background Thread<br/>auto_consume_loop]
        BG -->|Every 1s| POLL[Poll 10 messages]
        POLL -->|Consume| QUEUE
        MAN -->|Consume| QUEUE
    end

    QUEUE -.->|Queue depth| KEDA[KEDA ScaledObject]
    KEDA -.->|Scale if > 10 msgs| CONSUMER_DEPLOY[Consumer Deployment]
    CONSUMER_DEPLOY -->|Creates| Consumer

    style BG fill:#90EE90
    style KEDA fill:#FFD700
```

### Test Execution Flow

```mermaid
flowchart LR
    subgraph CLI["Command Line"]
        RUN[./run-scaling-tests.sh]
    end

    subgraph Testkube["Testkube (testkube namespace)"]
        TW[TestWorkflows]
        TW -->|cpu-scaling-workflow.yaml| CPU_TW[CPU TestWorkflow]
        TW -->|memory-scaling-workflow.yaml| MEM_TW[Memory TestWorkflow]
        TW -->|rabbitmq-scaling-workflow.yaml| RMQ_TW[RabbitMQ TestWorkflow]
        TW -->|prometheus-scaling-workflow.yaml| PROM_TW[Prometheus TestWorkflow]
    end

    subgraph Execution["Test Execution"]
        CPU_TW -->|grafana/k6 image| K6_CPU[k6 CPU Load]
        MEM_TW -->|grafana/k6 image| K6_MEM[k6 Memory Load]
        RMQ_TW -->|grafana/k6 image| K6_RMQ[k6 RabbitMQ Load]
        PROM_TW -->|grafana/k6 image| K6_PROM[k6 Prometheus Load]
    end

    subgraph Results["Scaling Verification"]
        K6_CPU -->|HTTP POST| CPU_APP[cpu-workload]
        K6_MEM -->|HTTP POST| MEM_APP[memory-workload]
        K6_RMQ -->|HTTP POST| RMQ_APP[rabbitmq-producer]
        K6_PROM -->|HTTP load| PROM_APP[prometheus-workload]

        CPU_APP -.->|HPA scales| HPA1[1 → 10 pods]
        MEM_APP -.->|HPA scales| HPA2[1 → 10 pods]
        RMQ_APP -.->|Queue fills| HPA3[1 → 10 pods]
        PROM_APP -.->|Metric threshold| HPA4[1 → 10 pods]
    end

    RUN --> TW
```

### Scaling Triggers

| Workload | KEDA Trigger | Scale Condition | Min → Max |
|----------|-------------|-----------------|-----------|
| `cpu-workload` | CPU utilization | > 50% average CPU | 1 → 10 |
| `memory-workload` | Memory utilization | > 256Mi average | 1 → 10 |
| `rabbitmq-consumer` | RabbitMQ queue depth | > 10 messages in `task-queue` | 1 → 10 |
| `cpu-workload` (Prometheus) | Prometheus metric query | Custom metric threshold | 1 → 10 |

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | 24+ | Container runtime for kind cluster |
| kind | 0.24+ | Kubernetes in Docker |
| kubectl | 1.30+ | Kubernetes CLI |
| Helm | 3.14+ | Package manager for KEDA, Prometheus, Testkube |
| Python | 3.11+ | Workload runtime and test dependencies |
| pip3 | — | Python package management |

**Optional tools:**

- `shellcheck` — Shell script linting (used by `run-tests.sh`)
- `kubeconform` — Kubernetes manifest validation (used by `run-tests.sh`)
- `k6` — Load testing CLI (alternative to Testkube for running scaling tests)

### Install Prerequisites (macOS)

```bash
# Docker Desktop
brew install --cask docker

# kind
brew install kind

# kubectl
brew install kubectl

# Helm
brew install helm

# Optional: shellcheck, kubeconform, k6
brew install shellcheck kubeconform k6
```

## Quick Start

### 1. Set Up the Lab Environment

```bash
./setup.sh
```

This script:
- Creates a kind cluster (`kind-keda-lab`)
- Installs KEDA, RabbitMQ, metrics-server, Prometheus, and Testkube
- Builds and loads the Python workload Docker image
- Deploys workload manifests and KEDA ScaledObjects
- Deploys Testkube TestWorkflow definitions

**Setup takes ~5-10 minutes** depending on network speed (Helm chart downloads are the longest part).

### 2. Verify Cluster Health

```bash
./verify.sh
```

Checks:
- Cluster connectivity and node status
- KEDA operator running
- RabbitMQ pods ready
- Prometheus stack running
- Testkube agent running
- Workload deployments and ScaledObjects

### 3. Run Scaling Tests

```bash
./run-scaling-tests.sh
```

Executes 4 k6 load tests via Testkube TestWorkflows:
- **cpu-scaling-test** — Generates HTTP load to trigger CPU-based HPA scaling
- **memory-scaling-test** — Triggers memory-based HPA scaling
- **rabbitmq-scaling-test** — Sends messages to RabbitMQ queue for KEDA queue-depth scaling
- **prometheus-scaling-test** — Triggers Prometheus metric-based scaling

**Monitor scaling in real-time:**

```bash
# Watch KEDA ScaledObjects
watch kubectl get scaledobjects -n lab

# Watch HPA scaling events
watch kubectl get hpa -n lab

# Watch pod scaling
watch kubectl get pods -n lab -w
```

### 4. Clean Up

```bash
./teardown.sh
```

Deletes the kind cluster and removes the workload Docker image.

## Workloads

All workloads use a single Python HTTP server image with 4 modes controlled by the `MODE` environment variable.

### CPU Mode

```yaml
MODE: cpu
```

- **Endpoint:** `POST /cpu`
- **Payload:** `{"intensity": 50}` (1-100)
- **Behavior:** Executes CPU-intensive prime number computation
- **Scaling:** KEDA monitors CPU utilization via metrics-server; scales when avg > 50%

### Memory Mode

```yaml
MODE: memory
```

- **Endpoint:** `POST /memory`
- **Payload:** `{"memory_mb": 128, "hold_time": 5}`
- **Behavior:** Allocates specified MB of memory, holds for specified seconds
- **Scaling:** KEDA monitors memory utilization; scales when avg > 256Mi

### RabbitMQ Mode

```yaml
MODE: rabbitmq
RABBITMQ_ROLE: producer|consumer
RABBITMQ_URL: amqp://guest:guest@rabbitmq.default.svc.cluster.local:5672
RABBITMQ_QUEUE: task-queue
```

- **Producer endpoint:** `POST /produce`
- **Producer payload:** `{"count": 10, "size": 256}`
- **Consumer endpoint:** `POST /consume` (manual trigger)
- **Auto-consume:** Consumer pods run a background thread that continuously polls the queue
- **Scaling:** KEDA monitors RabbitMQ queue depth via ScaledObject; scales when > 10 messages in queue

**RabbitMQ workload architecture:**

```mermaid
flowchart LR
    Producer[rabbitmq-producer<br/>1 replica] -->|POST /produce| Queue[(task-queue)]
    Queue -->|Queue depth| KEDA[KEDA ScaledObject]
    KEDA -->|Scale if > 10 msgs| Consumer[rabbitmq-consumer<br/>1 → 10 replicas]
    Consumer -->|auto-consume loop| Queue
    Consumer -->|POST /consume| Manual[Manual consume]
```

### Prometheus Mode

```yaml
MODE: prometheus
```

- **Endpoint:** `GET /metrics` (Prometheus text format on port 8080)
- **Behavior:** Exposes custom metrics (`workload_requests_total`, `workload_queue_depth_simulation`)
- **Scraping:** Prometheus scrapes every 15s via ServiceMonitor (in `prometheus` namespace)
- **Scaling:** KEDA queries Prometheus for `workload_queue_depth_simulation` metric; scales when sum > 5

**Prometheus scaling architecture:**

```mermaid
flowchart LR
    k6[k6 Load Test] -->|GET /metrics| prom_workload[prometheus-workload<br/>port 8080]
    prom_workload -->|Exposes metrics| svc[Service: prometheus-workload]
    svc -->|Scraped every 15s| prom[Prometheus Server]
    prom -->|Query: sum(workload_queue_depth_simulation)| keda[KEDA Prometheus Scaler]
    keda -->|Scale if > 5| prom_deploy[prometheus-workload<br/>Deployment 1-10 replicas]
```

**Important notes:**
- The ServiceMonitor must be in the `prometheus` namespace with label `release: prometheus`
- The ServiceMonitor uses `namespaceSelector` to discover endpoints in the `lab` namespace
- The metric `workload_queue_depth_simulation` increments with each request to `/metrics`
- The workload pod must be restarted to reset the metric's time-based drain factor for testing

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `cpu` | Workload mode: `cpu`, `memory`, `rabbitmq`, `prometheus` |
| `LOAD_INTENSITY` | `50` | CPU load intensity (1-100) |
| `MEMORY_LIMIT_MB` | `256` | Memory allocation limit per request (MB) |
| `PROCESSING_DELAY_MS` | `1000` | Processing delay for RabbitMQ messages (ms) |
| `SERVER_PORT` | `8080` | HTTP server port |
| `METRICS_PORT` | `8000` | Metrics server port (prometheus mode) |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672` | RabbitMQ connection string |
| `RABBITMQ_QUEUE` | `task-queue` | RabbitMQ queue name |
| `RABBITMQ_ROLE` | `consumer` | RabbitMQ role: `producer` or `consumer` |
| `CONFIG_FILE` | — | Optional JSON config file path |

## Running Tests

### Code-Level Tests

```bash
./run-tests.sh
```

Runs:
- **Python unit tests** — `pytest` with coverage reporting
- **ShellCheck** — Shell script linting for all `.sh` files
- **kubeconform** — Kubernetes manifest schema validation
- **k6 syntax check** — Validates k6 script syntax (if k6 installed)

### Manual TestWorkflow Execution

```bash
# Run a single scaling test via Testkube
kubectl testkube run testworkflow cpu-scaling-test -n testkube

# Check test execution status
kubectl get testworkflowexecutions -n testkube

# View test logs
kubectl testkube get execution <execution-id> -n testkube
```

### Manual Scaling Verification

```bash
# Trigger CPU scaling (run from a pod in the cluster)
kubectl run -it --rm load-generator --image=curlimages/curl --restart=Never -- \
  curl -X POST http://cpu-workload.lab.svc.cluster.local:8080/cpu \
  -H "Content-Type: application/json" \
  -d '{"intensity": 80}'

# Watch scaling in another terminal
watch kubectl get hpa -n lab

# Send RabbitMQ messages
kubectl exec -it deploy/rabbitmq-producer -n lab -- \
  curl -X POST http://localhost:8080/produce \
  -H "Content-Type: application/json" \
  -d '{"count": 100, "size": 256}'

# Check RabbitMQ queue depth
kubectl exec rabbitmq-0 -n default -- rabbitmqctl list_queues name messages
```

## Observability

### Metrics Server

Provides Kubernetes Metrics API for CPU/memory-based HPAs:

```bash
# View pod resource usage
kubectl top pods -n lab

# View node resource usage
kubectl top nodes
```

### Prometheus

Access Prometheus UI:

```bash
kubectl port-forward -n prometheus svc/prometheus-prometheus-kube-prometheus-prometheus 9090:9090
```

Then open http://localhost:9090

**Useful queries:**

```
# KEDA HPA metrics
keda_hpa_replicas{namespace="lab"}

# Workload request rate
rate(http_requests_total{namespace="lab"}[5m])

# Pod CPU usage
container_cpu_usage_seconds_total{namespace="lab"}
```

### KEDA Events

```bash
# View KEDA scaling events
kubectl get events -n lab --field-selector reason=ScaledObjectReady

# Check ScaledObject status
kubectl describe scaledobject cpu-scaled-object -n lab
```

## Project Structure

```
kind-keda-lab/
├── setup.sh                    # Main setup: cluster, KEDA, RabbitMQ, Prometheus, Testkube
├── verify.sh                   # Post-deployment health checks
├── teardown.sh                 # Delete cluster and clean up
├── run-tests.sh                # Code-level tests (pytest, shellcheck, kubeconform)
├── run-scaling-tests.sh        # Execute KEDA scaling tests via Testkube
├── config.env                  # Configuration: versions, namespaces, resource limits
├── kind-config.yaml            # kind cluster configuration
├── lib/
│   ├── logging.sh              # Logging utilities (log::section, log::success, etc.)
│   └── keda.sh                 # KEDA helper functions
├── workload/
│   ├── src/
│   │   ├── main.py             # Main HTTP server with mode routing
│   │   ├── cpu_stress.py       # CPU-intensive computation handler
│   │   ├── memory_stress.py    # Memory allocation handler
│   │   ├── rabbitmq_worker.py  # RabbitMQ producer/consumer handler
│   │   └── metrics_server.py   # Prometheus metrics handler
│   ├── tests/                  # Python unit tests
│   ├── Dockerfile              # Workload image definition
│   └── requirements.txt        # Python dependencies
├── manifests/
│   ├── workloads/              # Workload Deployment and Service manifests
│   │   ├── cpu-workload.yaml
│   │   ├── memory-workload.yaml
│   │   ├── rabbitmq-workload.yaml
│   │   ├── prometheus-workload.yaml
│   │   └── prometheus-servicemonitor.yaml  # Prometheus scraping config
│   ├── scaled-objects/         # KEDA ScaledObject definitions
│   │   ├── cpu-scaled-object.yaml
│   │   ├── memory-scaled-object.yaml
│   │   ├── rabbitmq-scaled-object.yaml
│   │   └── prometheus-scaled-object.yaml
│   ├── rabbitmq/               # RabbitMQ StatefulSet manifest
│   │   └── rabbitmq.yaml
│   ├── prometheus/             # Prometheus Helm values
│   │   └── prometheus-values.yaml
│   └── testkube/               # Testkube TestWorkflow definitions
│       ├── cpu-scaling-workflow.yaml
│       ├── memory-scaling-workflow.yaml
│       ├── rabbitmq-scaling-workflow.yaml
│       └── prometheus-scaling-workflow.yaml
└── k6/
    └── scripts/                # k6 load test scripts (embedded in TestWorkflows)
        ├── cpu-scaling.js
        ├── memory-scaling.js
        ├── rabbitmq-scaling.js
        └── prometheus-scaling.js
```

## Troubleshooting

### KEDA Not Scaling

**Check ScaledObject status:**

```bash
kubectl get scaledobjects -n lab
kubectl describe scaledobject <name> -n lab
```

Look for:
- `READY: True` — ScaledObject is correctly configured
- `ACTIVE: True` — KEDA has detected events and HPA is active
- Events section for error messages

**Common issues:**

1. **CPU/Memory HPA shows `<unknown>` metrics**
   - Cause: metrics-server not running or failing
   - Fix: `kubectl rollout status deployment/metrics-server -n kube-system`
   - Check: `kubectl top pods -n lab` should show CPU/memory values

2. **RabbitMQ ScaledObject not ready**
   - Cause: `task-queue` doesn't exist in RabbitMQ
   - Fix: `kubectl exec rabbitmq-0 -n default -- rabbitmqadmin declare queue name=task-queue durable=true`

3. **RabbitMQ producer can't connect**
   - Cause: Wrong RabbitMQ URL (namespace mismatch)
   - Fix: Ensure URL is `amqp://guest:guest@rabbitmq.default.svc.cluster.local:5672`

4. **Prometheus ScaledObject not active**
   - Cause: ServiceMonitor not discovered by Prometheus
   - Fix: Ensure ServiceMonitor is in `prometheus` namespace with label `release: prometheus`
   - Check: `kubectl get servicemonitor -n prometheus` and verify Prometheus config at `/etc/prometheus/config_out/prometheus.env.yaml`

5. **Prometheus metric query returns empty**
   - Cause: Prometheus not scraping workload endpoint
   - Fix: Check ServiceMonitor `namespaceSelector` matches workload namespace, and endpoint port name matches service port
   - Check: `curl 'http://localhost:9090/api/v1/targets' | grep prometheus-workload` and verify health is `up`

6. **Prometheus metric value stays at 0**
   - Cause: Workload's `/metrics` endpoint not calling `record_request()`
   - Fix: Ensure workload code calls `prometheus_handler.record_request()` on each metrics request
   - Note: Metric includes time-based drain factor; restart workload pod to reset for fresh testing

### Workload Image Not Updating

kind clusters cache Docker layers. If you rebuild the workload image:

```bash
# Force rebuild without cache
docker build --no-cache -t kind-keda-lab-workload:latest workload/

# Reload into kind
kind load docker-image kind-keda-lab-workload:latest --name kind-keda-lab

# Force redeploy with new imagePullPolicy
kubectl rollout restart deployment -n lab
```

### Testkube TestWorkflow Not Found

```bash
# Check if TestWorkflows are deployed
kubectl get testworkflows -n testkube

# Check execution status
kubectl get testworkflowexecutions -n testkube

# View Testkube logs
kubectl logs -n testkube deploy/testkube-api-server
```

### Cluster Fails to Start

```bash
# Check kind cluster status
kind get clusters

# Check Docker
docker ps | grep kind-keda-lab

# Delete and recreate
./teardown.sh && ./setup.sh
```

## Version Matrix

| Component | Version | Source |
|-----------|---------|--------|
| Kubernetes | 1.33.1 | kindest/node |
| KEDA | 2.19.0 | kedacore/charts |
| RabbitMQ | 16.0.14 | bitnami/charts |
| Prometheus stack | 83.4.0 | prometheus-community/charts |
| Testkube | 2.8.3 | kubeshop/charts |

## License

MIT
