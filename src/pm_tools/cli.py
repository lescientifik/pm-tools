"""CLI entry point for pm-tools.

The `pm` command provides a unified interface with subcommands:
  pm search, pm fetch, pm parse, pm filter, pm cite, pm download, pm diff, pm refs, pm collect
"""

import argparse
import io
import json
import sys

from pm_tools import audit, cite, diff, download, fetch, filter, init, parse, refs, search
from pm_tools.args import positive_int
from pm_tools.cache import find_pm_dir
from pm_tools.io import safe_parse


def _build_collect_parser() -> argparse.ArgumentParser:
    """Build argument parser for pm collect."""
    parser = argparse.ArgumentParser(
        prog="pm collect",
        description="Collect PubMed articles (search + fetch + parse -> JSONL).",
    )
    parser.add_argument(
        "--csl", action="store_true", help="Output CSL-JSON instead of ArticleRecord"
    )
    parser.add_argument(
        "-n",
        "--max",
        type=positive_int,
        default=100,
        dest="max_results",
        help="Maximum results (default: 100)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show progress on stderr")
    parser.add_argument(
        "--refresh", action="store_true", help="Bypass cache and re-fetch from API"
    )
    parser.add_argument("query_words", nargs="*", help="PubMed search query")
    return parser


def collect_main(argv: list[str] | None = None) -> int:
    """Collect articles: pm search | pm fetch | pm parse in one command."""
    raw_args = argv if argv is not None else sys.argv[1:]

    parser = _build_collect_parser()
    args, code = safe_parse(parser, raw_args)
    if args is None:
        return 2 if code != 0 else 0

    query = " ".join(args.query_words)
    if not query.strip():
        print("Error: Query cannot be empty", file=sys.stderr)
        return 1

    if args.verbose:
        print(f'Searching PubMed: "{query}" (max {args.max_results})...', file=sys.stderr)

    try:
        detected_pm_dir = find_pm_dir()

        pmids = search.search(
            query,
            args.max_results,
            pm_dir=detected_pm_dir,
            refresh=args.refresh,
            verbose=args.verbose,
        )
        if not pmids:
            return 0

        xml = fetch.fetch(
            pmids,
            verbose=args.verbose,
            pm_dir=detected_pm_dir,
            refresh=args.refresh,
        )
        if not xml:
            return 0

        for article in parse.parse_xml_stream(io.BytesIO(xml.encode("utf-8"))):
            output = parse.format_article(article, csl=args.csl)
            print(json.dumps(output, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# --- Unified `pm` entry point ---

SUBCOMMANDS = {
    "init": init.main,
    "search": search.main,
    "fetch": fetch.main,
    "parse": parse.main,
    "filter": filter.main,
    "cite": cite.main,
    "download": download.main,
    "refs": refs.main,
    "diff": diff.main,
    "audit": audit.main,
    "collect": collect_main,
}

MAIN_HELP = """\
pm - PubMed CLI tools for AI agents

Usage: pm <command> [OPTIONS]

Recommended workflow:
  pm collect     Search + fetch + parse in one command (RECOMMENDED)
  pm filter      Filter JSONL articles by year, journal, author, etc.

All commands:
  collect     Search + fetch + parse in one command (RECOMMENDED)
  search      Search PubMed, return PMIDs
  fetch       Fetch PubMed XML by PMIDs
  parse       Parse PubMed XML to JSONL
  filter      Filter JSONL articles by field patterns
  cite        Fetch CSL-JSON citations
  download    Download full-text articles (NXML or PDF)
  refs        Extract cited PMIDs/DOIs from NXML files
  diff        Compare two JSONL files by PMID
  audit       View audit trail and PRISMA report
  init        Initialize audit trail and cache (.pm/)

Examples:
  pm collect "CRISPR cancer" --max 100 > results.jsonl
  pm filter --year 2024 --has-abstract < results.jsonl

Tip: save results to a file so you can reuse them without re-searching:
  pm collect "my query" > results.jsonl
  pm filter --year 2024 < results.jsonl
  pm filter --has-doi < results.jsonl

Use 'pm <command> --help' for command-specific help."""


def main() -> None:
    """Main `pm` entry point with subcommands."""
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print(MAIN_HELP)
        sys.exit(0)

    if args[0] == "--version":
        from pm_tools import __version__

        print(f"pm-tools {__version__}")
        sys.exit(0)

    cmd = args[0]
    if cmd not in SUBCOMMANDS:
        print(f"Error: Unknown command '{cmd}'", file=sys.stderr)
        # Suggest similar commands
        from difflib import get_close_matches

        matches = get_close_matches(cmd, SUBCOMMANDS.keys(), n=1, cutoff=0.5)
        if matches:
            print(f"Did you mean: {matches[0]}", file=sys.stderr)
        print("hint: use 'pm --help' to see available commands", file=sys.stderr)
        sys.exit(2)

    handler = SUBCOMMANDS[cmd]
    result = handler(args[1:])
    sys.exit(result or 0)
