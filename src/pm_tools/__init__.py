"""PubMed CLI tools for AI agents."""

from pm_tools.parse import (
    LEGACY_FIELDS,
    article_to_csl,
    parse_xml_csl,
    parse_xml_stream_csl,
)
from pm_tools.types import AbstractSection, ArticleRecord, AuthorName, CslJsonRecord

__all__ = [
    "AbstractSection",
    "ArticleRecord",
    "AuthorName",
    "CslJsonRecord",
    "LEGACY_FIELDS",
    "article_to_csl",
    "parse_xml_csl",
    "parse_xml_stream_csl",
]
__version__ = "0.3.0"
