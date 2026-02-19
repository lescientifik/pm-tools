"""CLI entry point for pm-tools.

The `pm` command provides a unified interface with subcommands:
  pm search, pm fetch, pm parse, pm filter, pm cite, pm download, pm diff, pm quick
"""

import sys

from pm_tools import audit, cite, diff, download, fetch, filter, init, parse, search


def quick_main() -> None:
    """Quick search: pm search | pm fetch | pm parse in one command."""
    args = sys.argv[1:]

    max_results = 100
    query = ""
    verbose = False
    i = 0

    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(QUICK_HELP)
            sys.exit(0)
        elif arg in ("--verbose", "-v"):
            verbose = True
        elif arg == "--max":
            i += 1
            if i >= len(args):
                print("Error: --max requires a number", file=sys.stderr)
                sys.exit(2)
            try:
                max_results = int(args[i])
            except ValueError:
                print(f"Error: --max requires a number, got '{args[i]}'", file=sys.stderr)
                sys.exit(2)
        elif arg.startswith("--max="):
            try:
                max_results = int(arg.split("=", 1)[1])
            except ValueError:
                print("Error: --max requires a number", file=sys.stderr)
                sys.exit(2)
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            sys.exit(1)
        else:
            if query:
                print(
                    "Error: Only one query allowed. Use quotes for multi-word queries.",
                    file=sys.stderr,
                )
                sys.exit(1)
            query = arg
        i += 1

    if not query:
        print("Error: Missing query argument", file=sys.stderr)
        print('Usage: pm quick [OPTIONS] "search query"', file=sys.stderr)
        sys.exit(1)

    if not query.strip():
        print("Error: Query cannot be empty", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f'Searching PubMed: "{query}" (max {max_results})...', file=sys.stderr)

    try:
        import json

        from pm_tools.cache import find_pm_dir

        detected_pm_dir = find_pm_dir()

        pmids = search.search(
            query,
            max_results,
            cache_dir=detected_pm_dir,
            pm_dir=detected_pm_dir,
        )
        if not pmids:
            sys.exit(0)

        xml = fetch.fetch(
            pmids,
            verbose=verbose,
            cache_dir=detected_pm_dir,
            pm_dir=detected_pm_dir,
        )
        if not xml:
            sys.exit(0)

        articles = parse.parse_xml(xml)
        for article in articles:
            print(json.dumps(article, ensure_ascii=False))
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


QUICK_HELP = """\
pm quick - Quick PubMed search (outputs JSONL)

Usage: pm quick [OPTIONS] "search query"

Options:
  --max N         Maximum results (default: 100)
  -v, --verbose   Show progress on stderr
  -h, --help      Show this help message

Output:
  JSONL to stdout (one article per line)

Examples:
  pm quick "CRISPR cancer therapy"
  pm quick --max 20 "machine learning diagnosis"

For advanced filtering, use the full pipeline:
  pm search "query" | pm fetch | pm parse | pm filter --year 2024"""


# --- Unified `pm` entry point ---

SUBCOMMANDS = {
    "init": init.main,
    "search": search.main,
    "fetch": fetch.main,
    "parse": parse.main,
    "filter": filter.main,
    "cite": cite.main,
    "download": download.main,
    "diff": diff.main,
    "audit": audit.main,
    "quick": lambda args=None: quick_main(),
}

MAIN_HELP = """\
pm - PubMed CLI tools for AI agents

Usage: pm <command> [OPTIONS]

Commands:
  init        Initialize audit trail and cache (.pm/)
  search      Search PubMed, return PMIDs
  fetch       Fetch PubMed XML by PMIDs
  parse       Parse PubMed XML to JSONL
  filter      Filter JSONL articles by field patterns
  cite        Fetch CSL-JSON citations
  download    Download full-text PDFs
  diff        Compare two JSONL files by PMID
  audit       View audit trail and PRISMA report
  quick       One-command search pipeline (outputs JSONL)

Examples:
  pm search "CRISPR cancer" | pm fetch | pm parse > results.jsonl
  pm quick "covid vaccine" --max 50
  pm filter --year 2024 --has-abstract < articles.jsonl

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
