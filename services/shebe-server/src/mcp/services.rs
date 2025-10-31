//! Shebe service wrapper for MCP tools
//!
//! This module provides a wrapper around Shebe's core services
//! for use by MCP tool handlers.

use crate::config::Config;
use crate::search::SearchService;
use crate::storage::StorageManager;
use std::sync::Arc;

/// Wrapper for Shebe core services
///
/// Provides shared access to search, storage, and configuration
/// for all MCP tool handlers.
pub struct ShebeServices {
    pub search: Arc<SearchService>,
    pub storage: Arc<StorageManager>,
    pub config: Arc<Config>,
}

impl ShebeServices {
    /// Create new services from configuration
    pub fn new(config: Config) -> Self {
        let storage = Arc::new(StorageManager::new(config.storage.index_dir.clone()));

        let search = Arc::new(SearchService::new(
            Arc::clone(&storage),
            config.search.default_k,
            config.search.max_k,
        ));

        Self {
            search,
            storage,
            config: Arc::new(config),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_shebe_services_creation() {
        let temp_dir = TempDir::new().unwrap();
        let mut config = Config::default();
        config.storage.index_dir = temp_dir.path().to_path_buf();

        let services = ShebeServices::new(config);

        assert_eq!(services.config.search.default_k, 10);
        assert_eq!(services.config.search.max_k, 100);
    }
}
