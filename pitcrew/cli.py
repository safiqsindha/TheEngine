"""
pitcrew/cli.py — Command-line interface for DS log analysis.

Usage:
    python -m pitcrew.cli analyze <path/to/file.dslog> [--team TEAM] [--out FILE]
    python -m pitcrew.cli batch <directory> [--team TEAM] [--out FILE]

The analyze command prints a single-match markdown report to stdout.
The batch command prints a comparison table for all .dslog files in a directory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pitcrew.dslog import analyze, batch_analyze
from pitcrew.report import generate, generate_batch_table


def cmd_analyze(args: argparse.Namespace) -> int:
    path = Path(args.path)
    try:
        analysis = analyze(path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 — CLI error boundary; unknown parse errors surfaced to user
        print(f"ERROR parsing {path}: {e}", file=sys.stderr)
        return 1

    report = generate(analysis, team=args.team)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"Report written to {out_path}")
    else:
        print(report)

    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    try:
        analyses = batch_analyze(directory)
    except NotADirectoryError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not analyses:
        print(f"No .dslog files found in {directory}")
        return 0

    table = generate_batch_table(analyses, team=args.team)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(table)
        print(f"Batch report written to {out_path}")
    else:
        print(table)

    # Print individual reports after the table
    if not args.table_only:
        print()
        for a in analyses:
            print("-" * 60)
            print(generate(a, team=args.team))
            print()

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pitcrew",
        description="Pit Crew DS Log analyzer — Team 2950 The Devastators",
    )
    parser.add_argument(
        "--team", default="2950", help="Team number label for reports (default: 2950)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze a single .dslog file and print a match report"
    )
    analyze_parser.add_argument("path", help="Path to a .dslog file")
    analyze_parser.add_argument(
        "--out", default="", help="Write report to this file instead of stdout"
    )

    # batch subcommand
    batch_parser = subparsers.add_parser(
        "batch",
        help="Batch-analyze all .dslog files in a directory and print a comparison table",
    )
    batch_parser.add_argument("directory", help="Directory containing .dslog files")
    batch_parser.add_argument(
        "--out", default="", help="Write report to this file instead of stdout"
    )
    batch_parser.add_argument(
        "--table-only",
        action="store_true",
        help="Print only the comparison table, not individual reports",
    )

    args = parser.parse_args(argv)

    if args.command == "analyze":
        return cmd_analyze(args)
    elif args.command == "batch":
        return cmd_batch(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
