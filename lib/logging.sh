#!/usr/bin/env bash
# =============================================================================
# Logging library for Kind-KEDA Lab Environment
# Provides consistent, colorized logging functions for all shell scripts.
# =============================================================================

# Color codes
readonly COLOR_RESET='\033[0m'
readonly COLOR_BOLD='\033[1m'
readonly COLOR_RED='\033[31m'
readonly COLOR_GREEN='\033[32m'
readonly COLOR_YELLOW='\033[33m'
readonly COLOR_BLUE='\033[34m'
readonly COLOR_CYAN='\033[36m'

# -----------------------------------------------------------------------------
# log::msg — Print a primary message (bold cyan)
# Usage: log::msg "Creating kind cluster..."
# -----------------------------------------------------------------------------
log::msg() {
    local msg="${1:-}"
    if [[ -n "$msg" ]]; then
        echo -e "${COLOR_BOLD}${COLOR_CYAN}[INFO]${COLOR_RESET} ${msg}"
    fi
}

# -----------------------------------------------------------------------------
# log::submsg — Print a sub/indented message (bold blue)
# Usage: log::submsg "Waiting for pods to be ready..."
# -----------------------------------------------------------------------------
log::submsg() {
    local msg="${1:-}"
    if [[ -n "$msg" ]]; then
        echo -e "  ${COLOR_BLUE}[···]${COLOR_RESET} ${msg}"
    fi
}

# -----------------------------------------------------------------------------
# log::err — Print an error message (bold red) to stderr
# Usage: log::err "Docker is not running"
# -----------------------------------------------------------------------------
log::err() {
    local msg="${1:-}"
    if [[ -n "$msg" ]]; then
        echo -e "${COLOR_BOLD}${COLOR_RED}[ERROR]${COLOR_RESET} ${msg}" >&2
    fi
}

# -----------------------------------------------------------------------------
# log::success — Print a success message (bold green)
# Usage: log::success "Cluster created successfully"
# -----------------------------------------------------------------------------
log::success() {
    local msg="${1:-}"
    if [[ -n "$msg" ]]; then
        echo -e "${COLOR_BOLD}${COLOR_GREEN}[OK]${COLOR_RESET} ${msg}"
    fi
}

# -----------------------------------------------------------------------------
# log::warn — Print a warning message (bold yellow)
# Usage: log::warn "This will delete all data"
# -----------------------------------------------------------------------------
log::warn() {
    local msg="${1:-}"
    if [[ -n "$msg" ]]; then
        echo -e "${COLOR_BOLD}${COLOR_YELLOW}[WARN]${COLOR_RESET} ${msg}"
    fi
}

# -----------------------------------------------------------------------------
# log::section — Print a section header (bold, underlined)
# Usage: log::section "Phase 1: Setup"
# -----------------------------------------------------------------------------
log::section() {
    local msg="${1:-}"
    if [[ -n "$msg" ]]; then
        echo ""
        echo -e "${COLOR_BOLD}${COLOR_CYAN}============================================${COLOR_RESET}"
        echo -e "${COLOR_BOLD}${COLOR_CYAN}  ${msg}${COLOR_RESET}"
        echo -e "${COLOR_BOLD}${COLOR_CYAN}============================================${COLOR_RESET}"
        echo ""
    fi
}
