# Docker Testing Guide

**Purpose:** Run Rust tests in a Docker container for consistency across environments

**Last Updated:** 2025-10-22

---

## Overview

Shebe provides Docker-based testing to ensure tests run consistently across different
development environments. This is especially useful for CI/CD pipelines and ensuring
all developers test in the same Rust environment.

## Quick Start

### Run All Tests

```bash
# From repository root
make docker-test
```

This will:
1. Pull `rust:1.83-slim` image (if not cached)
2. Install build dependencies (pkg-config, libssl-dev, curl)
3. Run `cargo test` with all optimizations
4. Cache dependencies for faster subsequent runs

### Run Tests (Fast - Using Cache)

```bash
make docker-test-quick
```

Uses cached dependencies and build artifacts. Much faster than full rebuild.

### Run Clippy in Docker

```bash
make docker-clippy
```

### Check Code Formatting

```bash
make docker-fmt-check
```

---

## Git Pre-Commit Hook

A pre-commit hook automatically runs tests before allowing commits.

### How It Works

1. **Detects Changes:** Only runs if `.rs` or `.toml` files changed
2. **Runs Tests:** Executes `docker compose run --rm shebe-test`
3. **Blocks Commit:** Prevents commit if tests fail

### Hook Location

`.git/hooks/pre-commit` (automatically installed)

### Bypass Hook (Not Recommended)

```bash
git commit --no-verify -m "Skip tests (use with caution)"
```

### Manual Test Run

```bash
# If Docker is unavailable
cd services/shebe-server
cargo test
```

---

## Docker Compose Configuration

### Test Service Definition

**File:** `deploy/docker-compose.yml`

```yaml
shebe-test:
  image: rust:1.83-slim
  working_dir: /workspace/services/shebe-server
  volumes:
    - ../:/workspace:rw
    - cargo-registry:/usr/local/cargo/registry
    - cargo-git:/usr/local/cargo/git
    - cargo-target:/workspace/services/shebe-server/target
  command: cargo test --color=always
  profiles:
    - test
```

### Volume Caching

Three Docker volumes cache build artifacts:

- **cargo-registry:** Downloaded crates (~200MB)
- **cargo-git:** Git dependencies
- **cargo-target:** Compiled artifacts (~1GB)

**Clean Cache:**

```bash
make docker-test-clean
```

This removes all cached volumes. Next test run will re-download dependencies.

---

## CI/CD Integration

### GitLab CI Example

```yaml
test:
  image: docker:latest
  services:
    - docker:dind
  script:
    - cd deploy
    - docker compose run --rm shebe-test
  only:
    - merge_requests
    - main
```

### GitHub Actions Example

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: make docker-test
```

---

## Performance Comparison

| Method              | First Run  | Cached Run | Use Case            |
|---------------------|------------|------------|---------------------|
| `make dev-test`     | 5-10s      | <5s        | Local development   |
| `make docker-test`  | 2-5 min    | 30-60s     | CI/CD, consistency  |
| `make docker-test-quick` | 1-2 min | 10-20s     | Fast Docker testing |

**Recommendation:**
- Use `make dev-test` for rapid iteration
- Use `make docker-test` for pre-commit/CI/CD
- Pre-commit hook ensures consistency before commits

---

## Troubleshooting

### Issue: Docker not found

**Error:**
```
Docker not found. Please install Docker
```

**Solution:**
1. Install Docker: https://docs.docker.com/get-docker/
2. Or run tests natively: `cd services/shebe-server && cargo test`

### Issue: Docker daemon not running

**Error:**
```
Docker daemon not running
```

**Solution:**
```bash
# Linux
sudo systemctl start docker

# macOS
# Start Docker Desktop app

# Windows
# Start Docker Desktop app
```

### Issue: Permission denied

**Error:**
```
permission denied while trying to connect to Docker daemon
```

**Solution:**
```bash
# Add user to docker group (Linux)
sudo usermod -aG docker $USER
newgrp docker

# Or use sudo
sudo make docker-test
```

### Issue: Tests fail in Docker but pass natively

**Cause:** Different Rust versions or system libraries

**Solution:**
1. Check Rust version: `rustc --version`
2. Update Docker image in `docker-compose.yml`:
   ```yaml
   image: rust:1.83-slim  # Match your local version
   ```
3. Clean cache: `make docker-test-clean`
4. Re-run: `make docker-test`

### Issue: Slow Docker tests

**Cause:** Rebuilding dependencies every run

**Solution:**
1. Ensure volumes are configured (check `docker-compose.yml`)
2. Use quick mode: `make docker-test-quick`
3. Pre-download dependencies:
   ```bash
   cd deploy
   docker compose run --rm shebe-test cargo fetch
   ```

---

## Advanced Usage

### Run Specific Tests

```bash
cd deploy
docker compose run --rm shebe-test cargo test test_validate_path
```

### Run Tests with Output

```bash
cd deploy
docker compose run --rm shebe-test cargo test -- --nocapture
```

### Run Tests in Parallel

```bash
cd deploy
docker compose run --rm shebe-test cargo test -- --test-threads=4
```

### Debug Failed Tests

```bash
cd deploy
docker compose run --rm shebe-test cargo test -- --nocapture RUST_BACKTRACE=1
```

### Interactive Shell

```bash
cd deploy
docker compose run --rm shebe-test bash
# Inside container:
cargo test
cargo clippy
exit
```

---

## Best Practices

1. **Run Tests Locally First:** Use `make dev-test` for fast feedback
2. **Use Docker Before Commit:** Let pre-commit hook catch issues
3. **Clean Cache Periodically:** Run `make docker-test-clean` weekly
4. **CI/CD Always Uses Docker:** Ensures consistency across environments
5. **Keep Rust Version Updated:** Update `docker-compose.yml` to match CI/CD

---

## Related Documentation

- **Docker Deployment:** docs/deployment/docker-deployment.md
- **Development Workflow:** docs/guides/development-workflow.md
- **CI/CD Setup:** docs/ci-cd/gitlab-ci-setup.md

---

**Document Version:** 1.0
**Last Updated:** 2025-10-22
**Maintained By:** Shebe Team
