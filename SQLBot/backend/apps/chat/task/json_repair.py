"""Tolerant repair of LLM-generated JSON used for chart configuration.

Chart answers are returned as a single JSON object whose ``summary`` field is a
Markdown string. The dominant failure mode is a *real* newline / tab inside that
string instead of its ``\\n`` / ``\\t`` escape, which breaks ``json.loads`` and —
on a partial repair — yields garbled front-end Markdown. This module is kept free
of heavy dependencies (no pandas / langchain) so it can be unit-tested in
isolation and reused by the chat task layer.
"""

from __future__ import annotations


def repair_json_string_literals(text: str) -> str:
    """Repair common model mistakes inside JSON without changing valid content.

    A single state-machine pass normalizes control characters *inside string
    literals only*, strips ``//`` comments and trailing commas *outside* strings,
    and leaves every other byte — including already-escaped sequences — untouched,
    so the ``summary`` reaching the front end matches what the model intended.
    """
    if not text:
        return text
    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if escaped:
                # Previous char was a backslash; keep this one verbatim (covers
                # \n \" \\ \/ etc.) and clear the escape flag.
                out.append(ch)
                escaped = False
                i += 1
                continue
            if ch == '\\':
                out.append(ch)
                escaped = True
                i += 1
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                i += 1
                continue
            if ch == '\n':
                out.append('\\n')
                i += 1
                continue
            if ch == '\r':
                # Collapse CRLF / lone CR to a single escaped newline.
                out.append('\\n')
                i += 2 if i + 1 < n and text[i + 1] == '\n' else 1
                continue
            if ch == '\t':
                out.append('\\t')
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # Outside a string literal.
        if ch == '"':
            out.append(ch)
            in_string = True
            i += 1
            continue
        if ch == '/' and i + 1 < n and text[i + 1] == '/':
            # // line comment outside a string: skip to end of line.
            while i < n and text[i] != '\n':
                i += 1
            continue
        if ch == ',':
            # Drop a trailing comma that precedes (whitespace then) } or ].
            j = i + 1
            while j < n and text[j] in ' \t\r\n':
                j += 1
            if j < n and text[j] in '}]':
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)
