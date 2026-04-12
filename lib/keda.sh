#!/usr/bin/env bash
# =============================================================================
# KEDA installation helpers for Kind-KEDA Lab Environment
# Provides functions to install and verify KEDA via Helm.
# =============================================================================

# -----------------------------------------------------------------------------
# keda::install — Install KEDA via Helm chart
# Globals: KEDA_VERSION, KEDA_NAMESPACE, CLUSTER_NAME
# -----------------------------------------------------------------------------
keda::install() {
    log::section "Installing KEDA v${KEDA_VERSION}"

    log::msg "Adding KEDA Helm repository..."
    helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1
    helm repo update >/dev/null 2>&1
    log::success "KEDA Helm repository added"

    log::msg "Creating namespace ${KEDA_NAMESPACE}..."
    kubectl create namespace "${KEDA_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    log::msg "Installing KEDA operator..."
    helm upgrade --install keda kedacore/keda \
        --namespace "${KEDA_NAMESPACE}" \
        --version "${KEDA_VERSION}" \
        --wait \
        --timeout 300s \
        --set podSecurityContext.fsGroup=65534 \
        >/dev/null 2>&1

    if [[ $? -eq 0 ]]; then
        log::success "KEDA operator installed"
    else
        log::err "KEDA installation failed"
        return 1
    fi

    log::msg "Waiting for KEDA operator to be ready..."
    kubectl rollout status deployment/keda-operator \
        --namespace "${KEDA_NAMESPACE}" \
        --timeout=120s >/dev/null 2>&1

    if [[ $? -eq 0 ]]; then
        log::success "KEDA operator is running"
    else
        log::err "KEDA operator failed to become ready"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# keda::verify — Verify KEDA is running and healthy
# Globals: KEDA_NAMESPACE
# -----------------------------------------------------------------------------
keda::verify() {
    log::submsg "Checking KEDA pods..."

    local pod_count
    pod_count=$(kubectl get pods --namespace "${KEDA_NAMESPACE}" \
        -l app.kubernetes.io/instance=keda \
        --field-selector=status.phase=Running \
        --no-headers 2>/dev/null | wc -l)

    if [[ "${pod_count}" -gt 0 ]]; then
        log::success "KEDA: ${pod_count} pod(s) running"
    else
        log::err "KEDA: No running pods found in namespace ${KEDA_NAMESPACE}"
        return 1
    fi

    return 0
}

# -----------------------------------------------------------------------------
# keda::cleanup — Remove KEDA installation
# Globals: KEDA_NAMESPACE
# -----------------------------------------------------------------------------
keda::cleanup() {
    log::msg "Removing KEDA..."
    helm uninstall keda --namespace "${KEDA_NAMESPACE}" --wait --timeout 120s 2>/dev/null || true
    log::success "KEDA removed"
}
