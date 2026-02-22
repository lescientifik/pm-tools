"""pm refs: Extract cited PMIDs/DOIs from NXML (JATS) files."""

from __future__ import annotations

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
