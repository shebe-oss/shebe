#!/usr/bin/env python3
"""
Analyze Claude Code context usage with and without serena-mcp.

Compares:
1. Sessions that used serena tools vs sessions that didn't
2. Token consumption per tool call
3. Context exhaustion patterns

Output: Data to inform whether a lightweight find_references tool in shebe is needed.
"""

import os
import re
import json
import sys
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ToolCall:
    """Single tool invocation."""
    tool_name: str
    timestamp: Optional[str] = None
    duration_ms: Optional[int] = None
    success: bool = True
    error: Optional[str] = None


@dataclass
class SessionStats:
    """Statistics for a single Claude Code session."""
    session_id: str
    file_path: str
    file_size_bytes: int
    tool_calls: list = field(default_factory=list)
    serena_calls: int = 0
    shebe_calls: int = 0
    other_mcp_calls: int = 0
    builtin_calls: int = 0
    has_serena: bool = False
    has_shebe: bool = False
    # Estimated from file size (rough proxy for context)
    estimated_tokens: int = 0


class ContextAnalyzer:
    """Analyze context usage patterns from debug logs."""

    # Tool call patterns
    TOOL_CALL_PATTERN = re.compile(
        r'MCP server "(\w+)": Calling MCP tool: (\w+)'
    )
    TOOL_SUCCESS_PATTERN = re.compile(
        r'MCP server "(\w+)": Tool \'(\w+)\' completed'
    )
    TOOL_FAIL_PATTERN = re.compile(
        r'MCP server "(\w+)": Tool \'(\w+)\' failed'
    )
    BUILTIN_TOOL_PATTERN = re.compile(
        r'executePreToolHooks called for tool: (Read|Write|Edit|Glob|Grep|Bash|Task)'
    )

    # Serena-specific patterns (verbose output detection)
    SERENA_SYMBOL_PATTERN = re.compile(r'mcp__serena__find_symbol')
    SERENA_PATTERN_PATTERN = re.compile(r'mcp__serena__search_for_pattern')
    SERENA_OVERVIEW_PATTERN = re.compile(r'mcp__serena__get_symbols_overview')

    def __init__(self, debug_dir: str):
        self.debug_dir = Path(debug_dir)
        self.sessions: list[SessionStats] = []

    def analyze(self) -> dict:
        """Run full analysis."""
        if not self.debug_dir.exists():
            print(f"Debug directory not found: {self.debug_dir}")
            return {}

        log_files = list(self.debug_dir.glob("*.txt"))
        print(f"Analyzing {len(log_files)} debug log files...")

        for log_file in log_files:
            stats = self._analyze_session(log_file)
            if stats and (stats.serena_calls > 0 or stats.shebe_calls > 0 or
                          stats.builtin_calls > 5):
                self.sessions.append(stats)

        return self._generate_report()

    def _analyze_session(self, log_file: Path) -> Optional[SessionStats]:
        """Analyze a single session log file."""
        try:
            content = log_file.read_text(errors='ignore')
            file_size = log_file.stat().st_size
        except Exception as e:
            return None

        stats = SessionStats(
            session_id=log_file.stem,
            file_path=str(log_file),
            file_size_bytes=file_size,
            # Rough estimate: ~4 chars per token on average
            estimated_tokens=file_size // 4
        )

        # Count tool calls by type
        for line in content.split('\n'):
            # MCP tool calls
            mcp_match = self.TOOL_CALL_PATTERN.search(line)
            if mcp_match:
                server = mcp_match.group(1)
                tool = mcp_match.group(2)

                if server == 'serena':
                    stats.serena_calls += 1
                    stats.has_serena = True
                    stats.tool_calls.append(ToolCall(
                        tool_name=f"serena__{tool}"
                    ))
                elif server == 'shebe':
                    stats.shebe_calls += 1
                    stats.has_shebe = True
                    stats.tool_calls.append(ToolCall(
                        tool_name=f"shebe__{tool}"
                    ))
                else:
                    stats.other_mcp_calls += 1

            # Builtin tool calls
            builtin_match = self.BUILTIN_TOOL_PATTERN.search(line)
            if builtin_match:
                stats.builtin_calls += 1

        return stats if stats.tool_calls or stats.builtin_calls > 0 else None

    def _generate_report(self) -> dict:
        """Generate comparison report."""
        # Categorize sessions
        serena_only = [s for s in self.sessions if s.has_serena and not s.has_shebe]
        shebe_only = [s for s in self.sessions if s.has_shebe and not s.has_serena]
        both = [s for s in self.sessions if s.has_serena and s.has_shebe]
        neither = [s for s in self.sessions if not s.has_serena and not s.has_shebe]

        report = {
            'summary': {
                'total_sessions_analyzed': len(self.sessions),
                'sessions_with_serena_only': len(serena_only),
                'sessions_with_shebe_only': len(shebe_only),
                'sessions_with_both': len(both),
                'sessions_with_neither': len(neither),
            },
            'serena_sessions': self._aggregate_stats(serena_only + both, 'serena'),
            'shebe_sessions': self._aggregate_stats(shebe_only + both, 'shebe'),
            'no_mcp_sessions': self._aggregate_stats(neither, 'none'),
            'comparison': {},
            'tool_call_breakdown': self._tool_breakdown(),
        }

        # Calculate comparison metrics
        if serena_only:
            serena_avg_size = sum(s.file_size_bytes for s in serena_only) / len(serena_only)
            serena_avg_calls = sum(s.serena_calls for s in serena_only) / len(serena_only)
        else:
            serena_avg_size = 0
            serena_avg_calls = 0

        if shebe_only:
            shebe_avg_size = sum(s.file_size_bytes for s in shebe_only) / len(shebe_only)
            shebe_avg_calls = sum(s.shebe_calls for s in shebe_only) / len(shebe_only)
        else:
            shebe_avg_size = 0
            shebe_avg_calls = 0

        if neither:
            neither_avg_size = sum(s.file_size_bytes for s in neither) / len(neither)
        else:
            neither_avg_size = 0

        report['comparison'] = {
            'avg_log_size_serena_sessions_kb': serena_avg_size / 1024,
            'avg_log_size_shebe_sessions_kb': shebe_avg_size / 1024,
            'avg_log_size_no_mcp_sessions_kb': neither_avg_size / 1024,
            'avg_serena_calls_per_session': serena_avg_calls,
            'avg_shebe_calls_per_session': shebe_avg_calls,
            'serena_vs_shebe_size_ratio': (
                serena_avg_size / shebe_avg_size if shebe_avg_size > 0 else 0
            ),
        }

        return report

    def _aggregate_stats(self, sessions: list, label: str) -> dict:
        """Aggregate statistics for a group of sessions."""
        if not sessions:
            return {
                'count': 0,
                'total_file_size_mb': 0,
                'avg_file_size_kb': 0,
                'total_tool_calls': 0,
                'avg_tool_calls': 0,
            }

        total_size = sum(s.file_size_bytes for s in sessions)
        total_calls = sum(len(s.tool_calls) for s in sessions)

        return {
            'count': len(sessions),
            'total_file_size_mb': total_size / (1024 * 1024),
            'avg_file_size_kb': (total_size / len(sessions)) / 1024,
            'total_tool_calls': total_calls,
            'avg_tool_calls': total_calls / len(sessions),
            'estimated_total_tokens': sum(s.estimated_tokens for s in sessions),
            'estimated_avg_tokens': sum(s.estimated_tokens for s in sessions) / len(sessions),
        }

    def _tool_breakdown(self) -> dict:
        """Break down tool calls by specific tool."""
        tool_counts = defaultdict(int)
        tool_sessions = defaultdict(set)

        for session in self.sessions:
            for call in session.tool_calls:
                tool_counts[call.tool_name] += 1
                tool_sessions[call.tool_name].add(session.session_id)

        return {
            tool: {
                'total_calls': count,
                'sessions_used': len(tool_sessions[tool])
            }
            for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1])
        }


def print_report(report: dict):
    """Print formatted report."""
    print("\n" + "=" * 80)
    print("SERENA vs SHEBE CONTEXT USAGE ANALYSIS")
    print("=" * 80)

    summary = report['summary']
    print(f"\n--- Session Distribution ---")
    print(f"  Total sessions analyzed: {summary['total_sessions_analyzed']}")
    print(f"  Sessions with serena only: {summary['sessions_with_serena_only']}")
    print(f"  Sessions with shebe only: {summary['sessions_with_shebe_only']}")
    print(f"  Sessions with both: {summary['sessions_with_both']}")
    print(f"  Sessions with neither: {summary['sessions_with_neither']}")

    print(f"\n--- Serena Sessions ---")
    serena = report['serena_sessions']
    print(f"  Count: {serena['count']}")
    print(f"  Avg log size: {serena['avg_file_size_kb']:.1f} KB")
    print(f"  Avg tool calls: {serena['avg_tool_calls']:.1f}")
    if serena.get('estimated_avg_tokens'):
        print(f"  Estimated avg tokens: {serena['estimated_avg_tokens']:,.0f}")

    print(f"\n--- Shebe Sessions ---")
    shebe = report['shebe_sessions']
    print(f"  Count: {shebe['count']}")
    print(f"  Avg log size: {shebe['avg_file_size_kb']:.1f} KB")
    print(f"  Avg tool calls: {shebe['avg_tool_calls']:.1f}")
    if shebe.get('estimated_avg_tokens'):
        print(f"  Estimated avg tokens: {shebe['estimated_avg_tokens']:,.0f}")

    print(f"\n--- No MCP Sessions (baseline) ---")
    none = report['no_mcp_sessions']
    print(f"  Count: {none['count']}")
    print(f"  Avg log size: {none['avg_file_size_kb']:.1f} KB")

    print(f"\n--- Comparison ---")
    comp = report['comparison']
    print(f"  Avg log size (serena): {comp['avg_log_size_serena_sessions_kb']:.1f} KB")
    print(f"  Avg log size (shebe): {comp['avg_log_size_shebe_sessions_kb']:.1f} KB")
    print(f"  Avg log size (no mcp): {comp['avg_log_size_no_mcp_sessions_kb']:.1f} KB")
    print(f"  Serena/Shebe size ratio: {comp['serena_vs_shebe_size_ratio']:.2f}x")
    print(f"  Avg serena calls/session: {comp['avg_serena_calls_per_session']:.1f}")
    print(f"  Avg shebe calls/session: {comp['avg_shebe_calls_per_session']:.1f}")

    print(f"\n--- Tool Call Breakdown (Top 20) ---")
    breakdown = report.get('tool_call_breakdown', {})
    for i, (tool, stats) in enumerate(list(breakdown.items())[:20]):
        print(f"  {tool}: {stats['total_calls']} calls across {stats['sessions_used']} sessions")

    # Analysis conclusion
    print("\n" + "=" * 80)
    print("ANALYSIS CONCLUSIONS")
    print("=" * 80)

    if comp['serena_vs_shebe_size_ratio'] > 1.5:
        print(f"""
[FINDING] Serena sessions have {comp['serena_vs_shebe_size_ratio']:.1f}x larger logs than shebe sessions.

This suggests serena-mcp tools may return more verbose output, consuming more context.
A lightweight find_references tool in shebe could be more token-efficient.

RECOMMENDATION: Proceed with shebe find_references implementation.
""")
    elif comp['serena_vs_shebe_size_ratio'] > 1.0:
        print(f"""
[FINDING] Serena sessions are {comp['serena_vs_shebe_size_ratio']:.1f}x larger than shebe sessions.

Modest difference - both tools have similar context footprint.
Shebe find_references may still be valuable for:
- Simpler API (no LSP setup required)
- Purpose-built for rename workflows
- Confidence scoring for LLM decision-making

RECOMMENDATION: Consider implementing, but lower priority.
""")
    else:
        print(f"""
[FINDING] Shebe sessions are actually larger than serena sessions.

This could indicate:
- Shebe tools are verbose in different ways
- Different usage patterns (more search queries)
- Sample size too small for conclusions

RECOMMENDATION: Gather more data before deciding.
""")


def main():
    debug_dir = os.path.expanduser("~/.claude/debug")

    if len(sys.argv) > 1:
        debug_dir = sys.argv[1]

    print(f"Analyzing Claude Code debug logs in: {debug_dir}")

    analyzer = ContextAnalyzer(debug_dir)
    report = analyzer.analyze()

    print_report(report)

    # Export JSON
    output_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "serena-context-analysis.json"
    )
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nJSON report exported to: {output_file}")


if __name__ == "__main__":
    main()
