# Security Policy

## Supported Versions

We actively support the following versions of Shebe with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | :white_check_mark: |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Reporting a Vulnerability

We take the security of Shebe seriously. If you discover a security vulnerability, please follow these steps:

### 1. Do Not Open a Public Issue

Please do not create a public GitLab issue for security vulnerabilities, as this could put users at risk.

### 2. Report Privately

Report the vulnerability using one of these methods:

- **Confidential Issue:** Create a confidential issue on GitLab at https://gitlab.com/shebe-oss/shebe/-/issues/new
  - Select "This issue is confidential"
  - Use the label `security`

- **Email:** Send details to the maintainers through GitLab's contact feature

### 3. Provide Details

Please include the following information in your report:

- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact of the vulnerability
- Any suggested fixes (if you have them)
- Your contact information for follow-up

### 4. Response Timeline

We aim to:

- **Acknowledge** your report within 48 hours
- **Provide an initial assessment** within 7 days
- **Release a fix** within 30 days for confirmed vulnerabilities

### 5. Disclosure Policy

- We will work with you to understand and resolve the issue
- We ask that you do not publicly disclose the vulnerability until we have released a fix
- We will credit you in the security advisory (unless you prefer to remain anonymous)

## Security Best Practices

When using Shebe:

### For Deployment

1. **Access Control:**
   - Limit filesystem access to the shebe-mcp binary
   - Restrict which repositories can be indexed
   - Use appropriate file permissions for session data

2. **Network Security:**
   - If using the HTTP server, use HTTPS in production
   - Implement authentication if exposing the API
   - Use firewalls to restrict access

3. **Data Privacy:**
   - Be aware that indexed code is stored locally
   - Session data is stored in `~/.local/state/shebe/sessions/`
   - Ensure proper permissions on session directories

### For Development

1. **Dependencies:**
   - Regularly update Rust dependencies
   - Review security advisories for transitive dependencies
   - Run `cargo audit` periodically

2. **Code Review:**
   - All code changes require review before merging
   - Security-sensitive changes require additional scrutiny
   - Use `cargo clippy` to catch common issues

3. **Testing:**
   - Maintain test coverage above 85%
   - Include security test cases
   - Test with potentially malicious input

## Known Security Considerations

### File System Access

Shebe requires filesystem access to:
- Read source code files for indexing
- Write session data to `~/.local/state/shebe/`

**Mitigation:** Run with minimum required permissions

### Search Query Injection

The search service uses Tantivy's query parser, which is designed to safely handle user input.

**Mitigation:** Input is parsed and validated before execution

### Path Traversal

File paths are validated to prevent directory traversal attacks.

**Mitigation:** All paths are checked and sanitized

## Security Updates

Security updates will be released as:
- **Patch releases** for non-breaking fixes (0.4.1, 0.4.2, etc.)
- **Minor releases** if breaking changes are required

Subscribe to releases on GitLab to stay informed:
https://gitlab.com/shebe-oss/shebe/-/releases

## Acknowledgments

We appreciate the security researchers and community members who help keep Shebe secure by responsibly disclosing vulnerabilities.

---

**Last Updated:** 2025-10-31
