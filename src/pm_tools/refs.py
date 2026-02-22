"""pm refs: Extract cited PMIDs/DOIs from NXML (JATS) files."""

from __future__ import annotations

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
    for pub_id in root.iter("pub-id"):
        if pub_id.get("pub-id-type") == id_type:
            text = pub_id.text
            if text and text.strip():
                refs.append(text.strip())

    # Deduplicate preserving order
    return list(dict.fromkeys(refs))


HELP_TEXT = """\
pm refs - Extract cited PMIDs/DOIs from NXML files

Usage:
  pm refs [OPTIONS] FILE [FILE...]
  cat article.nxml | pm refs

Extracts cited identifiers from the JATS <ref-list> in NXML files.
Output is one identifier per line, suitable for piping to pm fetch.

Options:
  --doi            Extract DOIs instead of PMIDs
  -h, --help       Show this help message

Exit Codes:
  0 - Success (even if no refs found)
  1 - Error (file not found, invalid input)

Examples:
  pm refs article.nxml
  pm refs *.nxml | sort -u | pm fetch | pm parse
  pm refs --doi article.nxml
  pm refs ./articles/*.nxml"""


def main(args: list[str] | None = None) -> int:
    """CLI entry point for pm refs."""
    if args is None:
        args = sys.argv[1:]

    id_type = "pmid"
    files: list[str] = []

    for arg in args:
        if arg in ("--help", "-h"):
            print(HELP_TEXT)
            return 0
        elif arg == "--doi":
            id_type = "doi"
        elif arg.startswith("-"):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            return 1
        else:
            files.append(arg)

    # Collect all refs across files, deduplicated
    all_refs: list[str] = []

    if files:
        for filepath in files:
            try:
                with open(filepath) as f:
                    content = f.read()
            except OSError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1
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

    return 0
