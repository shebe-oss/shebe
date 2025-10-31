//! Application state for the Shebe API
//!
//! Provides shared state across all request handlers, including
//! configuration, storage manager, search service, and indexing
//! pipeline.

use std::sync::Arc;

use crate::config::Config;
use crate::indexer::IndexingPipeline;
use crate::search::SearchService;
use crate::storage::StorageManager;

/// Shared application state for Axum handlers
///
/// This struct contains all shared services and configuration
/// needed by the API handlers. All fields are wrapped in Arc
/// for thread-safe sharing across async tasks.
#[derive(Clone)]
pub struct AppState {
    /// Application configuration
    pub config: Arc<Config>,

    /// Storage manager for session CRUD
    pub storage: Arc<StorageManager>,

    /// Search service for executing BM25 queries
    pub search: Arc<SearchService>,

    /// Indexing pipeline for processing repositories
    /// Note: handlers create new pipelines with request-specific
    /// patterns rather than using this shared instance
    #[allow(dead_code)]
    pub indexing: Arc<IndexingPipeline>,
}

impl AppState {
    /// Create a new AppState from configuration
    ///
    /// # Arguments
    ///
    /// * `config` - Application configuration
    ///
    /// # Returns
    ///
    /// A new AppState with all services initialized
    pub fn new(config: Config) -> Self {
        // Create storage manager
        let storage = Arc::new(StorageManager::new(config.storage.index_dir.clone()));

        // Create search service
        let search = Arc::new(SearchService::new(
            storage.clone(),
            config.search.default_k,
            config.search.max_k,
        ));

        // Create default indexing pipeline
        // Note: This is primarily for reference; handlers create
        // their own pipelines with request-specific patterns
        let indexing = Arc::new(
            IndexingPipeline::new(
                config.indexing.chunk_size,
                config.indexing.overlap,
                vec![], // Use request-specific patterns
                vec![], // Use request-specific patterns
                config.indexing.max_file_size_mb,
            )
            .expect("Failed to create indexing pipeline"),
        );

        Self {
            config: Arc::new(config),
            storage,
            search,
            indexing,
        }
    }
}
