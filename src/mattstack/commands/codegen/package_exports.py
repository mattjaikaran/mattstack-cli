"""Export generated names from a package `__init__.py` and its literal `__all__`."""

from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.plan import FilePlan

LINE_LIMIT = 88
NAME_LITERAL_RE = re.compile(r"""^(['"])([A-Za-z_]\w*)\1$""")
NON_CODE = frozenset({tokenize.COMMENT, tokenize.NL})


@dataclass(frozen=True)
class _AllLiteral:
    start: int  # offset of the line holding `__all__ =`
    close: int  # offset of the closing bracket
    names: tuple[str, ...]
    tuple_literal: bool
    standalone_close: bool  # only whitespace precedes the closing bracket on its line
    last_item_end: int | None  # offset just past the last string item
    last_item_comma: bool
    indent: str
    quote: str


def _offsets(text: str) -> list[int]:
    """Offset of each line start, indexed by tokenize's 1-based row."""
    return [0, 0, *(m.end() for m in re.finditer("\n", text))]


def _tokens(text: str, path: Path) -> list[tokenize.TokenInfo]:
    try:
        return list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError) as exc:
        raise GenerateError(f"Cannot read {path} to add exports: {exc}") from exc


def _dynamic(path: Path) -> GenerateError:
    return GenerateError(
        f"{path} builds __all__ dynamically; make it one literal list of strings "
        "or add the generated names to it by hand."
    )


def _parse_all(text: str, tokens: list[tokenize.TokenInfo], path: Path) -> _AllLiteral | None:
    """Locate the single top-level `__all__ = [...]` literal; None when absent."""
    mentions = [t for t in tokens if t.type == tokenize.NAME and t.string == "__all__"]
    if not mentions:
        return None
    target = mentions[0]
    if len(mentions) > 1 or target.start[1] != 0:
        raise _dynamic(path)
    code = [t for t in tokens[tokens.index(target) :] if t.type not in NON_CODE]
    index = 1
    if code[index].string == ":":  # annotated: `__all__: list[str] = [...]`
        while index < len(code) and code[index].string != "=":
            if code[index].type == tokenize.NEWLINE:
                raise _dynamic(path)
            index += 1
    if index + 1 >= len(code) or code[index].string != "=":
        raise _dynamic(path)
    opener = code[index + 1]
    if opener.string not in ("[", "("):
        raise _dynamic(path)
    closer = "]" if opener.string == "[" else ")"
    names: list[str] = []
    last: tokenize.TokenInfo | None = None
    comma = False
    position = index + 2
    while position < len(code) and code[position].string != closer:
        token = code[position]
        if token.type == tokenize.STRING and (last is None or comma):
            match = NAME_LITERAL_RE.match(token.string)
            if not match:
                raise _dynamic(path)
            names.append(match.group(2))
            last, comma = token, False
        elif token.string == "," and last is not None and not comma:
            comma = True
        else:
            raise _dynamic(path)
        position += 1
    if position + 1 >= len(code) or code[position + 1].type not in (
        tokenize.NEWLINE,
        tokenize.ENDMARKER,
    ):
        raise _dynamic(path)
    offsets = _offsets(text)
    close_row, close_col = code[position].start
    return _AllLiteral(
        start=offsets[target.start[0]],
        close=offsets[close_row] + close_col,
        names=tuple(names),
        tuple_literal=closer == ")",
        standalone_close=not text[offsets[close_row] : offsets[close_row] + close_col].strip(),
        last_item_end=offsets[last.end[0]] + last.end[1] if last else None,
        last_item_comma=comma,
        indent=" " * last.start[1] if last and last.start[0] != opener.start[0] else "    ",
        quote=last.string[0] if last else '"',
    )


def _quoted(names: list[str], quote: str) -> list[str]:
    return [f"{quote}{name}{quote}" for name in names]


def _extend_all(text: str, literal: _AllLiteral, names: list[str]) -> str:
    items = _quoted(names, literal.quote)
    if literal.standalone_close:
        line_start = text.rfind("\n", 0, literal.close) + 1
        block = "".join(f"{literal.indent}{item},\n" for item in items)
        text = text[:line_start] + block + text[line_start:]
        if literal.last_item_end is not None and not literal.last_item_comma:
            text = text[: literal.last_item_end] + "," + text[literal.last_item_end :]
        return text
    if literal.last_item_end is None:
        insert = ", ".join(items) + ("," if literal.tuple_literal and len(items) == 1 else "")
    else:
        insert = (" " if literal.last_item_comma else ", ") + ", ".join(items)
    return text[: literal.close] + insert + text[literal.close :]


def _render_all(names: list[str]) -> str:
    items = _quoted(names, '"')
    one_line = f"__all__ = [{', '.join(items)}]"
    if len(one_line) <= LINE_LIMIT:
        return one_line + "\n"
    return "__all__ = [\n" + "".join(f"    {item},\n" for item in items) + "]\n"


def _render_import(module: str, names: list[str]) -> str:
    one_line = f"from {module} import {', '.join(names)}"
    if len(one_line) <= LINE_LIMIT:
        return one_line + "\n"
    return f"from {module} import (\n" + "".join(f"    {name},\n" for name in names) + ")\n"


def _import_end(tokens: list[tokenize.TokenInfo], text: str, before: int) -> int | None:
    """Offset just past the last top-level import statement that starts before *before*."""
    offsets = _offsets(text)
    end: int | None = None
    in_import = False
    for token in tokens:
        offset = offsets[token.start[0]] + token.start[1]
        if offset >= before:
            break
        if token.type == tokenize.NAME and token.start[1] == 0:
            in_import = token.string in ("from", "import")
        elif token.type == tokenize.NEWLINE and in_import:
            end = offsets[token.end[0]] + token.end[1]
            in_import = False
    return end


def export_names(text: str, path: Path, module: str, names: list[str]) -> str:
    """Return *text* importing *names* from *module* and listing them in `__all__`.

    Existing imports, exports, and comments stay as they are; names already
    imported or exported are not added twice. A blank file gains `__all__`;
    a non-blank file without one keeps exporting everything it defines.
    Raises GenerateError when `__all__` is anything but one top-level literal
    list or tuple of strings.
    """
    wanted = list(dict.fromkeys(names))
    if not text.strip():
        return _render_import(module, wanted) + "\n" + _render_all(wanted)
    tokens = _tokens(text, path)
    literal = _parse_all(text, tokens, path)
    defined = {t.string for t in tokens if t.type == tokenize.NAME}
    missing = [name for name in wanted if name not in defined]
    block = _render_import(module, missing) if missing else ""
    if literal is None:
        return text + ("\n" if block and not text.endswith("\n") else "") + block
    # Edit back to front: `__all__` follows the import block, so offsets hold.
    new_exports = [name for name in wanted if name not in literal.names]
    if new_exports:
        text = _extend_all(text, literal, new_exports)
    if not block:
        return text
    end = _import_end(tokens, text, literal.start)
    if end is None:
        return text[: literal.start] + block + "\n" + text[literal.start :]
    return text[:end] + block + text[end:]


def plan_exports(plan: FilePlan, init_file: Path, module: str, names: list[str]) -> None:
    """Plan *init_file* so its package imports *names* from *module* and exports them.

    Raises GenerateError while planning, before anything is written, when the
    existing `__all__` cannot be extended safely.
    """
    current = plan.text(init_file)
    updated = export_names(current, init_file, module, names)
    if updated != current:
        plan.write(init_file, updated)
