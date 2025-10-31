//! HTTP request handlers for the Shebe API
//!
//! Implements handlers for all 5 REST endpoints: health, index,
//! search, list sessions, and delete session.

use std::sync::Arc;

use axum::{
    extract::{Path, State},
    response::IntoResponse,
    Json,
};

use crate::api::state::AppState;
use crate::error::ShebeError;
use crate::types::*;

/// Health check handler
///
/// Returns server status and version information.
///
/// # Returns
///
/// JSON response with status "ok" and version number
pub async fn health_handler() -> impl IntoResponse {
    Json(HealthResponse {
        status: "ok".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    })
}

/// Index repository handler
///
/// Indexes a directory into a new session using the specified
/// include/exclude patterns.
///
/// # Arguments
///
/// * `state` - Shared application state
/// * `req` - Index request with path and patterns
///
/// # Returns
///
/// Index statistics on success, error on failure
///
/// # Errors
///
/// - `InvalidPath`: Path doesn't exist or isn't accessible
/// - `SessionAlreadyExists`: Session ID already in use
/// - `IndexingFailed`: Failed to index directory
pub async fn index_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<IndexRequest>,
) -> Result<Json<IndexResponse>, ShebeError> {
    // Validate path exists
    let path = std::path::PathBuf::from(&req.path);
    if !path.exists() {
        return Err(ShebeError::InvalidPath(format!(
            "Path not found: {}",
            req.path
        )));
    }

    if !path.is_dir() {
        return Err(ShebeError::InvalidPath(format!(
            "Path is not a directory: {}",
            req.path
        )));
    }

    // Check if session already exists
    if state.storage.session_exists(&req.session) {
        return Err(ShebeError::SessionAlreadyExists(req.session.clone()));
    }

    // Use the unified index_repository method (same as MCP binary)
    let stats = state.storage.index_repository(
        &req.session,
        &path,
        req.include_patterns.clone(),
        req.exclude_patterns.clone(),
        state.config.indexing.chunk_size,
        state.config.indexing.overlap,
        state.config.indexing.max_file_size_mb,
        false, // force = false (already checked session doesn't exist)
    )?;

    Ok(Json(IndexResponse::from(stats)))
}

/// Search handler
///
/// Executes a BM25 search against the specified session.
///
/// # Arguments
///
/// * `state` - Shared application state
/// * `req` - Search request with query and session
///
/// # Returns
///
/// Search results on success, error on failure
///
/// # Errors
///
/// - `InvalidQuery`: Query is empty or invalid
/// - `SessionNotFound`: Session doesn't exist
/// - `SearchFailed`: Search execution failed
pub async fn search_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<SearchRequest>,
) -> Result<Json<SearchResponse>, ShebeError> {
    // Validate query
    if req.query.trim().is_empty() {
        return Err(ShebeError::InvalidQuery(
            "Query cannot be empty".to_string(),
        ));
    }

    // Execute search (synchronous, same as MCP)
    let response = state.search.search(req)?;

    Ok(Json(response))
}

/// List sessions handler
///
/// Returns metadata for all existing sessions.
///
/// # Arguments
///
/// * `state` - Shared application state
///
/// # Returns
///
/// List of session information
pub async fn list_sessions_handler(
    State(state): State<Arc<AppState>>,
) -> Result<Json<SessionsResponse>, ShebeError> {
    let sessions = state
        .storage
        .list_sessions()?
        .into_iter()
        .map(|m| SessionInfo {
            id: m.id,
            files: m.files_indexed,
            chunks: m.chunks_created,
            created_at: m.created_at.to_rfc3339(),
            size_bytes: m.index_size_bytes,
        })
        .collect();

    Ok(Json(SessionsResponse { sessions }))
}

/// Delete session handler
///
/// Removes a session and its associated index.
///
/// # Arguments
///
/// * `state` - Shared application state
/// * `session_id` - ID of the session to delete
///
/// # Returns
///
/// Success message on deletion, error if not found
///
/// # Errors
///
/// - `SessionNotFound`: Session doesn't exist
pub async fn delete_session_handler(
    State(state): State<Arc<AppState>>,
    Path(session_id): Path<String>,
) -> Result<Json<DeleteResponse>, ShebeError> {
    // Check session exists
    if !state.storage.session_exists(&session_id) {
        return Err(ShebeError::SessionNotFound(session_id.clone()));
    }

    // Delete session
    state.storage.delete_session(&session_id)?;

    Ok(Json(DeleteResponse {
        status: "deleted".to_string(),
        session: session_id,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[tokio::test]
    async fn test_health_handler() {
        let response = health_handler().await.into_response();
        assert_eq!(response.status(), 200);
    }

    #[tokio::test]
    async fn test_index_invalid_path() {
        let _temp_dir = TempDir::new().unwrap();
        let config = crate::config::Config::default();
        let state = Arc::new(AppState::new(config));

        let req = IndexRequest {
            path: "/nonexistent/path".to_string(),
            session: "test".to_string(),
            include_patterns: vec![],
            exclude_patterns: vec![],
        };

        let result = index_handler(State(state), Json(req)).await;

        assert!(result.is_err());
        match result.unwrap_err() {
            ShebeError::InvalidPath(_) => (),
            _ => panic!("Expected InvalidPath error"),
        }
    }

    #[tokio::test]
    async fn test_search_empty_query() {
        let _temp_dir = TempDir::new().unwrap();
        let mut config = crate::config::Config::default();
        config.storage.index_dir = _temp_dir.path().to_path_buf();

        let state = Arc::new(AppState::new(config));

        let req = SearchRequest {
            query: "   ".to_string(), // Empty after trimming
            session: "test".to_string(),
            k: None,
        };

        let result = search_handler(State(state), Json(req)).await;

        assert!(result.is_err());
        match result.unwrap_err() {
            ShebeError::InvalidQuery(_) => (),
            _ => panic!("Expected InvalidQuery error"),
        }
    }

    #[tokio::test]
    async fn test_delete_nonexistent_session() {
        let _temp_dir = TempDir::new().unwrap();
        let mut config = crate::config::Config::default();
        config.storage.index_dir = _temp_dir.path().to_path_buf();

        let state = Arc::new(AppState::new(config));

        let result = delete_session_handler(State(state), Path("nonexistent".to_string())).await;

        assert!(result.is_err());
        match result.unwrap_err() {
            ShebeError::SessionNotFound(_) => (),
            _ => panic!("Expected SessionNotFound error"),
        }
    }

    #[tokio::test]
    async fn test_list_sessions_empty() {
        let _temp_dir = TempDir::new().unwrap();
        let mut config = crate::config::Config::default();
        config.storage.index_dir = _temp_dir.path().to_path_buf();

        let state = Arc::new(AppState::new(config));

        let result = list_sessions_handler(State(state)).await;

        assert!(result.is_ok());
        let response = result.unwrap().0;
        assert_eq!(response.sessions.len(), 0);
    }
}
