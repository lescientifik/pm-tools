"""pm refs: Extract cited PMIDs/DOIs from NXML (JATS) files."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def extract_refs(nxml_content: str, id_type: str = "pmid") -> list[str]:
    """Extract cited identifiers from an NXML file's <ref-list>.

    Args:
        nxml_content: NXML (JATS XML) content as a string.
        id_type: Type of identifier to extract ("pmid" or "doi").

    Returns:
        List of identifier strings, deduplicated and in document order.
        Returns empty list on invalid XML or if no matching refs found.
    """
    if not nxml_content or not nxml_content.strip():
        return []

    try:
        root = ET.fromstring(nxml_content)
    except ET.ParseError:
        return []

    refs: list[str] = []
    for ref_list in root.iter("ref-list"):
        for pub_id in ref_list.iter("pub-id"):
            if pub_id.get("pub-id-type") == id_type:
                text = pub_id.text
                if text and text.strip():
                    refs.append(text.strip())

    # Deduplicate preserving order
    return list(dict.fromkeys(refs))


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for pm refs."""
    parser = argparse.ArgumentParser(
        prog="pm refs",
        description="Extract cited PMIDs/DOIs from NXML (JATS) files.",
        epilog=(
            "Examples:\n"
            "  pm refs article.nxml\n"
            "  pm refs *.nxml | sort -u | pm fetch | pm parse\n"
            "  pm refs --doi article.nxml\n"
            "  pm refs ./articles/*.nxml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--doi",
        action="store_true",
        help="Extract DOIs instead of PMIDs",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="NXML files to process (reads stdin if omitted)",
    )
    return parser


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm refs."""
    parser = _build_parser()
    try:
        parsed = parser.parse_args(args)
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0

    id_type = "doi" if parsed.doi else "pmid"
    files: list[str] = parsed.files

    # Collect all refs across files, deduplicated
    all_refs: list[str] = []
    had_error = False

    if files:
        for filepath in files:
            try:
                with open(filepath) as f:
                    content = f.read()
            except OSError as e:
                print(f"Error: {e}", file=sys.stderr)
                had_error = True
                continue
            refs = extract_refs(content, id_type=id_type)
            all_refs.extend(refs)
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
        refs = extract_refs(content, id_type=id_type)
        all_refs.extend(refs)
    else:
        print(
            "Error: No input. Provide NXML files or pipe via stdin.",
            file=sys.stderr,
        )
        return 1

    # Deduplicate across files preserving order
    unique_refs = list(dict.fromkeys(all_refs))
    for ref in unique_refs:
        print(ref)

    return 1 if had_error else 0
