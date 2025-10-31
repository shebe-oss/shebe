# Makefile style guide from http://clarkgrubb.com/makefile-style-guide
MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -o errexit -o nounset -o pipefail -c
.DEFAULT_GOAL := docker-build
.DELETE_ON_ERROR:
.SUFFIXES:


# STATIC VARS
REGISTRY_URL := registry.gitlab.com
IMAGE_NAME := rhobimd-oss/shebe
IMAGE_TAG ?= $(shell cat services/shebe-server/VERSION 2>/dev/null || echo "latest")
CONTAINER_NAME := shebe-server

# Docker build args
DOCKERFILE := services/shebe-server/Dockerfile
BUILD_CONTEXT := services/shebe-server

# Runtime configuration
HOST_PORT ?= 3000
DATA_DIR ?= $(PWD)/data


# DEVELOPMENT TARGETS ----------------------------------------------------------
# Cargo configuration
SHEBE_INDEX_DIR ?= $(HOME)/.local/state/shebe/sessions

# Build targets
build:
	cd services/shebe-server && cargo build

build-release:
	cd services/shebe-server && cargo build --release

# Run targets
run:
	cd services/shebe-server && SHEBE_INDEX_DIR=$(SHEBE_INDEX_DIR) cargo run --bin shebe

run-release:
	cd services/shebe-server && SHEBE_INDEX_DIR=$(SHEBE_INDEX_DIR) cargo run --release --bin shebe

# Test and quality targets
dev-test:
	cd services/shebe-server && cargo test

dev-fmt:
	cd services/shebe-server && cargo fmt

dev-clippy:
	cd services/shebe-server && cargo clippy

# Docker test targets (CI/CD and pre-commit hook)
docker-test:
	@echo "Running tests in Docker container..."
	cd deploy && docker compose run --rm shebe-test

docker-test-quick:
	@echo "Running tests in Docker (using cached dependencies)..."
	cd deploy && docker compose run --rm shebe-test cargo test

docker-clippy:
	@echo "Running clippy in Docker container..."
	cd deploy && docker compose run --rm shebe-test cargo clippy -- -D warnings

docker-fmt-check:
	@echo "Checking code formatting in Docker container..."
	cd deploy && docker compose run --rm shebe-test cargo fmt --check

# Clean Docker test artifacts
docker-test-clean:
	@echo "Cleaning Docker test volumes..."
	docker volume rm shebe_cargo-registry shebe_cargo-git shebe_cargo-target 2>/dev/null || true
	@echo "Test volumes cleaned"

# Legacy aliases
dev-build: build-release

dev-run: run


# MCP TARGETS ------------------------------------------------------------------
VERSION ?= $(shell cat services/shebe-server/VERSION)
ARCH := linux-x86_64
VERSIONED_NAME := shebe-mcp-v$(VERSION)-$(ARCH)
MCP_BINARY := services/shebe-server/target/release/shebe-mcp

mcp-build:
	cd services/shebe-server && cargo build --release --verbose --bin shebe-mcp
	@echo "Binary built: $(MCP_BINARY)"
	@ls -lh $(MCP_BINARY)

mcp-install: mcp-build
	@echo "Installing $(VERSIONED_NAME) to /usr/local/lib/..."
	sudo cp $(MCP_BINARY) /usr/local/lib/$(VERSIONED_NAME)
	@echo "Creating symlink /usr/local/bin/shebe-mcp..."
	sudo ln -sf /usr/local/lib/$(VERSIONED_NAME) /usr/local/bin/shebe-mcp
	@echo "Installation complete:"
	@ls -lh /usr/local/bin/shebe-mcp
	@which shebe-mcp

mcp-install-config:
	@echo "Installing config file template to ~/.config/shebe/..."
	@mkdir -p ~/.config/shebe
	@if [ -f ~/.config/shebe/config.toml ]; then \
		echo "Config file already exists at ~/.config/shebe/config.toml"; \
		echo "To replace it, run: cp shebe.toml ~/.config/shebe/config.toml"; \
	else \
		cp shebe.toml ~/.config/shebe/config.toml; \
		echo "Config file installed: ~/.config/shebe/config.toml"; \
		echo "Edit with: nano ~/.config/shebe/config.toml"; \
	fi

mcp-uninstall:
	@echo "Removing shebe-mcp symlink and versioned binary..."
	sudo rm -f /usr/local/bin/shebe-mcp
	sudo rm -f /usr/local/lib/$(VERSIONED_NAME)
	@echo "Uninstallation complete"

mcp-test:
	@echo "Testing shebe-mcp binary with initialize message..."
	@echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{'\
'"protocolVersion":"2024-11-05","capabilities":{"tools":{}},'\
'"clientInfo":{"name":"test","version":"1.0"}}}' | shebe-mcp


# HELP TARGET ------------------------------------------------------------------
help:
	@echo "Shebe Makefile Targets:"
	@echo ""
	@echo "Development Targets:"
	@echo "  build                Build debug binary"
	@echo "  build-release        Build release binary"
	@echo "  run                  Run server (debug mode)"
	@echo "  run-release          Run server (release mode)"
	@echo "  dev-test             Run cargo tests (native)"
	@echo "  dev-fmt              Format code (native)"
	@echo "  dev-clippy           Run clippy linter (native)"
	@echo ""
	@echo "Docker Test Targets:"
	@echo "  docker-test          Run tests in Docker container (full)"
	@echo "  docker-test-quick    Run tests in Docker (cached deps)"
	@echo "  docker-clippy        Run clippy in Docker container"
	@echo "  docker-fmt-check     Check formatting in Docker"
	@echo "  docker-test-clean    Clean Docker test volumes"
	@echo ""
	@echo "MCP Targets:"
	@echo "  mcp-build            Build shebe-mcp binary"
	@echo "  mcp-install          Install versioned binary to /usr/local/lib"
	@echo "  mcp-install-config   Install config template to ~/.config/shebe/"
	@echo "  mcp-uninstall        Remove installed binary and symlink"
	@echo "  mcp-test             Test MCP binary with initialize message"
	@echo ""
	@echo "Variables:"
	@echo "  IMAGE_TAG=$(IMAGE_TAG)"
	@echo "  HOST_PORT=$(HOST_PORT)"
	@echo "  DATA_DIR=$(DATA_DIR)"
	@echo "  VERSION=$(VERSION)"
	@echo "  SHEBE_INDEX_DIR=$(SHEBE_INDEX_DIR)"
