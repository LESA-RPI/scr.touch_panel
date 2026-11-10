"""Display-only shell tokens; preserve reference text exactly and never execute it."""

from functools import lru_cache
import re

_WORDS = re.compile(
    r"""\n|[^\S\n]+|\#[^\n]*|"(?:\\.|[^"\\])*"|'[^']*'|&&|\|\||[|;<>]|[^\s|;&<>]+|."""
)


@lru_cache(maxsize=32)
def command_tokens(text):
    """Highlight the small shell-reference vocabulary without changing copy text."""
    result = []
    expect_command = True
    timeout_duration = False
    for match in _WORDS.finditer(text):
        word = match.group()
        kind = "text"
        if word == "\n":
            expect_command, timeout_duration = True, False
        elif word.isspace():
            pass
        elif word.startswith("#"):
            kind = "comment"
        elif word in ("&&", "||", "|", ";", "<", ">"):
            kind = "operator"
            expect_command = True
        elif word[0] in ('"', "'"):
            kind = "string"
            expect_command = False
        elif word.startswith("-"):
            kind = "option"
        elif timeout_duration and re.fullmatch(r"\d+(?:\.\d+)?[smhd]?", word):
            kind, timeout_duration = "number", False
        elif expect_command:
            kind = "command"
            expect_command = word in ("sudo", "timeout")
            timeout_duration = word == "timeout"
        elif word.startswith(("~", "/", "./", "../")) or word.endswith(
            (".py", ".bash", ".sh")
        ):
            kind = "path"
        elif re.fullmatch(r"\d+(?:\.\d+)?", word):
            kind = "number"
        result.append({"text": word, "kind": kind})
    return tuple(result)
