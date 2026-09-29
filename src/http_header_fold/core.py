"""Normalize HTTP headers containing obs-fold continuation lines.

RFC 7230 deprecates the obsolete line folding (obs-fold) syntax where a header
field value can span multiple physical lines, each continuation line beginning
with at least one SP or HTAB. Despite the deprecation, real-world servers and
legacy proxies still emit folded headers, so a tolerant parser must flatten
them before passing the message to strict consumers.

This module treats any raw header block (bytes or str) as an opaque blob,
splits it on CRLF, and collapses continuation lines back into a single SP-
separated value per logical header. We intentionally preserve the original
casing of field names rather than forcing canonical title-case, because
section 3.2 of RFC 7230 makes field names case-insensitive and downstream
consumers that rely on exact casing are already broken in ways we should not
paper over.
"""

from __future__ import annotations

from typing import List, Tuple, Union, Iterator

__all__ = ["fold_headers", "unfold_header", "parse_headers"]

# Lines we recognise as continuation lines must start with SP or HTAB per RFC
# 7230 section 3.2. We do not treat a leading space on the very first line as
# a continuation because there is nothing to continue onto.
_CONTINUATION_PREFIXES = (" ", "\t")


def _to_text(raw: Union[str, bytes]) -> str:
    """Decode raw header input to str, assuming UTF-8 for bytes input.

    HTTP headers are technically ASCII (RFC 7230 section 3.2), but octets
    outside ASCII do occur in the wild. UTF-8 is a strict superset of ASCII
    and decodes every valid ASCII byte sequence identically, so it is the
    safe default. We use errors='replace' so a single bad byte cannot crash
    the whole parser — losing a character is better than losing all headers.
    """
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw


def _iter_logical_lines(text: str) -> Iterator[str]:
    """Yield logical header lines with obs-fold continuations already joined.

    RFC 7230 section 3.2 says a continuation line is one that begins with at
    least one SP or HTAB. We join such a line to its predecessor with a single
    space, collapsing whatever leading whitespace the continuation carried.
    This matches the recommendation that the folding whitespace be replaced
    by a single SP when unfolding.
    """
    buffer = ""
    has_buffer = False
    for line in text.splitlines():
        if line.startswith(_CONTINUATION_PREFIXES):
            if not has_buffer:
                # A continuation line with nothing before it is malformed.
                # Treat it as a standalone line so the caller can decide what
                # to do; we do not silently drop data.
                buffer = line.lstrip(" \t")
                has_buffer = True
            else:
                stripped = line.lstrip(" \t")
                if stripped:
                    buffer = buffer + " " + stripped
                # If the continuation is all whitespace we ignore it rather
                # than appending a trailing space, because a trailing space
                # on a header value is invisible noise that some strict
                # consumers reject.
        else:
            if has_buffer:
                yield buffer
            buffer = line
            has_buffer = True
    if has_buffer:
        yield buffer


def unfold_header(raw_header: Union[str, bytes]) -> str:
    """Flatten a single folded header field into one line.

    Given a string like ``"X-Foo: bar\r\n baz"`` return ``"X-Foo: bar baz"``.
    If the input is bytes it is decoded as UTF-8 with replacement for bad
    bytes (see _to_text). If the input contains no folding, it is returned
    verbatim apart from trailing whitespace on continuation lines.

    This function exists for callers who already know they have exactly one
    logical header and want the unfolded form without the key/value split
    that parse_headers performs.
    """
    text = _to_text(raw_header)
    parts = list(_iter_logical_lines(text))
    if not parts:
        return ""
    # A single logical header should produce exactly one joined line. If
    # the caller passed multiple blank-line-separated headers we only unfold
    # the folding within the first chunk; we do not merge unrelated headers.
    return parts[0]


def parse_headers(raw_headers: Union[str, bytes]) -> List[Tuple[str, str]]:
    """Parse a raw header block into a list of (name, value) pairs.

    Continuation lines (obs-fold) are joined to their preceding header with a
    single space. Blank lines terminate parsing — this mirrors the HTTP
    framing rule that a blank line separates the header block from the body.
    We return a list rather than a dict because duplicate header names are
    legal (e.g. multiple Set-Cookie or Via headers) and collapsing them would
    silently lose information.

    Header names are returned exactly as they appear in the input, preserving
    case. Header values have leading and trailing whitespace trimmed, which
    is safe because RFC 7230 section 3.2.4 says optional whitespace around the
    field-value is not part of the value.
    """
    text = _to_text(raw_headers)
    result: List[Tuple[str, str]] = []
    for line in _iter_logical_lines(text):
        if line == "":
            # Blank line: end of header block. Stop here so we do not try to
            # parse the body as headers.
            break
        # Find the colon that separates name from value. RFC 7230 section
        # 3.2 says the field-name is a token and contains no colon, so the
        # first colon is always the delimiter. We do not validate the token
        # grammar here because a tolerant parser should extract what it can.
        colon = line.find(":")
        if colon == -1:
            # No colon means this is not a valid header line. We skip it
            # rather than raising, because the caller may have passed a
            # partially-received buffer and dropping one garbled line is
            # less destructive than failing the whole parse.
            continue
        name = line[:colon]
        value = line[colon + 1:].strip()
        result.append((name, value))
    return result


def fold_headers(name: str, value: str, max_line_length: int = 78) -> str:
    """Produce an obs-fold representation of a single header.

    Given a name and value, emit a string where the value is broken across
    lines so that no line exceeds max_line_length characters. Each
    continuation line begins with a single space.

    We split on word boundaries (spaces in the value) to keep folded values
    readable. If a single word is longer than the available width it is
    placed on its own line without being broken — we do not hyphenate or
    mid-word split because that would corrupt opaque tokens.

    Note: obs-fold is deprecated by RFC 7230. This function is provided for
    completeness and for talking to legacy systems that expect folded input.
    Prefer single-line headers when the peer supports them.
    """
    if max_line_length < 1:
        raise ValueError("max_line_length must be positive")
    prefix = name + ": "
    words = value.split(" ")
    lines: List[str] = []
    current = prefix
    for word in words:
        if not current.endswith(prefix) and current != "":
            # If adding " word" would overflow, start a continuation line.
            if len(current) + 1 + len(word) > max_line_length and len(current) > len(prefix):
                lines.append(current)
                current = " " + word
                continue
            current = current + " " + word
        else:
            # First word on the line.
            if current == prefix:
                current = current + word
            else:
                current = current + word
    if current:
        lines.append(current)
    return "\r\n".join(lines)
