"""Notion-style templates: fill {{title}}, {{date}} and {{time}} (mirrors src/ct/ct_templates.cc)."""

from __future__ import annotations

import time
from typing import Mapping

from .content.editing import EditError, replace_text
from .page_content import NodeContent

Values = Mapping[str, str]


def default_values(title: str, now: float) -> dict[str, str]:
    local = time.localtime(now)
    return {"title": title, "date": time.strftime("%Y-%m-%d", local), "time": time.strftime("%H:%M", local)}


def _placeholder(key: str) -> str:
    return "{{" + key + "}}"


def fill(text: str, values: Values) -> str:
    """Replace the known {{key}} placeholders; unknown ones are left as they are."""
    for key, value in values.items():
        text = text.replace(_placeholder(key), value)
    return text


def fill_content(content: NodeContent, values: Values) -> NodeContent:
    """Fill placeholders in page content, keeping each placeholder's formatting for its value."""
    if isinstance(content, str):
        return fill(content, values)
    for key, value in values.items():
        try:
            content, _ = replace_text(content, _placeholder(key), value, replace_all=True)
        except EditError:  # placeholder not used on this page
            continue
    return content
