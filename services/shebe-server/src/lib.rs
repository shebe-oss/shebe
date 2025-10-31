//! Shebe - Simple RAG Service for Code Search
//!
//! A production-ready RAG service using BM25 full-text search
//! via Tantivy. Designed for fast, reliable code search with
//! UTF-8 safety and session isolation.
//!
//! # Architecture
//!
//! - **API Layer**: REST endpoints via Axum
//! - **Service Layer**: Business logic and orchestration
//! - **Repository Layer**: Data access and management
//! - **Storage Layer**: Tantivy indexes and metadata
//!
//! # Key Features
//!
//! - UTF-8 safe chunking (character-based, never panics)
//! - BM25 search via Tantivy (no vector embeddings)
//! - Session-based indexing (isolated indexes)
//! - REST API (5 endpoints)
//! - Production ready (Docker, logging, metrics)

// Phase 2: Core types and error handling (complete)
pub mod config;
pub mod error;
pub mod types;
pub mod xdg;

// Phase 3: UTF-8 safe chunker (complete)
pub mod indexer;

// Phase 5: Tantivy storage layer (complete)
pub mod storage;

// Phase 6: BM25 search implementation (complete)
pub mod search;

// Phase 7: REST API with Axum (complete)
pub mod api;

// Stage 2 Phase 2: MCP server integration (in progress)
pub mod mcp;

#[cfg(test)]
mod tests {
    // Module-level integration tests are in tests/ directory
}
