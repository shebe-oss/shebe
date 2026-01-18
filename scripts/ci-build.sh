#!/usr/bin/env bash
#----------------------------------------------------------
# Shebe CI Build Script (Native Builds)
#
# Builds release binaries using the native toolchain.
# Alpine image produces static musl binaries.
# Debian image produces dynamic glibc binaries.
#
# Usage:
#   ./scripts/ci-build.sh
#
# Environment variables:
#   CI_PROJECT_DIR    - Repository root (GitLab CI predefined, auto-detected locally)
#   SHEBE_SERVICE_DIR - Path to shebe-server (default: services/shebe-server)
#   RELEASE_DIR       - Output directory (default: releases)
#   BUILD_MODE        - Build mode: "static" or "dynamic" (auto-detected locally)
#   ARTIFACT_SUFFIX   - Tarball suffix (required in CI, auto-detected locally)
#
# Outputs:
#   releases/shebe-v{VERSION}-{ARTIFACT_SUFFIX}.tar.gz
#   releases/shebe-v{VERSION}-{ARTIFACT_SUFFIX}.tar.gz.sha256
#----------------------------------------------------------
set -euo pipefail

# Use CI_PROJECT_DIR in GitLab CI, otherwise calculate from script location
if [[ -n "${CI_PROJECT_DIR:-}" ]]; then
    REPO_ROOT="${CI_PROJECT_DIR}"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

# Configuration
SHEBE_SERVICE_DIR="${SHEBE_SERVICE_DIR:-services/shebe-server}"
RELEASE_DIR="${RELEASE_DIR:-releases}"
CARGO_TOML="${REPO_ROOT}/${SHEBE_SERVICE_DIR}/Cargo.toml"

# Binaries to include in tarballs
BINARIES=("shebe" "shebe-mcp")

#----------------------------------------------------------
# Functions
#----------------------------------------------------------

log() {
    echo "[ci-build] $*"
}

error() {
    echo "[ci-build] ERROR: $*" >&2
    exit 1
}

extract_version() {
    if [[ ! -f "${CARGO_TOML}" ]]; then
        error "Cargo.toml not found at ${CARGO_TOML}"
    fi
    grep '^version' "${CARGO_TOML}" | head -1 | sed 's/.*"\(.*\)".*/\1/'
}

# Detect if running on musl-based system (Alpine)
is_musl_system() {
    # Check for Alpine release file
    if [[ -f /etc/alpine-release ]]; then
        return 0
    fi
    # Check if libc is musl
    if ldd --version 2>&1 | grep -qi musl; then
        return 0
    fi
    return 1
}

# Build using native toolchain and create tarball
build_native() {
    local suffix="$1"
    local version="$2"
    local release_path="$3"
    local mode="${BUILD_MODE:-dynamic}"

    log "Building with native toolchain (mode: ${mode})"

    # Native build - no target specification needed
    cargo build --release

    # Native builds go to target/release
    local target_dir="target/release"

    # Verify binaries exist
    for binary in "${BINARIES[@]}"; do
        if [[ ! -f "${target_dir}/${binary}" ]]; then
            error "Binary not found: ${target_dir}/${binary}"
        fi
        log "Built: ${binary} ($(du -h "${target_dir}/${binary}" | cut -f1))"
    done

    # Show linking info for verification
    log "Checking linking:"
    if command -v ldd &> /dev/null; then
        ldd "${target_dir}/${BINARIES[0]}" 2>&1 || log "  (static binary - no dynamic dependencies)"
    fi

    # Create tarball
    local tarball_name="shebe-v${version}-${suffix}.tar.gz"
    log "Creating tarball: ${tarball_name}"
    tar -czf "${release_path}/${tarball_name}" \
        -C "${target_dir}" \
        "${BINARIES[@]}"

    # Generate checksum
    log "Generating SHA256 checksum for ${tarball_name}"
    (cd "${release_path}" && sha256sum "${tarball_name}" > "${tarball_name}.sha256")

    log "Build complete"
}

#----------------------------------------------------------
# Main
#----------------------------------------------------------

main() {
    log "Starting build process"
    log "Repository root: ${REPO_ROOT}"

    # Extract version
    VERSION=$(extract_version)
    if [[ -z "${VERSION}" ]]; then
        error "Failed to extract version from Cargo.toml"
    fi
    log "Version: ${VERSION}"

    # Change to service directory
    cd "${REPO_ROOT}/${SHEBE_SERVICE_DIR}"
    log "Working directory: $(pwd)"

    # Display toolchain info
    log "Rust toolchain:"
    rustc --version
    cargo --version

    # Create release directory
    local release_path="${REPO_ROOT}/${RELEASE_DIR}"
    mkdir -p "${release_path}"

    # Determine build mode and artifact suffix
    local suffix="${ARTIFACT_SUFFIX:-}"
    local mode="${BUILD_MODE:-}"

    if [[ -z "${suffix}" ]]; then
        # Auto-detect based on system
        if is_musl_system; then
            suffix="linux-x86_64-musl"
            mode="static"
            log "Detected musl system (Alpine)"
        else
            suffix="linux-x86_64"
            mode="dynamic"
            log "Detected glibc system (Debian/Ubuntu)"
        fi
    fi

    # Export BUILD_MODE for the build function
    export BUILD_MODE="${mode}"

    log "Build mode: ${mode}"
    log "Artifact suffix: ${suffix}"

    # Build native binary
    build_native "${suffix}" "${VERSION}" "${release_path}"

    # Display results
    log "Artifacts:"
    ls -la "${release_path}/"

    log "Checksums:"
    cat "${release_path}"/*.sha256

    # Export version for downstream jobs
    if [[ -n "${CI:-}" ]]; then
        echo "VERSION=${VERSION}" >> "${REPO_ROOT}/build.env"
        log "Exported VERSION=${VERSION} to build.env"
    fi

    log "Build successful"
}

main "$@"
