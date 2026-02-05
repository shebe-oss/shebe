//! Integration tests for pagination (Phase 4)
//!
//! These tests exercise the full MCP handler stack (not just
//! individual tool handlers) for both list_dir cursor-based
//! pagination and read_file offset-based pagination.

#[cfg(test)]
mod tests {
    use serde_json::json;
    use shebe::core::config::Config;
    use shebe::core::services::Services;
    use shebe::mcp::handlers::ProtocolHandlers;
    use shebe::mcp::protocol::*;
    use std::sync::Arc;
    use tempfile::TempDir;

    /// Create handlers backed by a temp directory containing
    /// an indexed session with `n` generated files.
    async fn setup_indexed_session(
        n: usize,
        session: &str,
    ) -> (ProtocolHandlers, TempDir, TempDir) {
        let storage_dir = TempDir::new().unwrap();
        let repo_dir = TempDir::new().unwrap();

        // Create n files in the repo directory
        for i in 0..n {
            let file_name = format!("file_{i:04}.rs");
            let content = format!("// File {i}\nfn func_{i}() -> usize {{ {i} }}\n");
            std::fs::write(repo_dir.path().join(&file_name), content).unwrap();
        }

        let mut config = Config::default();
        config.storage.index_dir = storage_dir.path().to_path_buf();
        let services = Arc::new(Services::new(config));
        let handlers = ProtocolHandlers::new(services);

        // Index the repo via the MCP handler
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(1)),
            method: "tools/call".to_string(),
            params: Some(json!({
                "name": "index_repository",
                "arguments": {
                    "path": repo_dir.path().to_str().unwrap(),
                    "session": session
                }
            })),
        };

        let response = handlers.handle_tools_call(request).await.unwrap();
        assert!(
            response.error.is_none(),
            "Indexing failed: {:?}",
            response.error
        );

        (handlers, storage_dir, repo_dir)
    }

    /// Call list_dir through the full handler stack.
    async fn call_list_dir(
        handlers: &ProtocolHandlers,
        session: &str,
        limit: usize,
        sort: &str,
        cursor: Option<&str>,
    ) -> JsonRpcResponse {
        let mut arguments = json!({
            "session": session,
            "limit": limit,
            "sort": sort
        });
        if let Some(c) = cursor {
            arguments["cursor"] = json!(c);
        }

        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(99)),
            method: "tools/call".to_string(),
            params: Some(json!({
                "name": "list_dir",
                "arguments": arguments
            })),
        };

        handlers.handle_tools_call(request).await.unwrap()
    }

    /// Call read_file through the full handler stack.
    async fn call_read_file(
        handlers: &ProtocolHandlers,
        session: &str,
        file_path: &str,
        offset: Option<usize>,
        length: Option<usize>,
    ) -> JsonRpcResponse {
        let mut arguments = json!({
            "session": session,
            "file_path": file_path
        });
        if let Some(o) = offset {
            arguments["offset"] = json!(o);
        }
        if let Some(l) = length {
            arguments["length"] = json!(l);
        }

        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(99)),
            method: "tools/call".to_string(),
            params: Some(json!({
                "name": "read_file",
                "arguments": arguments
            })),
        };

        handlers.handle_tools_call(request).await.unwrap()
    }

    /// Extract the text content from a successful tool call
    /// response.
    fn extract_text(response: &JsonRpcResponse) -> &str {
        assert!(
            response.error.is_none(),
            "Expected success, got error: {:?}",
            response.error
        );
        let result = response.result.as_ref().unwrap();
        result["content"][0]["text"].as_str().unwrap()
    }

    /// Extract file paths from list_dir markdown table.
    fn extract_file_paths(text: &str) -> Vec<String> {
        text.lines()
            .filter(|line| line.starts_with("| `"))
            .filter_map(|line| {
                let start = line.find('`')? + 1;
                let end = start + line[start..].find('`')?;
                Some(line[start..end].to_string())
            })
            .collect()
    }

    /// Extract cursor value from list_dir output text.
    fn extract_cursor(text: &str) -> Option<String> {
        let prefix = "cursor=\"";
        let start = text.find(prefix)? + prefix.len();
        let end = start + text[start..].find('"')?;
        Some(text[start..end].to_string())
    }

    // ---------------------------------------------------------
    // Test 1: list_dir full pagination loop (P1 Center)
    // ---------------------------------------------------------

    /// Index a 3000-file repo. Paginate with limit=500.
    /// 6 pages returned. Concatenated file list has 3000
    /// unique entries matching session info.
    #[tokio::test]
    async fn test_list_dir_full_pagination_loop() {
        let total = 3000_usize;
        let limit = 500_usize;
        let session = "integ-pagination-loop";

        let (handlers, _storage, _repo) = setup_indexed_session(total, session).await;

        let mut all_files = Vec::new();
        let mut cursor_str: Option<String> = None;
        let mut page_count = 0;

        loop {
            let response =
                call_list_dir(&handlers, session, limit, "alpha", cursor_str.as_deref()).await;

            let text = extract_text(&response);
            let paths = extract_file_paths(text);
            all_files.extend(paths);
            page_count += 1;

            cursor_str = extract_cursor(text);
            if cursor_str.is_none() {
                break;
            }
        }

        // Verify page count
        assert_eq!(page_count, 6, "3000 files / 500 per page = 6 pages");

        // Verify total unique entries
        let unique: std::collections::HashSet<_> = all_files.iter().collect();
        assert_eq!(
            unique.len(),
            total,
            "All files must be unique (no duplicates)"
        );
        assert_eq!(
            all_files.len(),
            total,
            "Total files must match session count"
        );
    }

    // ---------------------------------------------------------
    // Test 2: read_file full pagination loop (P1 Center)
    // ---------------------------------------------------------

    /// Create a 500KB file. Paginate with default chunk size.
    /// All chunks reassemble to original content (byte
    /// equality).
    #[tokio::test]
    async fn test_read_file_full_pagination_loop() {
        let session = "integ-readfile-loop";

        let storage_dir = TempDir::new().unwrap();
        let repo_dir = TempDir::new().unwrap();

        // Create a ~500KB file with distinct content
        let original: String = (0..20000)
            .map(|i| format!("Line {i:05}: content\n"))
            .collect();
        let file_name = "large_file.txt";
        let file_path = repo_dir.path().join(file_name);
        std::fs::write(&file_path, &original).unwrap();

        let mut config = Config::default();
        config.storage.index_dir = storage_dir.path().to_path_buf();
        let services = Arc::new(Services::new(config));
        let handlers = ProtocolHandlers::new(services);

        // Index
        let idx_request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(1)),
            method: "tools/call".to_string(),
            params: Some(json!({
                "name": "index_repository",
                "arguments": {
                    "path": repo_dir.path().to_str().unwrap(),
                    "session": session
                }
            })),
        };
        let idx_resp = handlers.handle_tools_call(idx_request).await.unwrap();
        assert!(
            idx_resp.error.is_none(),
            "Indexing failed: {:?}",
            idx_resp.error
        );

        // Read the file in chunks via offset pagination
        let file_path_str = file_path.to_str().unwrap();
        let chunk_len = 10000_usize;
        let mut offset = 0_usize;
        let mut reassembled = String::new();

        loop {
            let response = call_read_file(
                &handlers,
                session,
                file_path_str,
                Some(offset),
                Some(chunk_len),
            )
            .await;

            let text = extract_text(&response);

            // Extract the code block content between ```\n
            // and \n```
            let code_start = text.find("```\n").map(|p| p + 4).or_else(|| {
                // Language-specific fence: ```txt\n
                text.find("```txt\n").map(|p| p + 7)
            });

            if let Some(start) = code_start {
                // Find closing fence
                let remaining = &text[start..];
                if let Some(end) = remaining.rfind("\n```") {
                    reassembled.push_str(&remaining[..end]);
                }
            }

            // Check if more content available
            if text.contains("More content available") {
                // Extract next offset from the hint
                let hint_prefix = "offset=";
                if let Some(pos) = text.rfind(hint_prefix) {
                    let after = &text[pos + hint_prefix.len()..];
                    let end = after
                        .find(|c: char| !c.is_ascii_digit())
                        .unwrap_or(after.len());
                    offset = after[..end].parse().unwrap();
                } else {
                    break;
                }
            } else {
                break;
            }
        }

        // Verify byte-level equality
        assert_eq!(
            reassembled.len(),
            original.len(),
            "Reassembled length must match original \
             ({} vs {})",
            reassembled.len(),
            original.len()
        );
        assert_eq!(
            reassembled, original,
            "Reassembled content must match original \
             byte-for-byte"
        );
    }

    // ---------------------------------------------------------
    // Test 3: list_dir preserves sort order (P2 Boundary)
    // ---------------------------------------------------------

    /// Index 1000 files. Paginate with sort=alpha, limit=200.
    /// Verify last entry of each page < first entry of next
    /// page (lexicographic).
    #[tokio::test]
    async fn test_list_dir_pagination_preserves_sort_order() {
        let total = 1000_usize;
        let limit = 200_usize;
        let session = "integ-sort-order";

        let (handlers, _storage, _repo) = setup_indexed_session(total, session).await;

        let mut pages: Vec<Vec<String>> = Vec::new();
        let mut cursor_str: Option<String> = None;

        loop {
            let response =
                call_list_dir(&handlers, session, limit, "alpha", cursor_str.as_deref()).await;

            let text = extract_text(&response);
            pages.push(extract_file_paths(text));

            cursor_str = extract_cursor(text);
            if cursor_str.is_none() {
                break;
            }
        }

        // Should be exactly 5 pages (1000 / 200)
        assert_eq!(pages.len(), 5, "1000 / 200 = 5 pages");

        // Verify sort at page boundaries
        for i in 0..pages.len() - 1 {
            let last = pages[i].last().unwrap();
            let first = pages[i + 1].first().unwrap();
            assert!(
                last < first,
                "Page {i} last '{last}' must lexicographically \
                 precede page {} first '{first}'",
                i + 1
            );
        }

        // Verify sort within each page
        for (page_idx, page) in pages.iter().enumerate() {
            for i in 0..page.len() - 1 {
                assert!(
                    page[i] <= page[i + 1],
                    "Page {page_idx}: '{0}' should precede \
                     '{1}'",
                    page[i],
                    page[i + 1]
                );
            }
        }
    }

    // ---------------------------------------------------------
    // Test 4: list_dir no cursor backward compat (P1 Center)
    // ---------------------------------------------------------

    /// Index repo. Call list_dir without cursor. Verify
    /// response format matches pre-pagination schema: no
    /// cursor artifacts, standard field structure.
    #[tokio::test]
    async fn test_list_dir_no_cursor_backward_compat() {
        let session = "integ-listdir-compat";

        let (handlers, _storage, _repo) = setup_indexed_session(10, session).await;

        let response = call_list_dir(&handlers, session, 100, "alpha", None).await;

        let text = extract_text(&response);

        // Standard format fields
        assert!(
            text.contains("**Session:** `integ-listdir-compat`"),
            "Missing session header"
        );
        assert!(
            text.contains("**Files:** 10 (showing 1-10)"),
            "Missing files header"
        );
        assert!(
            text.contains("| File Path | Chunks |"),
            "Missing table header"
        );

        // No pagination artifacts
        assert!(
            !text.contains("cursor="),
            "No cursor expected for single-page result"
        );
        assert!(
            !text.contains("More results available"),
            "No 'more results' hint expected"
        );
        assert!(!text.contains("nextCursor"), "No nextCursor field expected");

        // Verify all 10 files present
        let paths = extract_file_paths(text);
        assert_eq!(paths.len(), 10, "All 10 files should be listed");
    }

    // ---------------------------------------------------------
    // Test 5: read_file no offset backward compat (P1 Center)
    // ---------------------------------------------------------

    /// Read small file without offset. Verify response format
    /// matches pre-pagination schema: standard headers, no
    /// offset artifacts.
    #[tokio::test]
    async fn test_read_file_no_offset_backward_compat() {
        let session = "integ-readfile-compat";

        let storage_dir = TempDir::new().unwrap();
        let repo_dir = TempDir::new().unwrap();

        // Create a small Rust file
        let content = "fn main() {\n    println!(\"test\");\n}\n";
        let file_name = "main.rs";
        let file_path = repo_dir.path().join(file_name);
        std::fs::write(&file_path, content).unwrap();

        let mut config = Config::default();
        config.storage.index_dir = storage_dir.path().to_path_buf();
        let services = Arc::new(Services::new(config));
        let handlers = ProtocolHandlers::new(services);

        // Index
        let idx_request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(json!(1)),
            method: "tools/call".to_string(),
            params: Some(json!({
                "name": "index_repository",
                "arguments": {
                    "path": repo_dir.path().to_str().unwrap(),
                    "session": session
                }
            })),
        };
        let idx_resp = handlers.handle_tools_call(idx_request).await.unwrap();
        assert!(
            idx_resp.error.is_none(),
            "Indexing failed: {:?}",
            idx_resp.error
        );

        // Read file without offset
        let response =
            call_read_file(&handlers, session, file_path.to_str().unwrap(), None, None).await;

        let text = extract_text(&response);

        // Standard format fields
        assert!(text.contains("**File:**"), "Missing file header");
        assert!(
            text.contains("**Session:** `integ-readfile-compat`"),
            "Missing session header"
        );
        assert!(text.contains("**Size:**"), "Missing size header");
        assert!(text.contains("**Language:**"), "Missing language header");
        assert!(
            text.contains(content),
            "File content must be present in response"
        );

        // No pagination artifacts
        assert!(
            !text.contains("showing bytes"),
            "No byte range info in non-offset read"
        );
        assert!(
            !text.contains("More content available"),
            "No 'more content' hint for small file"
        );
        assert!(!text.contains("offset="), "No offset hint for small file");
        assert!(
            !text.contains("lines in chunk"),
            "No chunk metadata in non-offset read"
        );
    }
}
