#!/usr/bin/env bash
# =============================================================================
# setup.sh — Main entry point for Kind-KEDA Lab Environment
# Creates kind cluster, installs KEDA, RabbitMQ, Prometheus, Testkube,
# and deploys workload images and manifests.
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Source configuration and libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/logging.sh"
source "${SCRIPT_DIR}/lib/keda.sh"

# -----------------------------------------------------------------------------
# Main orchestration
# -----------------------------------------------------------------------------
main() {
    log::section "Kind-KEDA Lab Environment — Setup"

    # --- Pre-flight checks ---
    preflight::check_docker
    preflight::check_kind
    preflight::check_helm
    preflight::check_kubectl
    preflight::check_memory

    # --- Phase 1: Create kind cluster ---
    cluster::create

    # --- Phase 2: Install KEDA ---
    keda::install

    # --- Phase 3: Install RabbitMQ ---
    infra::install_rabbitmq

    # --- Phase 4: Install metrics-server ---
    infra::install_metrics_server

    # --- Phase 5: Install Prometheus ---
    infra::install_prometheus

    # --- Phase 6: Install Testkube ---
    infra::install_testkube

    # --- Phase 6: Build and load workload ---
    workload::build_and_load

    # --- Phase 7: Deploy workload manifests ---
    workload::deploy

    # --- Phase 8: Apply Testkube Test CRDs ---
    testkube::apply_test_crds

    log::section "Setup Complete"
    log::success "Kind-KEDA Lab Environment is ready!"
    log::msg "Run './verify.sh' to check cluster health"
    log::msg "Run './run-tests.sh' to run code-level tests"
    log::msg "Run './run-scaling-tests.sh' to run scaling tests"
}

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
preflight::check_docker() {
    log::msg "Checking Docker..."
    if ! docker info >/dev/null 2>&1; then
        log::err "Docker is not running or not installed"
        log::err "Please start Docker and try again"
        exit 1
    fi
    log::success "Docker is running"
}

preflight::check_kind() {
    log::msg "Checking kind..."
    if ! command -v kind &>/dev/null; then
        log::err "kind is not installed"
        log::err "Install: go install sigs.k8s.io/kind@latest"
        exit 1
    fi
    log::success "kind is available"
}

preflight::check_helm() {
    log::msg "Checking Helm..."
    if ! command -v helm &>/dev/null; then
        log::err "Helm is not installed"
        log::err "Install: https://helm.sh/docs/intro/install/"
        exit 1
    fi
    log::success "Helm is available"
}

preflight::check_kubectl() {
    log::msg "Checking kubectl..."
    if ! command -v kubectl &>/dev/null; then
        log::err "kubectl is not installed"
        log::err "Install: https://kubernetes.io/docs/tasks/tools/"
        exit 1
    fi
    log::success "kubectl is available"
}

preflight::check_memory() {
    log::msg "Checking available memory..."
    local mem_mb
    if command -v sysctl &>/dev/null; then
        mem_mb=$(sysctl -n hw.memsize 2>/dev/null | awk '{print int($1/1024/1024)}' || echo "8192")
    else
        mem_mb=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo "8192")
    fi

    if [[ "${mem_mb}" -lt 7000 ]]; then
        log::warn "Available memory (${mem_mb}MB) is below recommended 8GB"
        log::warn "Cluster may experience issues with limited memory"
    else
        log::success "Memory check passed (${mem_mb}MB available)"
    fi
}

# -----------------------------------------------------------------------------
# Cluster management
# -----------------------------------------------------------------------------
cluster::create() {
    log::section "Creating kind cluster: ${CLUSTER_NAME}"

    # Check if cluster already exists
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log::warn "Cluster '${CLUSTER_NAME}' already exists, deleting first..."
        kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null || true
    fi

    log::msg "Creating cluster with node image ${KIND_NODE_IMAGE}..."
    if kind create cluster \
        --name "${CLUSTER_NAME}" \
        --image "${KIND_NODE_IMAGE}" \
        --config "${SCRIPT_DIR}/kind-config.yaml" \
        --wait 120s; then
        log::success "Cluster '${CLUSTER_NAME}' created"
    else
        log::err "Failed to create cluster"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Infrastructure installation
# -----------------------------------------------------------------------------
infra::install_rabbitmq() {
    log::section "Installing RabbitMQ"

    log::msg "Deploying RabbitMQ from manifest..."
    if kubectl apply -f "${SCRIPT_DIR}/manifests/rabbitmq/rabbitmq.yaml"; then
        log::success "RabbitMQ manifest applied"
    else
        log::err "RabbitMQ deployment failed"
        return 1
    fi

    log::msg "Waiting for RabbitMQ to be ready..."
    if kubectl rollout status statefulset/rabbitmq \
        --namespace default \
        --timeout=180s >/dev/null 2>&1; then
        log::success "RabbitMQ is ready"
    else
        log::err "RabbitMQ failed to become ready"
        return 1
    fi

    # Create task-queue for KEDA ScaledObject
    log::msg "Creating task-queue for KEDA scaling..."
    if kubectl exec rabbitmq-0 -- rabbitmqctl eval 'rabbit_amqqueue:declare({resource, <<"/">>, queue, <<"task-queue">>}, true, false, [], none).' >/dev/null 2>&1; then
        log::success "task-queue created"
    else
        log::warn "Failed to create task-queue (will be created by workload)"
    fi
}

infra::install_metrics_server() {
    log::section "Installing metrics-server"

    log::msg "Deploying metrics-server..."
    if kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml >/dev/null 2>&1; then
        log::success "metrics-server manifest applied"
    else
        log::err "metrics-server deployment failed"
        return 1
    fi

    # Add --kubelet-insecure-tls for kind clusters (self-signed certs)
    log::msg "Configuring metrics-server for kind cluster..."
    kubectl patch deployment metrics-server -n kube-system --type='json' \
        -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]' >/dev/null 2>&1

    log::msg "Waiting for metrics-server to be ready..."
    if kubectl rollout status deployment/metrics-server \
        --namespace kube-system \
        --timeout=120s >/dev/null 2>&1; then
        log::success "metrics-server is ready"
    else
        log::warn "metrics-server may still be starting (will be ready shortly)"
    fi
}

infra::install_prometheus() {
    log::section "Installing Prometheus"

    log::msg "Adding Prometheus Community Helm repository..."
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1
    helm repo update >/dev/null 2>&1
    log::success "Prometheus Community Helm repository added"

    log::msg "Creating namespace ${PROMETHEUS_NAMESPACE}..."
    kubectl create namespace "${PROMETHEUS_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    log::msg "Installing kube-prometheus-stack..."
    if helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        --namespace "${PROMETHEUS_NAMESPACE}" \
        --version "${PROMETHEUS_CHART_VERSION}" \
        --values "${SCRIPT_DIR}/manifests/prometheus/prometheus-values.yaml" \
        --wait \
        --timeout 300s \
        >/dev/null 2>&1; then
        log::success "Prometheus stack installed"
    else
        log::err "Prometheus installation failed"
        return 1
    fi

    log::msg "Waiting for Prometheus to be ready..."
    kubectl rollout status statefulset/prometheus-prometheus-kube-prometheus-prometheus \
        --namespace "${PROMETHEUS_NAMESPACE}" \
        --timeout=180s >/dev/null 2>&1 || true

    log::success "Prometheus installation complete"
}

infra::install_testkube() {
    log::section "Installing Testkube"

    log::msg "Adding Kubeshop Helm repository..."
    helm repo add kubeshop https://kubeshop.github.io/helm-charts >/dev/null 2>&1
    helm repo update >/dev/null 2>&1
    log::success "Kubeshop Helm repository added"

    log::msg "Creating namespace ${TESTKUBE_NAMESPACE}..."
    kubectl create namespace "${TESTKUBE_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    log::msg "Installing Testkube..."
    if helm upgrade --install testkube kubeshop/testkube \
        --namespace "${TESTKUBE_NAMESPACE}" \
        --version "${TESTKUBE_CHART_VERSION}" \
        --wait \
        --timeout 300s \
        >/dev/null 2>&1; then
        log::success "Testkube installed"
    else
        log::err "Testkube installation failed"
        return 1
    fi

    log::msg "Waiting for Testkube agent to be ready..."
    kubectl rollout status deployment/testkube-api-server \
        --namespace "${TESTKUBE_NAMESPACE}" \
        --timeout=180s >/dev/null 2>&1 || true

    log::success "Testkube installation complete"
}

# -----------------------------------------------------------------------------
# Workload management
# -----------------------------------------------------------------------------
workload::build_and_load() {
    log::section "Building and loading workload image"

    log::msg "Building Docker image: ${WORKLOAD_IMAGE}:${WORKLOAD_IMAGE_TAG}..."
    if docker build \
        -t "${WORKLOAD_IMAGE}:${WORKLOAD_IMAGE_TAG}" \
        "${SCRIPT_DIR}/workload/"; then
        log::success "Docker image built"
    else
        log::err "Docker image build failed"
        exit 1
    fi

    log::msg "Loading image into kind cluster..."
    if kind load docker-image "${WORKLOAD_IMAGE}:${WORKLOAD_IMAGE_TAG}" \
        --name "${CLUSTER_NAME}"; then
        log::success "Image loaded into kind"
    else
        log::err "Failed to load image into kind"
        exit 1
    fi
}

workload::deploy() {
    log::section "Deploying workload manifests"

    log::msg "Creating workload namespace..."
    kubectl create namespace "${WORKLOAD_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    log::msg "Applying workload manifests..."
    kubectl apply -f "${SCRIPT_DIR}/manifests/workloads/" --namespace "${WORKLOAD_NAMESPACE}"

    log::msg "Applying KEDA ScaledObjects..."
    kubectl apply -f "${SCRIPT_DIR}/manifests/scaled-objects/" --namespace "${WORKLOAD_NAMESPACE}"

    log::success "Workload manifests applied"

    # Apply Prometheus ServiceMonitor in prometheus namespace
    log::msg "Configuring Prometheus ServiceMonitor..."
    if [[ -f "${SCRIPT_DIR}/manifests/workloads/prometheus-servicemonitor.yaml" ]]; then
        kubectl apply -f "${SCRIPT_DIR}/manifests/workloads/prometheus-servicemonitor.yaml" --namespace "${PROMETHEUS_NAMESPACE}"
        log::success "Prometheus ServiceMonitor configured"
    fi
}

# -----------------------------------------------------------------------------
# Testkube Test CRDs
# -----------------------------------------------------------------------------
testkube::apply_test_crds() {
    log::section "Applying Testkube Test CRDs"

    if [[ -d "${SCRIPT_DIR}/manifests/testkube/" ]]; then
        log::msg "Applying Testkube Test CRDs and TestSuite..."
        kubectl apply -f "${SCRIPT_DIR}/manifests/testkube/" --namespace "${TESTKUBE_NAMESPACE}"
        log::success "Testkube Test CRDs applied"
    else
        log::warn "No Testkube CRDs found, skipping"
    fi
}

# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
main "$@"
