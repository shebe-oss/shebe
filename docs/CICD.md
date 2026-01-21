# Shebe CI/CD Pipeline

**Version:** 1.1
**Updated:** 2026-01-21

This document describes the CI/CD pipeline for building, testing and releasing Shebe.

---

## Overview

Shebe uses a dual-platform CI/CD strategy:

- **GitLab CI:** Primary CI/CD for testing, Linux builds and GitLab releases
- **GitHub Actions:** macOS builds (requires native Apple runners)

```
                            Tag Push (v*.*.*)
                                  |
                                  v
+------------------------------------------------------------------+
|                         GitLab CI                                |
|                                                                  |
|  +-----------+                                                   |
|  | test:shebe|  (MR pipelines only, currently disabled)          |
|  +-----------+                                                   |
|                                                                  |
|  BUILD STAGE (parallel):                                         |
|  +---------------+        +---------------+                      |
|  | build:linux   |        | build:macos   |                      |
|  | (2x parallel) |        | (triggers GH) |----+                 |
|  +-------+-------+        +---------------+    |                 |
|          |                                     |                 |
|          v                                     |                 |
|  RELEASE STAGE:                                |                 |
|  +---------------+  +---------------+          |                 |
|  | package:mcpb  |  | release:shebe |          |                 |
|  | (MCPB bundle) |  | (GitLab rel.) |          |                 |
|  +---------------+  +---------------+          |                 |
|                                                                  |
+------------------------------------------------------------------+
                                                 |
                         repository_dispatch     | (from build:macos)
                                                 v
+------------------------------------------------------------------+
|                       GitHub Actions                             |
|                                                                  |
|  +-------------------+     +-------------------+                  |
|  | Build macOS x86_64| --> | Upload to Release |                  |
|  | Build macOS arm64 |     | Publish Release   |                  |
|  +-------------------+     +-------------------+                  |
|                                                                  |
+------------------------------------------------------------------+
                                  |
                                  v
                        GitHub Release (published)
                        - darwin-x86_64.tar.gz
                        - darwin-aarch64.tar.gz
```

**Note:** The `release:github` job is currently disabled. Linux artifacts are uploaded
to GitLab Package Registry only. GitHub releases contain macOS binaries only.

---

## Pipeline Stages

### Stage 1: prep

**Job:** `dummy:job`

Placeholder job for merge request pipelines. Ensures pipelines always have at least one job.

| Attribute | Value |
|-----------|-------|
| Trigger | MR pipelines only |
| Duration | < 1 second |
| Purpose | Prevent empty pipeline errors |

---

### Stage 2: test

**Job:** `test:shebe` (currently disabled)

Runs on merge requests and main branch pushes when Rust files change.

| Check | Tool | Threshold |
|-------|------|-----------|
| Format | `cargo fmt --check` | No differences |
| Lint | `cargo clippy` | Zero warnings |
| Tests | `cargo nextest` | All passing |
| Coverage | `cargo tarpaulin` | >= 60% |

**Triggers:**
- Merge request with changes to `Cargo.toml` or `Cargo.lock`
- Push to main with Rust file changes

**Artifacts:**
- `cobertura.xml` - Coverage report (Cobertura format)

**Status:** Currently commented out in `.gitlab-ci.yml`. Tests are run locally before commits.

---

### Stage 3: build

Two parallel jobs run in this stage:

**Job:** `build:linux`

Builds Linux release binaries using parallel matrix strategy.

| Variant | Image | Output | Use Case |
|---------|-------|--------|----------|
| glibc | rust-debian | `shebe-vX.Y.Z-linux-x86_64.tar.gz` | Standard Linux |
| musl | rust-alpine | `shebe-vX.Y.Z-linux-x86_64-musl.tar.gz` | Alpine, MCPB |

**Script:** `scripts/ci-build.sh`

**Current Mode:** Preview/dry-run (`PREVIEW_MODE: true`, `--dry-run` flag)

**Artifacts:**
- `releases/*.tar.gz` - Binary tarballs
- `releases/*.sha256` - Checksums

---

**Job:** `build:macos`

Triggers GitHub Actions to build macOS binaries. Runs in parallel with `build:linux`.

**Actions:**
- Extracts version from `Cargo.toml`
- Triggers `repository_dispatch` event on GitHub
- Passes version and ref to GitHub Actions

**Required Variables:**
- `SHEBE_GITHUB_TOKEN` - GitHub Personal Access Token with repo scope
- `SHEBE_GITHUB_REPO` - Target repository (default: `rhobimd-oss/shebe`)

**Triggers:**
- Tag push matching `v*.*.*`
- Push to main with Cargo.toml/Cargo.lock changes

---

### Stage 4: release

**Job:** `package:mcpb`

Creates MCP Bundle (.mcpb) from the musl static binary.

| Input | Output |
|-------|--------|
| `shebe-vX.Y.Z-linux-x86_64-musl.tar.gz` | `shebe-mcp-vX.Y.Z.mcpb` |

**Script:** `scripts/ci-mcpb.sh`

**Artifacts:**
- `releases/*.mcpb` - MCP Bundle
- `releases/*.mcpb.sha256` - Checksum
- `releases/server.json` - MCP server manifest

---

**Job:** `release:shebe`

Creates GitLab release with changelog and artifact links.

**Script:** `scripts/ci-release.sh`

**Current Mode:** Preview (`PREVIEW_MODE: true`, `--preview` flag)

**Features:**
- Extracts changelog from `CHANGELOG.md`
- Uploads artifacts to GitLab Package Registry
- Creates release with asset links
- Supports `--preview` mode for local testing

**Artifacts:**
- `RELEASE_NOTES.md` - Generated release notes
- `CHANGELOG.md` - Full changelog

---

**Job:** `release:github` (currently disabled)

Creates GitHub release and uploads Linux artifacts.

**Script:** `scripts/ci-github-release.sh --no-trigger`

**Actions:**
1. Creates draft GitHub release (or uses existing)
2. Uploads Linux artifacts to GitHub release
3. Saves release ID to `github_release.env`

Note: macOS builds are triggered separately by `build:macos` job.

**Required Variables:**
- `SHEBE_GITHUB_TOKEN` - GitHub Personal Access Token (masked, protected)

**Artifacts:**
- `github_release.env` - Contains `GITHUB_RELEASE_ID`

**Status:** Currently commented out in `.gitlab-ci.yml`. GitHub releases are created
by the macOS GitHub Actions workflow when triggered.

---

### Stage 5: publish

**Job:** `publish:mcp-registry` (manual, currently disabled)

Publishes to official MCP Registry.

**Script:** `scripts/ci-mcpb-publish.sh`

**Required Variables:**
- `MCP_PRIVATE_KEY` - DNS-based authentication key

---

## GitHub Actions Workflow

**File:** `.github/workflows/release-macos.yml`

Builds macOS binaries on native Apple runners.

### Triggers

| Trigger | Source | Use Case |
|---------|--------|----------|
| `repository_dispatch` | GitLab CI | Production releases |
| `workflow_dispatch` | Manual | Testing |

### Build Matrix

| Target | Runner | Architecture |
|--------|--------|--------------|
| `x86_64-apple-darwin` | macos-13 | Intel |
| `aarch64-apple-darwin` | macos-14 | Apple Silicon |

### Jobs

**Job:** `build`

1. Checkout source at ref/tag
2. Install Rust toolchain
3. Cache cargo registry
4. Build and package via `scripts/ci-github-build.sh`
5. Upload as GitHub Actions artifact

**Script:** `scripts/ci-github-build.sh --target <target>`

The script:
- Extracts version from `Cargo.toml`
- Builds release binary for target
- Creates tarball with SHA256 checksum
- Sets GitHub Actions outputs (`version`, `artifact_name`)

**Job:** `release`

1. Checkout source (for Cargo.toml)
2. Extract version from `Cargo.toml`
3. Download build artifacts
4. Upload to GitHub release (create if manual run)
5. Publish release (remove draft status)

---

## CI/CD Variables

### GitLab CI/CD Variables

| Variable | Type | Scope | Description |
|----------|------|-------|-------------|
| `SHEBE_GITHUB_TOKEN` | Masked, Protected | Tags | GitHub PAT with `repo` scope |
| `SHEBE_GITHUB_REPO` | Variable | All | Target GitHub repository (default: `rhobimd-oss/shebe`) |
| `MCP_PRIVATE_KEY` | Masked, Protected | Tags | MCP Registry auth key |

### Creating GitHub PAT

1. Go to GitHub Settings > Developer settings > Personal access tokens > Fine-grained tokens
2. Create token with:
   - **Repository access:** `rhobimd-oss/shebe`
   - **Permissions:** Contents (read/write), Actions (read/write)
3. Add to GitLab: Settings > CI/CD > Variables
   - Key: `SHEBE_GITHUB_TOKEN`
   - Masked: Yes
   - Protected: Yes

---

## Scripts

All CI scripts support `--preview` mode for local testing.

| Script | Purpose | Platform | Preview |
|--------|---------|----------|---------|
| `scripts/ci-build.sh` | Build Linux binaries, create tarballs | GitLab CI | Yes |
| `scripts/ci-github-build.sh` | Build macOS binaries, create tarballs | GitHub Actions | Yes |
| `scripts/ci-mcpb.sh` | Create MCP Bundle | GitLab CI | Yes |
| `scripts/ci-release.sh` | Create GitLab release | GitLab CI | Yes |
| `scripts/ci-github-release.sh` | Create GitHub release, trigger macOS | GitLab CI | Yes |
| `scripts/ci-mcpb-publish.sh` | Publish to MCP Registry | GitLab CI | Yes |

### Local Testing

```bash
# Preview GitLab Linux build
./scripts/ci-build.sh --preview

# Preview GitHub macOS build (specify target)
./scripts/ci-github-build.sh --target aarch64-apple-darwin --preview
./scripts/ci-github-build.sh --target x86_64-apple-darwin --preview

# Preview GitLab release
./scripts/ci-release.sh --preview

# Preview GitHub release
./scripts/ci-github-release.sh --preview

# Preview specific version
./scripts/ci-release.sh --preview v0.6.0
```

---

## Artifact Naming Convention

```
shebe-{version}-{os}-{arch}[-{variant}].tar.gz
```

| Platform | Artifact Name |
|----------|---------------|
| Linux x86_64 (glibc) | `shebe-v0.6.0-linux-x86_64.tar.gz` |
| Linux x86_64 (musl) | `shebe-v0.6.0-linux-x86_64-musl.tar.gz` |
| macOS Intel | `shebe-v0.6.0-darwin-x86_64.tar.gz` |
| macOS Apple Silicon | `shebe-v0.6.0-darwin-aarch64.tar.gz` |
| MCP Bundle | `shebe-mcp-v0.6.0.mcpb` |

### Tarball Contents

```
shebe-v0.6.0-linux-x86_64/
  shebe-mcp    # MCP server binary
  shebe        # CLI binary
```

---

## Release Flow

### Creating a Release

1. **Update version** in `services/shebe-server/Cargo.toml`
2. **Update CHANGELOG.md** with release notes
3. **Create and push tag:**
   ```bash
   git tag v0.6.0
   git push origin v0.6.0
   git push github v0.6.0  # Mirror to GitHub
   ```

4. **Pipeline executes:**
   - GitLab builds Linux binaries
   - GitLab creates releases (GitLab + GitHub draft)
   - GitHub Actions builds macOS binaries
   - GitHub Actions publishes final release

5. **Verify releases:**
   - GitLab: https://gitlab.com/rhobimd-oss/shebe/-/releases
   - GitHub: https://github.com/rhobimd-oss/shebe/releases

### Release Checklist

- [ ] Version bumped in Cargo.toml
- [ ] CHANGELOG.md updated with [Unreleased] section
- [ ] All tests passing on main
- [ ] Tag created and pushed to both remotes
- [ ] GitLab pipeline completed successfully
- [ ] GitHub Actions completed successfully
- [ ] Both releases contain all platform artifacts

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| GitHub release not created | Missing `SHEBE_GITHUB_TOKEN` | Add variable to GitLab CI/CD |
| macOS build not triggered | PAT missing Actions scope | Regenerate PAT with Actions permission |
| 401 on GitHub API | PAT expired | Regenerate and update variable |
| Empty releases dir | Build job failed | Check build:linux logs |
| Version mismatch | Cargo.toml not updated | Ensure version in Cargo.toml matches tag |

### Debug Commands

```bash
# Check GitLab CI variables
gitlab-ci-lint .gitlab-ci.yml

# Test GitHub API access (requires SHEBE_GITHUB_TOKEN env var)
curl -H "Authorization: Bearer $SHEBE_GITHUB_TOKEN" \
  https://api.github.com/repos/rhobimd-oss/shebe/releases

# Verify tag exists on both remotes
git ls-remote origin --tags v0.6.0
git ls-remote github --tags v0.6.0

# Test version extraction locally
grep '^version' services/shebe-server/Cargo.toml | head -1 | sed 's/.*"\(.*\)".*/\1/'
```

---

## Architecture Decisions

### Why Dual CI/CD?

**Problem:** macOS cannot run in Docker containers (Apple EULA, kernel requirements)

**Solution:** Use GitHub Actions for macOS builds

- GitLab CI: Linux builds, orchestration, GitLab releases
- GitHub Actions: macOS builds only (triggered by GitLab)

### Why Both GitLab and GitHub Releases?

| Platform | Purpose |
|----------|---------|
| GitLab | Primary release, full changelog, package registry |
| GitHub | Zed extension compatibility (`zed::latest_github_release()`) |

### Why musl Builds?

- **Static linking:** No glibc dependency
- **MCPB bundles:** Single portable binary
- **Alpine containers:** Native compatibility

---

## References

- [GitLab CI/CD Documentation](https://docs.gitlab.com/ee/ci/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub REST API: Releases](https://docs.github.com/en/rest/releases)
- [Zed Extension API](https://docs.rs/zed_extension_api)
