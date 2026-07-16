from __future__ import annotations

import html
import re
from collections.abc import Callable

from markdown_it import MarkdownIt

from worldbuilding_wiki.store import WIKI_LINK_RE

_renderer = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": False})


def render_markdown(
    body: str,
    resolve_link: Callable[[str], tuple[str, str] | None] | None = None,
) -> str:
    def replace(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        label = (match.group(2) or target).strip()
        resolved = resolve_link(target) if resolve_link else None
        if not resolved:
            return f"**[未解析：{_markdown_escape(label)}]**"
        url, title = resolved
        return f"[{_markdown_escape(label or title)}]({url})"

    prepared = WIKI_LINK_RE.sub(replace, body)
    return _renderer.render(prepared)


def _markdown_escape(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", html.escape(value, quote=False))
