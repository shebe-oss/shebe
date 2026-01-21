#!/usr/bin/env bash
#----------------------------------------------------------
# Shebe CI GitHub Release Script
#
# Creates a draft GitHub release and uploads Linux artifacts.
# Used by Zed extension which requires GitHub releases.
# Triggers GitHub Actions for macOS builds after upload.
#
# Usage:
#   ./scripts/ci-github-release.sh              # Run in GitLab CI
#   ./scripts/ci-github-release.sh --preview    # Local preview (no API calls)
#   ./scripts/ci-github-release.sh --preview v0.6.0  # Preview specific version
#
# Required environment variables (GitLab CI):
#   CI_PROJECT_DIR      - Repository root directory
#   CI_COMMIT_TAG       - Git tag (e.g., v0.6.0)
#   CI_PIPELINE_ID      - Pipeline ID (for tracking)
#   SHEBE_GITHUB_TOKEN  - GitHub Personal Access Token with repo scope
#   SHEBE_GITHUB_REPO   - GitHub repository (default: rhobimd-oss/shebe)
#
# Optional environment variables:
#   RELEASE_DIR         - Directory containing release artifacts (default: releases)
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
RELEASE_DIR="${RELEASE_DIR:-releases}"
SHEBE_GITHUB_REPO="${SHEBE_GITHUB_REPO:-rhobimd-oss/shebe}"
GITHUB_API_URL="https://api.github.com"
GITHUB_UPLOAD_URL="https://uploads.github.com"
PREVIEW_MODE=false
TRIGGER_MACOS=true

#----------------------------------------------------------
# Functions
#----------------------------------------------------------

log() {
    echo "[ci-github-release] $*"
}

error() {
    echo "[ci-github-release] ERROR: $*" >&2
    exit 1
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --preview [VERSION]  Preview release locally (no API calls)"
    echo "                       VERSION defaults to version from Cargo.toml"
    echo "  --no-trigger         Skip triggering GitHub Actions for macOS builds"
    echo "                       (use when macOS is triggered separately)"
    echo ""
    echo "Examples:"
    echo "  $0                   # Run in GitLab CI (requires CI variables)"
    echo "  $0 --no-trigger      # Create release without triggering macOS builds"
    echo "  $0 --preview         # Preview with version from Cargo.toml"
    echo "  $0 --preview v0.6.0  # Preview specific version"
    exit 0
}

setup_preview_environment() {
    local version="${1:-}"

    # Get version from Cargo.toml if not provided
    if [[ -z "${version}" ]]; then
        local cargo_toml="${REPO_ROOT}/services/shebe-server/Cargo.toml"
        if [[ -f "${cargo_toml}" ]]; then
            version="v$(grep '^version = ' "${cargo_toml}" | head -1 | sed 's/version = "\(.*\)"/\1/')"
        else
            error "No version provided and Cargo.toml not found"
        fi
    fi

    # Ensure version starts with 'v'
    if [[ "${version}" != v* ]]; then
        version="v${version}"
    fi

    # Set mock CI variables for preview
    export CI_COMMIT_TAG="${version}"
    export CI_PIPELINE_ID="preview-12345"
    export SHEBE_GITHUB_TOKEN="preview-token"
    export SHEBE_GITHUB_REPO="rhobimd-oss/shebe"

    log "Preview mode enabled for ${CI_COMMIT_TAG}"
}

validate_environment() {
    log "Validating environment..."

    if [[ "${PREVIEW_MODE}" == "true" ]]; then
        log "Preview mode - skipping CI variable validation"
        return 0
    fi

    # Get version from Cargo.toml as the source of truth
    local cargo_toml="${REPO_ROOT}/services/shebe-server/Cargo.toml"
    if [[ -f "${cargo_toml}" ]]; then
        local cargo_version
        cargo_version=$(grep '^version = ' "${cargo_toml}" | head -1 | sed 's/version = "\(.*\)"/\1/')
        export CI_COMMIT_TAG="v${cargo_version}"
        log "Version from Cargo.toml: ${CI_COMMIT_TAG}"
    else
        error "Cargo.toml not found at ${cargo_toml}"
    fi

    if [[ -z "${SHEBE_GITHUB_TOKEN:-}" ]]; then
        error "SHEBE_GITHUB_TOKEN is not set. Add it to GitLab CI/CD variables (masked, protected)."
    fi

    if [[ -z "${SHEBE_GITHUB_REPO:-}" ]]; then
        error "SHEBE_GITHUB_REPO is not set."
    fi

    log "Environment validated"
    log "  GitHub repo: ${SHEBE_GITHUB_REPO}"
    log "  Version: ${CI_COMMIT_TAG}"
}

# Check if GitHub release already exists
check_release_exists() {
    local version="$1"

    log "Checking if release ${version} already exists..."

    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Accept: application/vnd.github+json" \
        -H "Authorization: Bearer ${SHEBE_GITHUB_TOKEN}" \
        "${GITHUB_API_URL}/repos/${SHEBE_GITHUB_REPO}/releases/tags/${version}")

    if [[ "${http_code}" == "200" ]]; then
        return 0  # exists
    else
        return 1  # does not exist
    fi
}

# Get release ID for existing release
get_release_id() {
    local version="$1"

    local response
    response=$(curl -s \
        -H "Accept: application/vnd.github+json" \
        -H "Authorization: Bearer ${SHEBE_GITHUB_TOKEN}" \
        "${GITHUB_API_URL}/repos/${SHEBE_GITHUB_REPO}/releases/tags/${version}")

    echo "${response}" | jq -r '.id'
}

# Create a new draft release
create_draft_release() {
    local version="$1"

    log "Creating draft release ${version}..."

    local response
    response=$(curl -s -X POST \
        -H "Accept: application/vnd.github+json" \
        -H "Authorization: Bearer ${SHEBE_GITHUB_TOKEN}" \
        "${GITHUB_API_URL}/repos/${SHEBE_GITHUB_REPO}/releases" \
        -d "{
            \"tag_name\": \"${version}\",
            \"name\": \"Shebe ${version}\",
            \"body\": \"Release ${version}. See [GitLab release](https://gitlab.com/rhobimd-oss/shebe/-/releases/${version}) for changelog.\",
            \"draft\": true,
            \"prerelease\": false
        }")

    local release_id
    release_id=$(echo "${response}" | jq -r '.id')

    if [[ "${release_id}" == "null" ]] || [[ -z "${release_id}" ]]; then
        error "Failed to create release: ${response}"
    fi

    log "Created draft release (ID: ${release_id})"
    echo "${release_id}"
}

# Delete existing asset if present (for re-runs)
delete_existing_asset() {
    local release_id="$1"
    local filename="$2"

    local existing_asset
    existing_asset=$(curl -s \
        -H "Accept: application/vnd.github+json" \
        -H "Authorization: Bearer ${SHEBE_GITHUB_TOKEN}" \
        "${GITHUB_API_URL}/repos/${SHEBE_GITHUB_REPO}/releases/${release_id}/assets" \
        | jq -r ".[] | select(.name == \"${filename}\") | .id")

    if [[ -n "${existing_asset}" ]] && [[ "${existing_asset}" != "null" ]]; then
        log "Deleting existing asset ${filename} (ID: ${existing_asset})..."
        curl -s -X DELETE \
            -H "Accept: application/vnd.github+json" \
            -H "Authorization: Bearer ${SHEBE_GITHUB_TOKEN}" \
            "${GITHUB_API_URL}/repos/${SHEBE_GITHUB_REPO}/releases/assets/${existing_asset}"
    fi
}

# Upload a single file to the release
upload_asset() {
    local release_id="$1"
    local filepath="$2"
    local filename
    filename=$(basename "${filepath}")

    log "Uploading: ${filename}"

    # Delete existing asset if present (for re-runs)
    delete_existing_asset "${release_id}" "${filename}"

    # Determine content type
    local content_type
    if [[ "${filename}" == *.tar.gz ]]; then
        content_type="application/gzip"
    elif [[ "${filename}" == *.sha256 ]]; then
        content_type="text/plain"
    else
        content_type="application/octet-stream"
    fi

    # Upload asset
    local response
    response=$(curl -s -X POST \
        -H "Accept: application/vnd.github+json" \
        -H "Authorization: Bearer ${SHEBE_GITHUB_TOKEN}" \
        -H "Content-Type: ${content_type}" \
        --data-binary "@${filepath}" \
        "${GITHUB_UPLOAD_URL}/repos/${SHEBE_GITHUB_REPO}/releases/${release_id}/assets?name=${filename}")

    if echo "${response}" | jq -e '.id' > /dev/null 2>&1; then
        log "Uploaded: ${filename}"
    else
        log "WARNING: Upload may have failed for ${filename}"
        log "${response}"
    fi
}

# Upload all artifacts to the release
upload_artifacts() {
    local release_id="$1"
    local release_path="${REPO_ROOT}/${RELEASE_DIR}"

    log "Uploading artifacts from ${release_path}..."

    local count=0
    for artifact in "${release_path}"/*.tar.gz "${release_path}"/*.sha256; do
        if [[ -f "${artifact}" ]]; then
            upload_asset "${release_id}" "${artifact}"
            ((count++))
        fi
    done

    if [[ ${count} -eq 0 ]]; then
        error "No artifacts found in ${release_path}"
    fi

    log "Uploaded ${count} artifacts"
}

# Trigger GitHub Actions for macOS builds
trigger_github_actions() {
    local version="$1"
    local release_id="$2"

    log "Triggering GitHub Actions for macOS build..."

    local response
    response=$(curl -s -X POST \
        -H "Accept: application/vnd.github+json" \
        -H "Authorization: Bearer ${SHEBE_GITHUB_TOKEN}" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "${GITHUB_API_URL}/repos/${SHEBE_GITHUB_REPO}/dispatches" \
        -d "{
            \"event_type\": \"build-macos\",
            \"client_payload\": {
                \"version\": \"${version}\",
                \"ref\": \"${version}\",
                \"release_id\": \"${release_id}\",
                \"gitlab_pipeline\": \"${CI_PIPELINE_ID:-unknown}\"
            }
        }")

    # repository_dispatch returns 204 No Content on success (empty response)
    log "Triggered GitHub Actions for macOS build"
    log "Check progress at: https://github.com/${SHEBE_GITHUB_REPO}/actions"
}

# Save release ID for downstream jobs
save_release_id() {
    local release_id="$1"
    local env_file="${REPO_ROOT}/github_release.env"

    echo "GITHUB_RELEASE_ID=${release_id}" > "${env_file}"
    log "Saved release ID to ${env_file}"
}

#----------------------------------------------------------
# Main
#----------------------------------------------------------

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --preview)
                PREVIEW_MODE=true
                shift
                # Check if next arg is a version (not another flag)
                if [[ $# -gt 0 && "$1" != -* ]]; then
                    setup_preview_environment "$1"
                    shift
                else
                    setup_preview_environment ""
                fi
                ;;
            --no-trigger)
                TRIGGER_MACOS=false
                shift
                ;;
            --help|-h)
                usage
                ;;
            *)
                error "Unknown argument: $1"
                ;;
        esac
    done

    log "Starting GitHub release process"
    log "Repository: ${SHEBE_GITHUB_REPO}"

    cd "${REPO_ROOT}"

    # Validate environment
    validate_environment

    local version="${CI_COMMIT_TAG}"
    log "Version: ${version}"

    if [[ "${PREVIEW_MODE}" == "true" ]]; then
        log "Preview mode - would perform these actions:"
        echo ""
        echo "1. Check if release ${version} exists on GitHub"
        echo "2. Create draft release if needed"
        echo "3. Upload artifacts from ${RELEASE_DIR}/:"
        shopt -s nullglob
        for artifact in "${REPO_ROOT}/${RELEASE_DIR}"/*.tar.gz "${REPO_ROOT}/${RELEASE_DIR}"/*.sha256; do
            echo "   - $(basename "${artifact}")"
        done
        shopt -u nullglob
        echo "4. Save release ID to github_release.env"
        if [[ "${TRIGGER_MACOS}" == "true" ]]; then
            echo "5. Trigger GitHub Actions for macOS build"
        else
            echo "5. (skipped) Trigger GitHub Actions (--no-trigger)"
        fi
        echo ""
        log "Preview complete"
        return 0
    fi

    # Check if release exists
    local release_id
    if check_release_exists "${version}"; then
        log "Release ${version} already exists"
        release_id=$(get_release_id "${version}")
    else
        release_id=$(create_draft_release "${version}")
    fi

    log "Release ID: ${release_id}"

    # Upload artifacts
    upload_artifacts "${release_id}"

    # Save release ID for downstream jobs
    save_release_id "${release_id}"

    # Trigger GitHub Actions for macOS builds (unless --no-trigger)
    if [[ "${TRIGGER_MACOS}" == "true" ]]; then
        trigger_github_actions "${version}" "${release_id}"
    else
        log "Skipping GitHub Actions trigger (--no-trigger specified)"
    fi

    log "GitHub release process complete"
    log "Release URL: https://github.com/${SHEBE_GITHUB_REPO}/releases/tag/${version}"
}

main "$@"
