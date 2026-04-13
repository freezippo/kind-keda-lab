#!/usr/bin/env bash
# =============================================================================
# run-tests.sh — Run all code-level tests for Kind-KEDA Lab
# Tests: Python unit tests, shellcheck, kubeconform, k6 syntax validation
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Source configuration and libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"
source "${SCRIPT_DIR}/lib/logging.sh"

# Track overall test status
TESTS_PASSED=true
TEST_RESULTS=()

# -----------------------------------------------------------------------------
# Python Unit Tests
# -----------------------------------------------------------------------------
test_python() {
    log::section "Running Python Unit Tests"

    if ! command -v python3 &>/dev/null; then
        log::err "python3 not found"
        TESTS_PASSED=false
        TEST_RESULTS+=("Python: FAILED (python3 not found)")
        return 1
    fi

    if ! command -v pip3 &>/dev/null; then
        log::err "pip3 not found"
        TESTS_PASSED=false
        TEST_RESULTS+=("Python: FAILED (pip3 not found)")
        return 1
    fi

    # Install test dependencies
    log::msg "Installing test dependencies..."
    pip3 install -q -r "${SCRIPT_DIR}/workload/requirements.txt"

    # Run pytest
    log::msg "Running pytest..."
    if PYTHONPATH="${SCRIPT_DIR}/workload/src" python3 -m pytest "${SCRIPT_DIR}/workload/tests/" \
        -v --tb=short --cov="${SCRIPT_DIR}/workload/src" --cov-report=term-missing; then
        log::success "Python unit tests passed"
        TEST_RESULTS+=("Python: PASSED")
        return 0
    else
        log::err "Python unit tests failed"
        TESTS_PASSED=false
        TEST_RESULTS+=("Python: FAILED")
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Shell Script Validation (shellcheck)
# -----------------------------------------------------------------------------
test_shellcheck() {
    log::section "Running ShellCheck Validation"

    if ! command -v shellcheck &>/dev/null; then
        log::warn "shellcheck not installed, skipping"
        TEST_RESULTS+=("ShellCheck: SKIPPED (not installed)")
        return 0
    fi

    local scripts=()
    scripts+=("${SCRIPT_DIR}/setup.sh")
    scripts+=("${SCRIPT_DIR}/teardown.sh")
    scripts+=("${SCRIPT_DIR}/verify.sh")

    # Add lib scripts
    for script in "${SCRIPT_DIR}"/lib/*.sh; do
        if [[ -f "$script" ]]; then
            scripts+=("$script")
        fi
    done

    # Add test runner scripts if they exist
    if [[ -f "${SCRIPT_DIR}/run-tests.sh" ]]; then
        scripts+=("${SCRIPT_DIR}/run-tests.sh")
    fi
    if [[ -f "${SCRIPT_DIR}/run-scaling-tests.sh" ]]; then
        scripts+=("${SCRIPT_DIR}/run-scaling-tests.sh")
    fi

    local failed=0
    for script in "${scripts[@]}"; do
        log::msg "Checking: $(basename "$script")"
        if ! shellcheck "$script"; then
            failed=$((failed + 1))
        fi
    done

    if [[ $failed -eq 0 ]]; then
        log::success "ShellCheck validation passed (${#scripts[@]} scripts)"
        TEST_RESULTS+=("ShellCheck: PASSED")
        return 0
    else
        log::err "ShellCheck validation failed (${failed}/${#scripts[@]} scripts)"
        TESTS_PASSED=false
        TEST_RESULTS+=("ShellCheck: FAILED")
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Kubernetes Manifest Validation (kubeconform)
# -----------------------------------------------------------------------------
test_kubeconform() {
    log::section "Running Kubernetes Manifest Validation"

    if ! command -v kubeconform &>/dev/null; then
        log::warn "kubeconform not installed, skipping"
        TEST_RESULTS+=("Kubeconform: SKIPPED (not installed)")
        return 0
    fi

    local manifest_dir="${SCRIPT_DIR}/manifests"
    local failed=0
    local checked=0

    log::msg "Validating manifests in: ${manifest_dir}"

    for manifest in "${manifest_dir}"/**/*.yaml; do
        if [[ -f "$manifest" ]]; then
            log::msg "Validating: $(basename "$manifest")"
            if kubeconform -strict -kubernetes-version "1.33.1" "$manifest"; then
                checked=$((checked + 1))
            else
                log::err "Invalid manifest: $(basename "$manifest")"
                failed=$((failed + 1))
            fi
        fi
    done

    if [[ $failed -eq 0 ]]; then
        log::success "Manifest validation passed (${checked} manifests)"
        TEST_RESULTS+=("Kubeconform: PASSED")
        return 0
    else
        log::err "Manifest validation failed (${failed}/${checked} manifests invalid)"
        TESTS_PASSED=false
        TEST_RESULTS+=("Kubeconform: FAILED")
        return 1
    fi
}

# -----------------------------------------------------------------------------
# k6 Script Syntax Validation (dry-run)
# -----------------------------------------------------------------------------
test_k6_syntax() {
    log::section "Running k6 Script Syntax Validation"

    if ! command -v k6 &>/dev/null; then
        log::warn "k6 not installed, skipping syntax validation"
        TEST_RESULTS+=("k6 Syntax: SKIPPED (not installed)")
        return 0
    fi

    local script_dir="${SCRIPT_DIR}/k6/scripts"
    local failed=0
    local checked=0

    log::msg "Validating k6 scripts in: ${script_dir}"

    for script in "${script_dir}"/*.js; do
        if [[ -f "$script" ]]; then
            log::msg "Checking: $(basename "$script")"
            if k6 run --paused --duration 1s "$script" >/dev/null 2>&1; then
                log::success "  $(basename "$script"): syntax OK"
                checked=$((checked + 1))
            else
                log::err "  $(basename "$script"): syntax error"
                failed=$((failed + 1))
            fi
        fi
    done

    if [[ $failed -eq 0 ]]; then
        log::success "k6 syntax validation passed (${checked} scripts)"
        TEST_RESULTS+=("k6 Syntax: PASSED")
        return 0
    else
        log::err "k6 syntax validation failed (${failed}/${checked} scripts)"
        TESTS_PASSED=false
        TEST_RESULTS+=("k6 Syntax: FAILED")
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Main: Run all tests and report
# -----------------------------------------------------------------------------
main() {
    log::section "Kind-KEDA Lab — Code-Level Tests"

    # Run all test categories (continue on failure)
    test_python || true
    test_shellcheck || true
    test_kubeconform || true
    test_k6_syntax || true

    # Print summary
    log::section "Test Summary"
    for result in "${TEST_RESULTS[@]}"; do
        if [[ "$result" == *"PASSED"* ]]; then
            log::success "$result"
        elif [[ "$result" == *"SKIPPED"* ]]; then
            log::warn "$result"
        else
            log::err "$result"
        fi
    done

    # Exit with appropriate code
    if [[ "$TESTS_PASSED" == true ]]; then
        log::success "All tests passed!"
        exit 0
    else
        log::err "Some tests failed"
        exit 1
    fi
}

main "$@"
