//! Shebe server entry point
//!
//! Starts the REST API server for the Shebe RAG service.

use std::sync::Arc;

use axum::{
    middleware,
    routing::{delete, get, post},
    Router,
};
use tower_http::cors::CorsLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod api;
mod config;
mod error;
mod indexer;
mod search;
mod storage;
mod types;
mod xdg;

use crate::api::{handlers, middleware as api_middleware, state::AppState};
use crate::config::Config;
use crate::xdg::{migrate_legacy_paths, XdgDirs};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "shebe=info,tower_http=debug".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    tracing::info!("Starting Shebe RAG service");
    tracing::info!("Version: {}", env!("CARGO_PKG_VERSION"));

    // Initialize XDG directories
    let xdg = XdgDirs::new();
    xdg.log_paths();

    // Ensure XDG directories exist
    xdg.ensure_dirs_exist()?;

    // Run migration from legacy paths (if needed)
    if let Err(e) = migrate_legacy_paths(&xdg) {
        tracing::warn!("Migration warning: {}", e);
        tracing::info!("Continuing with current paths...");
    }

    // Load configuration
    let config = Config::load()?;

    // Log configuration details
    config.log_config();

    // Create shared application state
    let state = Arc::new(AppState::new(config.clone()));

    // Build the API router
    let app = Router::new()
        // Health check endpoint
        .route("/health", get(handlers::health_handler))
        // API v1 endpoints
        .route("/api/v1/index", post(handlers::index_handler))
        .route("/api/v1/search", post(handlers::search_handler))
        .route("/api/v1/sessions", get(handlers::list_sessions_handler))
        .route(
            "/api/v1/sessions/:session_id",
            delete(handlers::delete_session_handler),
        )
        // Add middleware
        .layer(middleware::from_fn(api_middleware::log_request))
        .layer(CorsLayer::permissive())
        // Add shared state
        .with_state(state);

    // Bind to address and start server
    let addr = format!("{}:{}", config.server.host, config.server.port);
    let listener = tokio::net::TcpListener::bind(&addr).await?;

    tracing::info!("Listening on {}", addr);
    tracing::info!("Service ready - Health check at http://{}/health", addr);

    // Serve the application
    axum::serve(listener, app).await?;

    Ok(())
}
