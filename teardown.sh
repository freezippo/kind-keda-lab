#!/usr/bin/env bash
# =============================================================================
# teardown.sh — Cleanup script for Kind-KEDA Lab Environment
# Deletes the kind cluster and cleans up Docker resources.
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Source configuration and libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/logging.sh"

# -----------------------------------------------------------------------------
# Main teardown
# -----------------------------------------------------------------------------
main() {
    log::section "Kind-KEDA Lab Environment — Teardown"

    # --- Delete kind cluster ---
    cluster::delete

    # --- Clean up Docker resources ---
    docker::cleanup

    log::section "Teardown Complete"
    log::success "All resources cleaned up"
}

# -----------------------------------------------------------------------------
# Cluster deletion
# -----------------------------------------------------------------------------
cluster::delete() {
    log::msg "Deleting kind cluster '${CLUSTER_NAME}'..."

    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null
        if [[ $? -eq 0 ]]; then
            log::success "Cluster '${CLUSTER_NAME}' deleted"
        else
            log::err "Failed to delete cluster '${CLUSTER_NAME}'"
        fi
    else
        log::warn "Cluster '${CLUSTER_NAME}' does not exist, skipping"
    fi
}

# -----------------------------------------------------------------------------
# Docker cleanup
# -----------------------------------------------------------------------------
docker::cleanup() {
    log::msg "Cleaning up Docker resources..."

    # Remove workload image
    if docker image inspect "${WORKLOAD_IMAGE}:${WORKLOAD_IMAGE_TAG}" &>/dev/null; then
        docker rmi "${WORKLOAD_IMAGE}:${WORKLOAD_IMAGE_TAG}" 2>/dev/null || true
        log::submsg "Removed workload image"
    fi

    # Remove dangling images
    docker image prune -f >/dev/null 2>&1 || true
    log::submsg "Cleaned dangling images"

    log::success "Docker cleanup complete"
}

# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
main "$@"
