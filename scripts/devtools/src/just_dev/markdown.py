"""A deliberately small, deterministic Markdown-to-Confluence-storage renderer."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_UNORDERED = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^\s)]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_EMPHASIS = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _safe_href(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        return url
    return None


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)

    def link(match: re.Match[str]) -> str:
        href = _safe_href(html.unescape(match.group(2)))
        text_value = match.group(1)
        if href is None:
            return text_value
        return f'<a href="{html.escape(href, quote=True)}">{text_value}</a>'

    escaped = _LINK.sub(link, escaped)
    escaped = _CODE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    return _EMPHASIS.sub(r"<em>\1</em>", escaped)


def markdown_to_storage(markdown: str) -> str:
    """Render only a safe subset; all raw HTML is escaped rather than passed through."""

    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_type: str | None = None
    code_lines: list[str] | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items, list_type
        if list_type and list_items:
            blocks.append(
                f"<{list_type}>" + "".join(f"<li>{_inline(item)}</li>" for item in list_items) + f"</{list_type}>"
            )
        list_items = []
        list_type = None

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines is not None:
            content = "\n".join(code_lines).replace("]]>", "]]&gt;")
            blocks.append(
                '<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA['
                + content
                + "]]></ac:plain-text-body></ac:structured-macro>"
            )
            code_lines = None

    for line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.strip().startswith("```"):
            if code_lines is None:
                flush_paragraph()
                flush_list()
                code_lines = []
            else:
                flush_code()
            continue
        if code_lines is not None:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue
        unordered = _UNORDERED.match(line)
        ordered = _ORDERED.match(line)
        list_match = unordered or ordered
        if list_match:
            flush_paragraph()
            next_type = "ul" if unordered else "ol"
            if list_type and list_type != next_type:
                flush_list()
            list_type = next_type
            list_items.append(list_match.group(1))
            continue
        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    flush_code()
    return "\n".join(blocks)
