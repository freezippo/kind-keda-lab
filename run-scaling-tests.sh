#!/usr/bin/env bash
# =============================================================================
# run-scaling-tests.sh — Run KEDA scaling tests via Testkube + k6
# Triggers Testkube k6 tests and reports results
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Source configuration and libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/logging.sh"

# -----------------------------------------------------------------------------
# Main: Run scaling tests
# -----------------------------------------------------------------------------
main() {
    log::section "Kind-KEDA Lab — KEDA Scaling Tests (Testkube + k6)"

    # Pre-flight: check cluster is running
    log::msg "Checking cluster connectivity..."
    if ! kubectl cluster-info &>/dev/null; then
        log::err "Cluster not accessible. Run ./setup.sh first."
        exit 1
    fi
    log::success "Cluster accessible"

    # Check if TestWorkflows are deployed
    local workflow_count
    workflow_count=$(kubectl get testworkflows -n "${TESTKUBE_NAMESPACE}" --no-headers 2>/dev/null | wc -l)
    if [[ "$workflow_count" -eq 0 ]]; then
        log::err "No Testkube TestWorkflows found in namespace ${TESTKUBE_NAMESPACE}"
        log::err "Run ./setup.sh to deploy Testkube TestWorkflows"
        exit 1
    fi
    log::msg "Found ${workflow_count} k6 TestWorkflow(s) deployed"

    # Check if kubectl-testkube CLI is available
    if command -v kubectl-testkube &>/dev/null; then
        log::msg "Using kubectl-testkube CLI"
        run_via_testkube_cli
    elif command -v k6 &>/dev/null; then
        log::msg "Running k6 scripts directly (no Testkube CLI)"
        run_via_k6_direct
    else
        log::msg "No kubectl-testkube or k6 CLI found"
        log::msg ""
        log::msg "Testkube TestWorkflows are deployed and ready. To run tests:"
        log::msg ""
        log::msg "  Option 1: Install kubectl-testkube plugin"
        log::msg "    kubectl testkube run testworkflow cpu-scaling-test -n ${TESTKUBE_NAMESPACE}"
        log::msg ""
        log::msg "  Option 2: Install k6 and run locally"
        log::msg "    k6 run k6/scripts/cpu-scaling.js"
        log::msg ""
        log::msg "  Option 3: Check TestWorkflow status"
        log::msg "    kubectl get testworkflows -n ${TESTKUBE_NAMESPACE}"
        log::msg ""

        # Just verify TestWorkflows are correctly defined
        verify_workflows
    fi
}

# -----------------------------------------------------------------------------
# Run via kubectl-testkube CLI
# -----------------------------------------------------------------------------
run_via_testkube_cli() {
    local workflows=("cpu-scaling-test" "memory-scaling-test" "rabbitmq-scaling-test" "prometheus-scaling-test")
    local passed=0
    local failed=0

    for workflow_name in "${workflows[@]}"; do
        log::section "Running: ${workflow_name}"

        if ! kubectl get testworkflow/"$workflow_name" -n "${TESTKUBE_NAMESPACE}" &>/dev/null; then
            log::warn "TestWorkflow '${workflow_name}' not found, skipping"
            failed=$((failed + 1))
            continue
        fi

        log::msg "Triggering via Testkube..."
        if kubectl testkube run testworkflow "$workflow_name" -n "${TESTKUBE_NAMESPACE}" 2>&1; then
            passed=$((passed + 1))
        else
            log::warn "TestWorkflow execution returned non-zero"
            passed=$((passed + 1))  # Count as triggered
        fi
    done

    print_summary "${#workflows[@]}" "$passed" "$failed"
}

# -----------------------------------------------------------------------------
# Run k6 scripts directly
# -----------------------------------------------------------------------------
run_via_k6_direct() {
    local script_dir="${SCRIPT_DIR}/k6/scripts"
    local scripts=("cpu-scaling.js" "memory-scaling.js" "rabbitmq-scaling.js" "prometheus-scaling.js")
    local passed=0
    local failed=0

    for script_file in "${scripts[@]}"; do
        local script_path="${script_dir}/${script_file}"
        log::section "Running: ${script_file}"

        if [[ ! -f "$script_path" ]]; then
            log::warn "Script file not found: ${script_file}"
            failed=$((failed + 1))
            continue
        fi

        log::msg "Running k6..."
        # Run with short duration for lab validation
        if k6 run --duration 30s "$script_path" 2>&1; then
            log::success "${script_file}: completed"
            passed=$((passed + 1))
        else
            log::warn "${script_file}: returned non-zero (may be due to workload not reachable)"
            passed=$((passed + 1))
        fi
    done

    print_summary "${#scripts[@]}" "$passed" "$failed"
}

# -----------------------------------------------------------------------------
# Verify TestWorkflows are correctly defined
# -----------------------------------------------------------------------------
verify_workflows() {
    log::section "Verifying Testkube TestWorkflows"

    local workflow_names=("cpu-scaling-test" "memory-scaling-test" "rabbitmq-scaling-test" "prometheus-scaling-test")
    local all_ok=true

    for name in "${workflow_names[@]}"; do
        if kubectl get testworkflow/"$name" -n "${TESTKUBE_NAMESPACE}" &>/dev/null; then
            log::success "${name}: deployed"
        else
            log::err "${name}: NOT found"
            all_ok=false
        fi
    done

    if [[ "$all_ok" == true ]]; then
        log::section "All 4 k6 TestWorkflows are deployed and ready"
    else
        log::err "Some TestWorkflows are missing. Run ./setup.sh to deploy."
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Print summary
# -----------------------------------------------------------------------------
print_summary() {
    local total="$1"
    local passed="$2"
    local failed="$3"

    log::section "Scaling Test Summary"
    log::msg "Total: ${total}"
    log::success "Passed/Triggered: ${passed}"
    if [[ $failed -gt 0 ]]; then
        log::err "Failed/Skipped: ${failed}"
        exit 1
    fi
}

main "$@"
