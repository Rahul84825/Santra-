"""Natural Punctuation and Speech-to-Text Formatting Engine."""

import re
from typing import Optional


class PunctuationFormatter:
    """Transforms spoken punctuation phrases into natural typography and whitespace."""

    # Explicit multi-word patterns mapped to punctuation
    MULTI_WORD_REPLACEMENTS = [
        (r"\b(?:new\s+paragraph|next\s+paragraph)\b", "\n\n"),
        (r"\b(?:new\s+line|newline|next\s+line)\b", "\n"),
        (r"\b(?:question\s+mark)\b", "?"),
        (r"\b(?:exclamation\s+mark|exclamation\s+point)\b", "!"),
        (r"\b(?:full\s+stop)\b", "."),
        (r"\b(?:dot\s+dot\s+dot|ellipsis)\b", "..."),
        (r"\b(?:semi\s+colon|semicolon)\b", ";"),
        (r"\b(?:open\s+parenthesis|open\s+paren|left\s+parenthesis|left\s+paren)\b", "("),
        (r"\b(?:close\s+parenthesis|close\s+paren|right\s+parenthesis|right\s+paren)\b", ")"),
        (r"\b(?:open\s+bracket|left\s+bracket)\b", "["),
        (r"\b(?:close\s+bracket|right\s+bracket)\b", "]"),
        (r"\b(?:open\s+brace|open\s+curly\s+brace|left\s+brace)\b", "{"),
        (r"\b(?:close\s+brace|close\s+curly\s+brace|right\s+brace)\b", "}"),
        (r"\b(?:open\s+quote|begin\s+quote)\b", '"'),
        (r"\b(?:close\s+quote|end\s+quote|unquote)\b", '"'),
        (r"\b(?:at\s+sign)\b", "@"),
        (r"\b(?:hash\s+tag|hash\s+sign|pound\s+sign)\b", "#"),
        (r"\b(?:dollar\s+sign)\b", "$"),
        (r"\b(?:percent\s+sign)\b", "%"),
        (r"\b(?:forward\s*slash)\b", "/"),
        (r"\b(?:back\s*slash|backslash)\b", r"\\"),
        (r"\b([a-zA-Z])\s+colon\b", r"\1:"),
    ]

    # Single-word replacements
    SINGLE_WORD_MAP = {
        "comma": ",",
        "period": ".",
        "colon": ":",
        "hyphen": "-",
        "dash": "-",
        "underscore": "_",
        "ampersand": "&",
        "asterisk": "*",
        "tab": "\t",
        "slash": "/",
        "equals": "=",
        "equal": "=",
    }

    def format_text(self, text: str, capitalize_first: bool = True) -> str:
        """Formats spoken text into typed prose with proper punctuation and spacing."""
        if not text:
            return ""

        res = text.strip()

        # 1. Multi-word punctuation replacements
        for pat, repl in self.MULTI_WORD_REPLACEMENTS:
            res = re.sub(pat, repl, res, flags=re.IGNORECASE)

        # 2. Single-word punctuation replacements (word boundary guarded, preserves newlines)
        for word, sym in self.SINGLE_WORD_MAP.items():
            res = re.sub(r"\b" + word + r"\b", sym, res, flags=re.IGNORECASE)

        # 2B. Spoken technical symbols & contextual tokens
        # Drive letters & file paths: "C colon backslash" -> "C:\"
        res = re.sub(r"\b([a-zA-Z])\s*:\s*\\", lambda m: m.group(1).upper() + r":\\", res)
        res = re.sub(r"(?<=[a-zA-Z0-9_])\s+(?:back\s*slash|backslash)\s+(?=[a-zA-Z0-9_])", r"\\", res, flags=re.IGNORECASE)
        # URLs: "https : / /" -> "https://"
        res = re.sub(r"\b(https?)\s*:\s*/\s*/\s*", r"\1://", res, flags=re.IGNORECASE)
        res = re.sub(r"(?<=[a-zA-Z0-9_])\s+(?:forward\s*slash|slash)\s+(?=[a-zA-Z0-9_])", "/", res, flags=re.IGNORECASE)
        # Web extensions and code extensions with dot
        res = re.sub(r"\b([a-zA-Z0-9_-]+)\s+dot\s+(to|com|org|net|io|co|in|edu|gov|py|js|ts|json|html|css|md|txt|exe|dll|csv)\b", r"\1.\2", res, flags=re.IGNORECASE)
        res = re.sub(r"\b(?:dot\s+(to|com|org|net|io|co|in|edu|gov|py|js|ts|json|html|css|md|txt|exe|dll|csv))\b", r".\1", res, flags=re.IGNORECASE)
        # Spoken "dot" between identifiers: "hianime dot to" -> "hianime.to"
        res = re.sub(r"(?<=[a-zA-Z0-9_])\s+dot\s+(?=[a-zA-Z0-9_])", ".", res, flags=re.IGNORECASE)
        # Spoken "point" in decimal numbers: "10 point 5" -> "10.5"
        res = re.sub(r"(\d+)\s+point\s+(\d+)", r"\1.\2", res, flags=re.IGNORECASE)

        # 2C. In-line spoken self-correction: "X no wait, change that to Y" -> "Y"
        res = re.sub(r"(\b\w+)\s+(?:no\s+wait|scratch\s+that|wait\s+no)[,\s]+(?:change\s+that\s+to\s+|make\s+that\s+to\s+|make\s+it\s+to\s+|make\s+it\s+)?(\b\w+[.?!]?)", r"\2", res, flags=re.IGNORECASE)
        res = re.sub(r"^.+?\s+(?:no\s+wait|scratch\s+that|wait\s+no)[,\s]+(?:change\s+that\s+to\s+|make\s+that\s+to\s+|make\s+it\s+to\s+|make\s+it\s+)?(.+)$", r"\1", res, flags=re.IGNORECASE)

        # 3. Clean up spacing before punctuation marks:
        # "hello , world" -> "hello, world"
        res = re.sub(r"[ \t]+([,.:;?!])", r"\1", res)
        # Ensure space after punctuation if followed by a letter/digit,
        # but avoid breaking decimals, thousands, URLs, file paths, and extensions:
        def _spacing_after_punct(m: re.Match) -> str:
            p = m.group(1)
            f = m.group(2)
            # Decimals or versions: 10.5, v2.1
            if p == "." and f.isdigit():
                return p + f
            # Thousands: 1,000
            if p == "," and f.isdigit():
                return p + f
            # Colons in URLs or Windows paths: https:// or C:\
            if p == ":" and (f in ["/", "\\"] or m.string[max(0, m.start()-5):m.start()].lower() in ["http", "https"]):
                return p + f
            return f"{p} {f}"

        res = re.sub(r"([,.:;?!])([a-zA-Z0-9/\\_])", _spacing_after_punct, res)

        # 3B. Precision restoration for technical tokens:
        # Restore URLs
        res = re.sub(r"\b(https?)\s*:\s*/\s*/\s*", r"\1://", res, flags=re.IGNORECASE)
        # Strip spaces inside URL components
        res = re.sub(r"\b(https?://[^\s]+?)\s*\.\s*(to|com|org|net|io|co|in|edu|gov|html|php)\b", r"\1.\2", res, flags=re.IGNORECASE)
        res = re.sub(r"(https?://[^\s?#]+?)\s*/\s*([^\s?#]+)", r"\1/\2", res)
        # Clean URL query strings: e.g. "https://hianime.to/user/watching ? filter = all & sort = updated"
        res = re.sub(r"(https?://[^\s?#]+)\s*\?\s*([a-zA-Z0-9_=& \t-]+)", lambda m: m.group(1).lower() + "?" + re.sub(r"\s*([&=])\s*", r"\1", m.group(2)).lower(), res)

        # Restore drive letters: "C: \ " or "C: \\ " -> "C:\"
        res = re.sub(r"\b([a-zA-Z])\s*:\s*\\+\s*", lambda m: m.group(1).upper() + r":\\", res)
        # Strip spaces around backslashes in paths: "Users \ activ \ Desktop" -> "Users\activ\Desktop"
        res = re.sub(r"\s*\\+\s*", r"\\", res)
        # Strip spaces around forward slashes in URLs/paths: "user / watching" -> "user/watching"
        res = re.sub(r"(?<=\S)\s*/\s*(?=\S)", "/", res)
        # Collapse file extensions with dot: "config . json" -> "config.json"
        res = re.sub(r"([a-zA-Z0-9_]+)\s*\.\s*(json|py|js|ts|html|css|txt|md|csv|exe|dll)\b", r"\1.\2", res, flags=re.IGNORECASE)
        # Restore thousands formatting: "1 , 000 , 000" -> "1,000,000"
        res = re.sub(r"(\d+(?:\s*,\s*\d{3})+)", lambda m: re.sub(r"\s+", "", m.group(1)), res)
        # Restore version strings: "v 2 . 1 . 0" or "v2. 1. 0" -> "v2.1.0"
        res = re.sub(r"\bv\s*(\d+(?:\s*\.\s*\d+)+)", lambda m: "v" + re.sub(r"\s+", "", m.group(1)), res, flags=re.IGNORECASE)
        # Restore decimals: "10 . 5" -> "10.5"
        res = re.sub(r"(\d+)\s*\.\s*(\d+)", r"\1.\2", res)
        # Restore technical units: "10.5 ms" -> "10.5ms"
        res = re.sub(r"(\d+(?:\.\d+)?)\s*(ms|s|mb|gb|kb|fps|px|ghz|mhz|hz)\b", r"\1\2", res, flags=re.IGNORECASE)

        # 4. Spacing around brackets and quotes:
        # "( hello )" -> "(hello)"
        res = re.sub(r"\(\s+", "(", res)
        res = re.sub(r"\s+\)", ")", res)
        res = re.sub(r"\[\s+", "[", res)
        res = re.sub(r"\s+\]", "]", res)
        res = re.sub(r"\{\s+", "{", res)
        res = re.sub(r"\s+\}", "}", res)
        # Strip whitespace inside double quotes: '" welcome "' -> '"welcome"'
        res = re.sub(r'"\s*([^"]*?)\s*"', r'"\1"', res)

        # 5. Spacing around newlines:
        res = re.sub(r"[ \t]*\n[ \t]*", "\n", res)
        res = re.sub(r"\n{3,}", "\n\n", res)

        # 6. Sentence capitalization:
        if capitalize_first and res:
            # Capitalize first character
            res = res[0].upper() + res[1:] if len(res) > 1 else res.upper()

            # Capitalize after sentence-ending punctuation (. ? !) and newlines
            def _cap_repl(m: re.Match) -> str:
                return m.group(1) + m.group(2).upper()

            res = re.sub(r"([!?\n]\s*|\.\s+)([a-z])", _cap_repl, res)

        # 7. Final URL and query string normalization (post-capitalization cleanup)
        def _clean_url_query_final(m: re.Match) -> str:
            url_part = m.group(1).lower()
            query_part = m.group(2)
            clean_q = re.sub(r"\s*([&=])\s*", r"\1", query_part)
            clean_q = re.sub(r"\s+", "", clean_q)
            return f"{url_part}?{clean_q}".lower()

        res = re.sub(r"(https?://[^\s?#]+)\s*\?\s*([a-zA-Z0-9_=& \t-]+)", _clean_url_query_final, res, flags=re.IGNORECASE)
        res = re.sub(r"\bhttps?://[^\s]+", lambda m: m.group(0).lower(), res, flags=re.IGNORECASE)

        return res


punctuation_formatter = PunctuationFormatter()
