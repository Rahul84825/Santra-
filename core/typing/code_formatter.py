"""Code Dictation Formatter for Universal Voice Typing Engine."""

import re
from typing import Optional


class CodeFormatter:
    """Formats spoken programming instructions into structured code."""

    DELIMITER_LOOKAHEAD = r"(?=\s+(?:open|close|left|right|equals|is|gets|plus|minus|times|divide|comma|colon|semicolon|dot|arrow|fat\s+arrow|thin\s+arrow|new\s+line|newline|tab|indent|returns|\(|\)|\[|\]|\{|\}|:|,|;|=|<|>|\+|-|\*|/|$)|$)"

    CASING_PREFIXES = [
        (r"\b(?:camel\s+case|camelcase)\s+([a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+)*?)" + DELIMITER_LOOKAHEAD, "camel"),
        (r"\b(?:snake\s+case|snakecase)\s+([a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+)*?)" + DELIMITER_LOOKAHEAD, "snake"),
        (r"\b(?:kebab\s+case|kebabcase)\s+([a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+)*?)" + DELIMITER_LOOKAHEAD, "kebab"),
        (r"\b(?:pascal\s+case|pascalcase)\s+([a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+)*?)" + DELIMITER_LOOKAHEAD, "pascal"),
        (r"\b(?:constant\s+case|constant|screaming\s+snake|upper\s+snake)\s+([a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+)*?)" + DELIMITER_LOOKAHEAD, "screaming_snake"),
    ]

    OPERATOR_MAP = [
        (r"\b(?:double\s+equals|equals\s+equals|is\s+equal\s+to)\b", " == "),
        (r"\b(?:not\s+equal\s+to|not\s+equals|exclamation\s+equals)\b", " != "),
        (r"\b(?:greater\s+than\s+or\s+equal\s+to)\b", " >= "),
        (r"\b(?:less\s+than\s+or\s+equal\s+to)\b", " <= "),
        (r"\b(?:plus\s+equals)\b", " += "),
        (r"\b(?:minus\s+equals)\b", " -= "),
        (r"\b(?:times\s+equals|multiply\s+equals)\b", " *= "),
        (r"\b(?:divide\s+equals)\b", " /= "),
        (r"\b(?:fat\s+arrow|arrow\s+function)\b", " => "),
        (r"\b(?:thin\s+arrow|skinny\s+arrow|returns\s+type|arrow)\b", " -> "),
        (r"\b(?:logical\s+and|and\s+and)\b", " && "),
        (r"\b(?:logical\s+or|or\s+or)\b", " || "),
        (r"\b(?:greater\s+than)\b", " > "),
        (r"\b(?:less\s+than)\b", " < "),
        (r"\b(?:equals|is\s+assigned\s+to|gets)\b", " = "),
        (r"\b(?:plus)\b", " + "),
        (r"\b(?:minus)\b", " - "),
        (r"\b(?:times|multiplied\s+by)\b", " * "),
        (r"\b(?:divided\s+by)\b", " / "),
        (r"\b(?:modulo|mod)\b", " % "),
    ]

    STRUCTURE_MAP = [
        (r"\b(?:new\s+line|newline)\b\s*\b(?:indent|tab|four\s+spaces)\b\s*", "\n    "),
        (r"\b(?:open\s+parenthesis|open\s+paren|left\s+paren)\b", "("),
        (r"\b(?:close\s+parenthesis|close\s+paren|right\s+paren)\b", ")"),
        (r"\b(?:open\s+bracket|left\s+bracket)\b", "["),
        (r"\b(?:close\s+bracket|right\s+bracket)\b", "]"),
        (r"\b(?:open\s+curly|open\s+curly\s+brace|open\s+brace)\b", "{\n"),
        (r"\b(?:close\s+curly|close\s+curly\s+brace|close\s+brace)\b", "\n}"),
        (r"\b(?:comma)\b", ","),
        (r"\b(?:colon)\b", ":"),
        (r"\b(?:semicolon)\b", ";"),
        (r"\b(?:dot)\b", "."),
        (r"\b(?:open\s+quote|begin\s+quote|double\s+quote)\b", '"'),
        (r"\b(?:close\s+quote|end\s+quote|unquote)\b", '"'),
        (r"\b(?:single\s+quote)\b", "'"),
        (r"\b(?:indent|four\s+spaces|tab)\b\s*", "    "),
        (r"\b(?:new\s+line|newline)\b\s*", "\n"),
    ]

    KEYWORD_MAP = {
        "def": "def ",
        "function": "function ",
        "class": "class ",
        "return": "return ",
        "import": "import ",
        "from": "from ",
        "if": "if ",
        "else": "else",
        "elif": "elif ",
        "for": "for ",
        "while": "while ",
        "try": "try:\n",
        "except": "except ",
        "finally": "finally:\n",
        "const": "const ",
        "let": "let ",
        "var": "var ",
        "async": "async ",
        "await": "await ",
        "lambda": "lambda ",
        "none": "None",
        "null": "null",
        "true": "True",
        "false": "False",
    }

    def _convert_casing(self, phrase: str, style: str) -> str:
        words = re.findall(r"[a-zA-Z0-9]+", phrase)
        if not words:
            return phrase

        if style == "camel":
            return words[0].lower() + "".join(w.capitalize() for w in words[1:])
        elif style == "snake":
            return "_".join(w.lower() for w in words)
        elif style == "kebab":
            return "-".join(w.lower() for w in words)
        elif style == "pascal":
            return "".join(w.capitalize() for w in words)
        elif style == "screaming_snake":
            return "_".join(w.upper() for w in words)
        return phrase

    def format_code(self, speech_text: str, language: str = "python") -> str:
        """Translates spoken programming syntax into executable code text."""
        if not speech_text:
            return ""

        res = speech_text.strip()

        # 1. Transform explicit casing directives first
        for pat, style in self.CASING_PREFIXES:
            def _casing_repl(m: re.Match) -> str:
                return self._convert_casing(m.group(1), style)
            res = re.sub(pat, _casing_repl, res, flags=re.IGNORECASE)

        # 2. Structure & brackets
        for pat, repl in self.STRUCTURE_MAP:
            res = re.sub(pat, repl, res, flags=re.IGNORECASE)

        # 3. Operators
        for pat, repl in self.OPERATOR_MAP:
            res = re.sub(pat, repl, res, flags=re.IGNORECASE)

        # 4. Keyword formatting (word-boundary matched without destroying indentation)
        for kw, repl in self.KEYWORD_MAP.items():
            val = repl.strip()
            if language in ["javascript", "typescript", "js", "ts"]:
                if val == "None":
                    val = "null"
                elif val == "True":
                    val = "true"
                elif val == "False":
                    val = "false"
            res = re.sub(r"\b" + kw + r"\b", val, res, flags=re.IGNORECASE)

        # 5. Clean up code whitespace
        # No space before opening paren or bracket if after identifier: "my_func (" -> "my_func("
        res = re.sub(r"([a-zA-Z0-9_])\s+\(", r"\1(", res)
        res = re.sub(r"([a-zA-Z0-9_])\s+\[", r"\1[", res)
        # No space after opening paren: "( self" -> "(self"
        res = re.sub(r"\(\s+", "(", res)
        # No space before closing paren: "b )" -> "b)"
        res = re.sub(r"\s+\)", ")", res)
        # Clean up spaces around dots: "obj . prop" -> "obj.prop"
        res = re.sub(r"\s*\.\s*", ".", res)
        # Clean up spaces before commas, colons, and semicolons
        res = re.sub(r"\s+([,;:!?)])", r"\1", res)
        # Ensure space after comma if followed by non-space
        res = re.sub(r",([^\s])", r", \1", res)
        # Strip whitespace inside quotes
        res = re.sub(r'"\s*([^"]*?)\s*"', r'"\1"', res)
        res = re.sub(r"'\s*([^']*?)\s*'", r"'\1'", res)
        # Clean up multiple spaces per line while strictly preserving leading indentation
        lines = res.split("\n")
        cleaned_lines = []
        for line in lines:
            leading = len(line) - len(line.lstrip(" "))
            indent = " " * leading
            rest = re.sub(r"[ \t]+", " ", line.strip())
            cleaned_lines.append(f"{indent}{rest}" if rest else "")
        res = "\n".join(cleaned_lines)

        return res.rstrip()


code_formatter = CodeFormatter()
