# HTTP Header Fold

Normalize HTTP headers that use the deprecated obs-fold continuation-line syntax into single-line key-value pairs.

```python
from http_header_fold import parse_headers, unfold_header, fold_headers

raw = "X-Trace: part-one\r\n part-two\r\n part-three"
pairs = parse_headers(raw)          # [('X-Trace', 'part-one part-two part-three')]
flat = unfold_header(raw)           # 'X-Trace: part-one part-two part-three'
folded = fold_headers("X-Trace", "part-one part-two part-three", max_line_length=30)
```

## Why this exists

RFC 7230 deprecated obs-fold (header values split across lines where each continuation begins with a space or tab), but legacy proxies and some servers still emit it. Strict parsers choke on folded headers, so the practical fix is to unfold them before passing the message body onward. This library does exactly that and nothing more: it reads a raw header block and returns a list of `(name, value)` pairs with continuations collapsed into a single space-separated value.

The deliberate trade-off is that header names are returned with their original casing rather than canonicalised to title-case. RFC 7230 says field names are case-insensitive, so forcing a casing would be a policy decision that belongs in the caller, not the parser.

## Edge you will hit

A blank line in the input terminates parsing, matching the HTTP framing rule that a blank line separates headers from the body. If you feed `parse_headers` a full HTTP message, the body is ignored — which is usually what you want, but will surprise you if you expected it to parse past the blank line.

`fold_headers` emits obs-fold output, which is deprecated. It exists for talking to legacy systems; prefer single-line headers for new code.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

