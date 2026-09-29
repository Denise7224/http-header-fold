import unittest

from http_header_fold.core import fold_headers, unfold_header, parse_headers


class TestParseHeaders(unittest.TestCase):

    def test_single_header_no_folding(self):
        result = parse_headers("Host: example.test")
        self.assertEqual(result, [("Host", "example.test")])

    def test_multiple_headers(self):
        raw = "Host: example.test\r\nContent-Length: 0"
        self.assertEqual(
            parse_headers(raw),
            [("Host", "example.test"), ("Content-Length", "0")],
        )

    def test_obs_fold_space_continuation(self):
        raw = "X-Long: part one\r\n part two"
        self.assertEqual(parse_headers(raw), [("X-Long", "part one part two")])

    def test_obs_fold_tab_continuation(self):
        raw = "X-Long: part one\r\n\tpart two"
        self.assertEqual(parse_headers(raw), [("X-Long", "part one part two")])

    def test_obs_fold_multiple_continuations(self):
        raw = "X-Long: a\r\n b\r\n c\r\n d"
        self.assertEqual(parse_headers(raw), [("X-Long", "a b c d")])

    def test_obs_fold_leading_whitespace_collapsed(self):
        # Multiple spaces and tabs at the start of a continuation line should
        # be collapsed into the single joining space.
        raw = "X-Long: a\r\n  \t  b"
        self.assertEqual(parse_headers(raw), [("X-Long", "a b")])

    def test_blank_line_stops_parsing(self):
        raw = "Host: example.test\r\n\r\nBody-Like: ignored"
        self.assertEqual(parse_headers(raw), [("Host", "example.test")])

    def test_duplicate_header_names_preserved(self):
        raw = "Set-Cookie: a=1\r\nSet-Cookie: b=2"
        self.assertEqual(
            parse_headers(raw),
            [("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")],
        )

    def test_value_whitespace_trimmed(self):
        raw = "X-Pad:   spaced value   "
        self.assertEqual(parse_headers(raw), [("X-Pad", "spaced value")])

    def test_line_without_colon_skipped(self):
        raw = "Host: example.test\r\ngarbage-line\r\nAccept: text/plain"
        self.assertEqual(
            parse_headers(raw),
            [("Host", "example.test"), ("Accept", "text/plain")],
        )

    def test_bytes_input_decoded(self):
        raw = b"Host: example.test\r\nX-Long: a\r\n b"
        self.assertEqual(
            parse_headers(raw),
            [("Host", "example.test"), ("X-Long", "a b")],
        )

    def test_empty_input(self):
        self.assertEqual(parse_headers(""), [])

    def test_case_preserved(self):
        raw = "CONTENT-TYPE: text/plain"
        self.assertEqual(parse_headers(raw), [("CONTENT-TYPE", "text/plain")])


class TestUnfoldHeader(unittest.TestCase):

    def test_unfold_single_field(self):
        self.assertEqual(unfold_header("X-Foo: bar\r\n baz"), "X-Foo: bar baz")

    def test_unfold_no_folding(self):
        self.assertEqual(unfold_header("X-Foo: bar"), "X-Foo: bar")

    def test_unfold_bytes(self):
        self.assertEqual(unfold_header(b"X-Foo: bar\r\n baz"), "X-Foo: bar baz")

    def test_unfold_empty(self):
        self.assertEqual(unfold_header(""), "")


class TestFoldHeaders(unittest.TestCase):

    def test_short_value_single_line(self):
        result = fold_headers("X-Short", "hi")
        self.assertEqual(result, "X-Short: hi")

    def test_long_value_wraps(self):
        value = "word " * 20
        result = fold_headers("X-Long", value.strip(), max_line_length=30)
        lines = result.split("\r\n")
        # Every line except possibly the last must be within the limit.
        for line in lines[:-1]:
            self.assertLessEqual(len(line), 30)
        # The reconstructed value must equal the original.
        unfolded = " ".join(line.lstrip(" ") for line in lines)
        self.assertEqual(unfolded, "X-Long: " + value.strip())

    def test_long_word_on_own_line(self):
        # A single word longer than the limit goes on its own line unbroken.
        long_word = "a" * 100
        result = fold_headers("X", long_word, max_line_length=20)
        lines = result.split("\r\n")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "X: " + long_word)

    def test_invalid_max_line_length(self):
        with self.assertRaises(ValueError):
            fold_headers("X", "y", max_line_length=0)


if __name__ == "__main__":
    unittest.main()
