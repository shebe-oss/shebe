# syntax=docker/dockerfile:1

##############################################
# Stage 1: Builder
##############################################
FROM rust:1.83-slim AS builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y \
        pkg-config \
        libssl-dev \
        curl \
        && \
    rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 -s /bin/bash shebe

# Set working directory
WORKDIR /build

# Copy only Cargo files first (for dependency caching)
COPY Cargo.toml Cargo.lock ./

# Create dummy main.rs and bench to build dependencies
RUN mkdir -p src benches && \
    echo "fn main() {}" > src/main.rs && \
    echo "fn main() {}" > benches/performance.rs && \
    cargo build --release && \
    rm -rf src benches

# Copy source code and benches
COPY src ./src
COPY benches ./benches

# Build application
# Touch main.rs to force rebuild (not just dependencies)
RUN touch src/main.rs && \
    cargo build --release && \
    strip target/release/shebe

##############################################
# Stage 2: Runtime
##############################################
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y \
        ca-certificates \
        curl \
        && \
    rm -rf /var/lib/apt/lists/*

# Create app user (matching builder UID)
RUN useradd -m -u 1000 -s /bin/bash shebe

# Create data directory
RUN mkdir -p /data && \
    chown -R shebe:shebe /data

# Set working directory
WORKDIR /app

# Copy binary from builder
COPY --from=builder --chown=shebe:shebe \
    /build/target/release/shebe \
    /usr/local/bin/shebe

# Switch to non-root user
USER shebe

# Expose port
EXPOSE 3000

# Set environment variables
ENV SHEBE_HOST=0.0.0.0
ENV SHEBE_PORT=3000
ENV SHEBE_INDEX_DIR=/data
ENV SHEBE_LOG_LEVEL=info

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Run application
CMD ["shebe"]
