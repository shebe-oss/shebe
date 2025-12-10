#!/usr/bin/env python3
"""
Analyze Claude Code context errors related to shebe-mcp tools.

This script parses Claude Code debug logs to identify patterns where:
1. Tool calls fail due to parameter validation errors
2. Query syntax causes parsing failures
3. Session management issues occur
4. File access patterns fail

Output: Categorized error analysis with actionable improvement recommendations.
"""

import os
import re
import sys
import json
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ErrorPattern:
    """Represents a categorized error pattern."""
    category: str
    pattern: str
    count: int = 0
    examples: list = field(default_factory=list)
    improvement: str = ""


@dataclass
class AnalysisResult:
    """Aggregated analysis results."""
    total_errors: int = 0
    by_tool: dict = field(default_factory=lambda: defaultdict(int))
    by_category: dict = field(default_factory=lambda: defaultdict(list))
    query_syntax_errors: list = field(default_factory=list)
    session_errors: list = field(default_factory=list)
    file_errors: list = field(default_factory=list)
    other_errors: list = field(default_factory=list)


class ShebeErrorAnalyzer:
    """Analyzes Claude Code debug logs for shebe-mcp related errors."""

    # Regex patterns for extracting error information
    TOOL_FAIL_PATTERN = re.compile(
        r'Tool \'(\w+)\' failed.*?: (.+?)(?:\n|$)'
    )
    MCP_ERROR_PATTERN = re.compile(
        r'MCP error (-?\d+): (.+?)(?:\"|$)'
    )
    QUERY_SYNTAX_PATTERN = re.compile(
        r'Syntax Error: (.+?)(?:\"|$)'
    )
    FIELD_NOT_EXIST_PATTERN = re.compile(
        r'Field does not exist: \'(\w+)\''
    )
    SESSION_EXISTS_PATTERN = re.compile(
        r'Session \'([^\']+)\' already exists'
    )
    OLD_SCHEMA_PATTERN = re.compile(
        r'Session \'([^\']+)\' uses old schema version (\d+)'
    )
    FILE_NOT_INDEXED_PATTERN = re.compile(
        r'File \'([^\']+)\' not indexed in session \'([^\']+)\''
    )
    TOOL_NOT_FOUND_PATTERN = re.compile(
        r'Tool (mcp__shebe__\w+) not found'
    )

    def __init__(self, debug_dir: str):
        self.debug_dir = Path(debug_dir)
        self.result = AnalysisResult()
        self.error_patterns = {}

    def analyze(self) -> AnalysisResult:
        """Run the full analysis on debug logs."""
        if not self.debug_dir.exists():
            print(f"Debug directory not found: {self.debug_dir}")
            return self.result

        log_files = list(self.debug_dir.glob("*.txt"))
        print(f"Analyzing {len(log_files)} debug log files...")

        for log_file in log_files:
            self._analyze_file(log_file)

        self._categorize_errors()
        return self.result

    def _analyze_file(self, log_file: Path):
        """Analyze a single debug log file."""
        try:
            content = log_file.read_text(errors='ignore')
        except Exception as e:
            print(f"Error reading {log_file}: {e}")
            return

        # Find all shebe-related error lines
        for line in content.split('\n'):
            if 'shebe' not in line.lower():
                continue

            self._extract_errors(line)

    def _extract_errors(self, line: str):
        """Extract error information from a log line."""
        # Tool failure pattern
        tool_match = self.TOOL_FAIL_PATTERN.search(line)
        if tool_match:
            tool_name = tool_match.group(1)
            error_msg = tool_match.group(2)
            self.result.total_errors += 1
            self.result.by_tool[tool_name] += 1

            # Categorize the error
            self._categorize_error(tool_name, error_msg)

        # Tool not found pattern
        not_found = self.TOOL_NOT_FOUND_PATTERN.search(line)
        if not_found:
            tool_name = not_found.group(1)
            self.result.total_errors += 1
            self.result.by_tool['tool_not_found'] += 1
            self.result.other_errors.append({
                'type': 'tool_not_found',
                'tool': tool_name,
                'message': f'Server not running when {tool_name} was called'
            })

    def _categorize_error(self, tool_name: str, error_msg: str):
        """Categorize an error message."""
        # Query syntax errors
        syntax_match = self.QUERY_SYNTAX_PATTERN.search(error_msg)
        if syntax_match:
            query = syntax_match.group(1).strip()
            self.result.query_syntax_errors.append({
                'tool': tool_name,
                'query': query,
                'category': self._classify_query_error(query)
            })
            return

        # Field not exist errors
        field_match = self.FIELD_NOT_EXIST_PATTERN.search(error_msg)
        if field_match:
            field_name = field_match.group(1)
            self.result.query_syntax_errors.append({
                'tool': tool_name,
                'query': f'{field_name}:...',
                'category': 'field_prefix',
                'field': field_name
            })
            return

        # Session already exists
        exists_match = self.SESSION_EXISTS_PATTERN.search(error_msg)
        if exists_match:
            session = exists_match.group(1)
            self.result.session_errors.append({
                'tool': tool_name,
                'session': session,
                'category': 'session_exists'
            })
            return

        # Old schema version
        schema_match = self.OLD_SCHEMA_PATTERN.search(error_msg)
        if schema_match:
            session = schema_match.group(1)
            version = schema_match.group(2)
            self.result.session_errors.append({
                'tool': tool_name,
                'session': session,
                'category': 'schema_mismatch',
                'old_version': version
            })
            return

        # File not indexed
        file_match = self.FILE_NOT_INDEXED_PATTERN.search(error_msg)
        if file_match:
            file_path = file_match.group(1)
            session = file_match.group(2)
            self.result.file_errors.append({
                'tool': tool_name,
                'file': file_path,
                'session': session,
                'category': 'file_not_indexed'
            })
            return

        # Unsupported query type
        if 'Unsupported query' in error_msg:
            self.result.query_syntax_errors.append({
                'tool': tool_name,
                'category': 'unsupported_query',
                'message': error_msg
            })
            return

        # Response too large
        if 'exceeds maximum allowed tokens' in error_msg:
            self.result.file_errors.append({
                'tool': tool_name,
                'category': 'response_too_large',
                'message': error_msg
            })
            return

        # Session name validation
        if 'Session must contain only' in error_msg:
            self.result.session_errors.append({
                'tool': tool_name,
                'category': 'invalid_session_name'
            })
            return

        # Other errors
        self.result.other_errors.append({
            'tool': tool_name,
            'message': error_msg
        })

    def _classify_query_error(self, query: str) -> str:
        """Classify a query syntax error into subcategories."""
        # URL-like patterns
        if re.search(r'/\w+/\{?\w+\}?', query):
            return 'url_pattern'

        # Go swagger annotations
        if '@Router' in query or '@' in query.split()[0] if query else '':
            return 'annotation'

        # Assignment-like patterns
        if ':=' in query:
            return 'assignment'

        # Colon-prefixed field search
        if re.search(r'^\w+:', query):
            return 'field_prefix'

        # Multiple special characters
        if re.search(r'[:\[\]{}]', query):
            return 'special_chars'

        # Multi-word phrase that might need quoting
        if len(query.split()) > 3:
            return 'complex_phrase'

        return 'other'

    def _categorize_errors(self):
        """Aggregate errors by category for reporting."""
        # Query errors by subcategory
        for err in self.result.query_syntax_errors:
            cat = err.get('category', 'unknown')
            self.result.by_category[f'query_{cat}'].append(err)

        # Session errors by subcategory
        for err in self.result.session_errors:
            cat = err.get('category', 'unknown')
            self.result.by_category[f'session_{cat}'].append(err)

        # File errors by subcategory
        for err in self.result.file_errors:
            cat = err.get('category', 'unknown')
            self.result.by_category[f'file_{cat}'].append(err)


def generate_improvements(result: AnalysisResult) -> list:
    """Generate improvement recommendations based on analysis."""
    improvements = []

    # Query syntax improvements
    query_cats = {k: v for k, v in result.by_category.items() if k.startswith('query_')}
    if query_cats:
        url_count = len(query_cats.get('query_url_pattern', []))
        annotation_count = len(query_cats.get('query_annotation', []))
        field_count = len(query_cats.get('query_field_prefix', []))
        special_count = len(query_cats.get('query_special_chars', []))

        if url_count > 0:
            improvements.append({
                'category': 'Query Parsing - URL Patterns',
                'priority': 'HIGH',
                'issue': f'{url_count} queries failed with URL-like patterns '
                         f'(e.g., /users/{{id}}/roles)',
                'examples': [e.get('query') for e in query_cats.get('query_url_pattern', [])[:5]],
                'recommendation': 'Auto-quote queries containing URL path patterns. '
                                  'Detect patterns like /path/{param} and wrap in quotes.',
                'implementation': [
                    'Add URL pattern detection in query preprocessing',
                    'Auto-escape curly braces: {id} -> \\{id\\}',
                    'Consider supporting file_path: prefix for path searches',
                    'Add helpful error message suggesting find_file for paths'
                ]
            })

        if annotation_count > 0:
            improvements.append({
                'category': 'Query Parsing - Code Annotations',
                'priority': 'MEDIUM',
                'issue': f'{annotation_count} queries failed with annotation patterns '
                         f'(e.g., @Router, @Param)',
                'examples': [e.get('query') for e in query_cats.get('query_annotation', [])[:5]],
                'recommendation': 'Handle @ symbol in queries by escaping or quoting',
                'implementation': [
                    'Escape @ symbol in query preprocessing',
                    'Document that annotations should be quoted',
                    'Add @-pattern aware tokenization'
                ]
            })

        if field_count > 0:
            improvements.append({
                'category': 'Query Parsing - Field Prefixes',
                'priority': 'MEDIUM',
                'issue': f'{field_count} queries used non-existent field prefixes '
                         f'(e.g., file:, admin:)',
                'examples': [e.get('field', 'unknown') for e in
                             query_cats.get('query_field_prefix', [])[:5]],
                'recommendation': 'Better error messages listing available fields, '
                                  'or auto-strip unknown field prefixes',
                'implementation': [
                    'Return list of valid fields in error message',
                    'Add content: as default field prefix',
                    'Support file_path: field for filename searches',
                    'Consider fuzzy matching for typos in field names'
                ]
            })

        if special_count > 0:
            improvements.append({
                'category': 'Query Parsing - Special Characters',
                'priority': 'MEDIUM',
                'issue': f'{special_count} queries failed due to special characters',
                'examples': [e.get('query') for e in query_cats.get('query_special_chars', [])[:5]],
                'recommendation': 'Auto-escape or strip problematic characters',
                'implementation': [
                    'Pre-process queries to escape [ ] { } characters',
                    'Add literal search mode that escapes all special chars',
                    'Document BM25 query syntax in tool description'
                ]
            })

    # Session management improvements
    session_cats = {k: v for k, v in result.by_category.items() if k.startswith('session_')}
    if session_cats:
        exists_count = len(session_cats.get('session_session_exists', []))
        schema_count = len(session_cats.get('session_schema_mismatch', []))

        if exists_count > 0:
            sessions = set(e.get('session') for e in
                           session_cats.get('session_session_exists', []))
            improvements.append({
                'category': 'Session Management - Auto Re-index',
                'priority': 'HIGH',
                'issue': f'{exists_count} index_repository calls failed because '
                         f'session exists ({len(sessions)} unique sessions)',
                'examples': list(sessions)[:5],
                'recommendation': 'Change default behavior or improve UX for re-indexing',
                'implementation': [
                    'Option 1: Default force=true for index_repository',
                    'Option 2: Add smart_index tool that auto-detects need for re-index',
                    'Option 3: Return session info instead of error when exists',
                    'Option 4: Add check_session tool to verify if index is fresh',
                    'Include last_indexed timestamp in error to help LLM decide'
                ]
            })

        if schema_count > 0:
            improvements.append({
                'category': 'Session Management - Schema Migration',
                'priority': 'HIGH',
                'issue': f'{schema_count} operations failed due to schema version mismatch',
                'examples': list(set(e.get('session') for e in
                                     session_cats.get('session_schema_mismatch', [])))[:5],
                'recommendation': 'Auto-migrate or provide clear migration path',
                'implementation': [
                    'Add auto_migrate flag to search_code/read_file',
                    'Add migrate_session tool for explicit upgrades',
                    'Include schema version in list_sessions output',
                    'On startup, log warning about outdated sessions',
                    'Consider automatic background migration on first access'
                ]
            })

    # File access improvements
    file_cats = {k: v for k, v in result.by_category.items() if k.startswith('file_')}
    if file_cats:
        not_indexed_count = len(file_cats.get('file_file_not_indexed', []))

        if not_indexed_count > 0:
            improvements.append({
                'category': 'File Access - Not Indexed',
                'priority': 'MEDIUM',
                'issue': f'{not_indexed_count} read_file calls failed for unindexed files',
                'recommendation': 'Better error recovery for unindexed files',
                'implementation': [
                    'Return partial index info (was file excluded by patterns?)',
                    'Suggest reindex with different include_patterns',
                    'Add fallback_read option to read directly from disk',
                    'Include exclude pattern that blocked file in error'
                ]
            })

    # Tool availability
    tool_not_found = result.by_tool.get('tool_not_found', 0)
    if tool_not_found > 0:
        improvements.append({
            'category': 'Server Availability',
            'priority': 'LOW',
            'issue': f'{tool_not_found} tool calls failed because server was not running',
            'recommendation': 'Improve server startup/discovery',
            'implementation': [
                'Add health check endpoint for MCP clients',
                'Document auto-start configuration for Claude Code',
                'Consider lazy initialization on first tool call'
            ]
        })

    return improvements


def print_report(result: AnalysisResult, improvements: list):
    """Print the analysis report."""
    print("\n" + "=" * 80)
    print("SHEBE-MCP ERROR ANALYSIS REPORT")
    print("=" * 80)

    print(f"\nTotal Errors Analyzed: {result.total_errors}")

    print("\n--- Errors by Tool ---")
    for tool, count in sorted(result.by_tool.items(), key=lambda x: -x[1]):
        print(f"  {tool}: {count}")

    print("\n--- Errors by Category ---")
    for cat, errors in sorted(result.by_category.items(), key=lambda x: -len(x[1])):
        print(f"  {cat}: {len(errors)}")

    print("\n" + "=" * 80)
    print("IMPROVEMENT RECOMMENDATIONS")
    print("=" * 80)

    for i, imp in enumerate(improvements, 1):
        print(f"\n{i}. [{imp['priority']}] {imp['category']}")
        print(f"   Issue: {imp['issue']}")
        if imp.get('examples'):
            print(f"   Examples: {imp['examples'][:3]}")
        print(f"   Recommendation: {imp['recommendation']}")
        print("   Implementation Steps:")
        for step in imp.get('implementation', []):
            print(f"     - {step}")

    print("\n" + "=" * 80)
    print("QUERY SYNTAX ERRORS (Sample)")
    print("=" * 80)
    for err in result.query_syntax_errors[:15]:
        q = err.get('query', err.get('message', 'unknown'))
        cat = err.get('category', 'unknown')
        print(f"  [{cat}] {q[:70]}{'...' if len(str(q)) > 70 else ''}")


def export_json(result: AnalysisResult, improvements: list, output_file: str):
    """Export analysis as JSON for further processing."""
    data = {
        'summary': {
            'total_errors': result.total_errors,
            'by_tool': dict(result.by_tool),
            'by_category': {k: len(v) for k, v in result.by_category.items()}
        },
        'query_syntax_errors': result.query_syntax_errors,
        'session_errors': result.session_errors,
        'file_errors': result.file_errors,
        'improvements': improvements
    }

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\nJSON report exported to: {output_file}")


def main():
    # Default to user's Claude debug directory
    debug_dir = os.path.expanduser("~/.claude/debug")

    if len(sys.argv) > 1:
        debug_dir = sys.argv[1]

    print(f"Analyzing Claude Code debug logs in: {debug_dir}")

    analyzer = ShebeErrorAnalyzer(debug_dir)
    result = analyzer.analyze()
    improvements = generate_improvements(result)

    print_report(result, improvements)

    # Export JSON report
    output_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "claude-error-analysis.json"
    )
    export_json(result, improvements, output_file)


if __name__ == "__main__":
    main()
