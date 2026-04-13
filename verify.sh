#!/usr/bin/env bash
# =============================================================================
# verify.sh — Post-deployment health checks for Kind-KEDA Lab Environment
# Verifies cluster health, component status, and workload readiness.
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Source configuration and libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/logging.sh"
source "${SCRIPT_DIR}/lib/keda.sh"

# Track overall health
OVERALL_STATUS=0

# -----------------------------------------------------------------------------
# Main verification
# -----------------------------------------------------------------------------
main() {
    log::section "Kind-KEDA Lab Environment — Verification"

    # --- Check kind cluster ---
    verify::cluster

    # --- Check KEDA ---
    verify::keda

    # --- Check RabbitMQ ---
    verify::rabbitmq

    # --- Check Prometheus ---
    verify::prometheus

    # --- Check Testkube ---
    verify::testkube

    # --- Check workloads ---
    verify::workloads

    # --- Final summary ---
    if [[ ${OVERALL_STATUS} -eq 0 ]]; then
        log::section "All Checks Passed"
        log::success "Kind-KEDA Lab Environment is healthy!"
    else
        log::section "Some Checks Failed"
        log::err "Review the errors above and re-run setup if needed"
    fi

    return ${OVERALL_STATUS}
}

# -----------------------------------------------------------------------------
# Verification functions
# -----------------------------------------------------------------------------
verify::cluster() {
    log::msg "Verifying kind cluster..."

    # Check cluster exists
    if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log::err "Cluster '${CLUSTER_NAME}' not found"
        OVERALL_STATUS=1
        return 1
    fi
    log::success "Cluster '${CLUSTER_NAME}' exists"

    # Check kubectl context
    local current_context
    current_context=$(kubectl config current-context 2>/dev/null || echo "")
    if [[ "${current_context}" == *"kind-${CLUSTER_NAME}"* ]]; then
        log::success "kubectl context set to kind-${CLUSTER_NAME}"
    else
        log::warn "kubectl context is '${current_context}' (expected kind-${CLUSTER_NAME})"
    fi

    # Check core nodes
    local node_count
    node_count=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
    if [[ "${node_count}" -gt 0 ]]; then
        log::success "Cluster has ${node_count} node(s)"
    else
        log::err "No nodes found in cluster"
        OVERALL_STATUS=1
        return 1
    fi
}

verify::keda() {
    log::msg "Verifying KEDA..."

    if ! keda::verify; then
        OVERALL_STATUS=1
        return 1
    fi

    # Check KEDA version
    local keda_version
    keda_version=$(kubectl get deployment keda-operator \
        --namespace "${KEDA_NAMESPACE}" \
        -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "unknown")
    log::submsg "KEDA image: ${keda_version}"
}

verify::rabbitmq() {
    log::msg "Verifying RabbitMQ..."

    local pod_count
    pod_count=$(kubectl get pods --namespace "${RABBITMQ_NAMESPACE}" \
        -l app=rabbitmq \
        --field-selector=status.phase=Running \
        --no-headers 2>/dev/null | wc -l)

    if [[ "${pod_count}" -gt 0 ]]; then
        log::success "RabbitMQ: ${pod_count} pod(s) running"
    else
        log::err "RabbitMQ: No running pods found"
        OVERALL_STATUS=1
        return 1
    fi
}

verify::prometheus() {
    log::msg "Verifying Prometheus..."

    # Check Prometheus operator
    local prom_pods
    prom_pods=$(kubectl get pods --namespace "${PROMETHEUS_NAMESPACE}" \
        --field-selector=status.phase=Running \
        --no-headers 2>/dev/null | wc -l)

    if [[ "${prom_pods}" -gt 0 ]]; then
        log::success "Prometheus: ${prom_pods} pod(s) running"
    else
        log::warn "Prometheus: No running pods (may still be starting)"
    fi

    # Check scraping is active
    local prom_svc
    prom_svc=$(kubectl get svc --namespace "${PROMETHEUS_NAMESPACE}" \
        -l app.kubernetes.io/name=prometheus \
        --no-headers 2>/dev/null | wc -l)

    if [[ "${prom_svc}" -gt 0 ]]; then
        log::success "Prometheus: Service found"
    else
        log::warn "Prometheus: Service not found"
    fi
}

verify::testkube() {
    log::msg "Verifying Testkube..."

    local testkube_pods
    testkube_pods=$(kubectl get pods --namespace "${TESTKUBE_NAMESPACE}" \
        --field-selector=status.phase=Running \
        --no-headers 2>/dev/null | wc -l)

    if [[ "${testkube_pods}" -gt 0 ]]; then
        log::success "Testkube: ${testkube_pods} pod(s) running"
    else
        log::warn "Testkube: No running pods (may still be starting)"
    fi

    # Check Testkube agent connectivity
    local api_svc
    api_svc=$(kubectl get svc --namespace "${TESTKUBE_NAMESPACE}" \
        -l app.kubernetes.io/name=testkube-api-server \
        --no-headers 2>/dev/null | wc -l)

    if [[ "${api_svc}" -gt 0 ]]; then
        log::success "Testkube: API server service found"
    else
        log::warn "Testkube: API server service not found"
    fi
}

verify::workloads() {
    log::msg "Verifying workloads..."

    # Check if workload namespace exists
    if ! kubectl get namespace "${WORKLOAD_NAMESPACE}" &>/dev/null; then
        log::warn "Workload namespace '${WORKLOAD_NAMESPACE}' not found"
        return 0
    fi

    # Check workload deployments
    local deploy_count
    deploy_count=$(kubectl get deployments --namespace "${WORKLOAD_NAMESPACE}" \
        --no-headers 2>/dev/null | wc -l)

    if [[ "${deploy_count}" -gt 0 ]]; then
        log::success "Workloads: ${deploy_count} deployment(s) found"
    else
        log::warn "Workloads: No deployments found (may not be deployed yet)"
    fi

    # Check ScaledObjects
    local so_count
    so_count=$(kubectl get scaledobjects --namespace "${WORKLOAD_NAMESPACE}" \
        --no-headers 2>/dev/null | wc -l)

    if [[ "${so_count}" -gt 0 ]]; then
        log::success "KEDA: ${so_count} ScaledObject(s) configured"
    else
        log::warn "KEDA: No ScaledObjects found (may not be deployed yet)"
    fi
}

# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
main "$@"
