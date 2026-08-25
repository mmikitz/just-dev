from __future__ import annotations

from just_dev.markdown import markdown_to_storage


def test_markdown_renderer_escapes_raw_html_and_keeps_safe_constructs() -> None:
    rendered = markdown_to_storage("# Heading\n\n<script>alert(1)</script> **bold** [safe](https://example.test)\n\n- one\n- two")

    assert "<h1>Heading</h1>" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<strong>bold</strong>" in rendered
    assert '<a href="https://example.test">safe</a>' in rendered
    assert "<ul><li>one</li><li>two</li></ul>" in rendered


def test_markdown_renderer_rejects_unsafe_link_scheme() -> None:
    rendered = markdown_to_storage("[nope](javascript:alert(1))")
    assert "javascript:" not in rendered
    assert "href=" not in rendered
