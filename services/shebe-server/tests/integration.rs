// Integration tests module
//
// This file serves as the entry point for all integration tests.
// Individual test modules are in the integration/ directory.

mod common;

// Test modules
mod integration {
    mod test_indexing;
    mod test_search;
    mod test_sessions;
    // mod test_api;  // TODO: Add API integration tests
}
