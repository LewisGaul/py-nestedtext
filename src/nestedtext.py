# encoding: utf8

# Copyright (c) 2020 Kenneth S. Kundert and Kale Kundert
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


"""
NestedText: A Human Readable and Writable Data Format
"""

__version__ = "0.0.1"

__all__ = (
    "load",
    "loads",
    "dump",
    "dumps",
    "DuplicateFieldBehaviour",
    "NestedtextError",
    "NestedtextType",
)

import collections
import enum
import os
import re
import textwrap
from typing import Dict, Iterable, List, NoReturn, Optional, Tuple, Union


NestedtextType = Union[str, List["NestedtextType"], Dict[str, "NestedTextType"]]


class NestedtextError(Exception):
    def __init__(
        self, message: str, lineno: Optional[int] = None, colno: Optional[int] = None
    ):
        if lineno is not None:
            message += f": {lineno}"
            if colno is not None:
                message += f":{colno}"
        super().__init__(message)
        self.lineno = lineno
        self.colno = colno


def _report(message, line, *args, colno=None, **kwargs) -> NoReturn:
    raise NestedtextError(message, line.lineno, colno)


def _indentation_error(line, depth) -> NoReturn:
    _report("invalid indentation", line, colno=depth)


# ------------------------------------------------------------------------------
# Parsing logic
# ------------------------------------------------------------------------------


class DuplicateFieldBehaviour(str, enum.Enum):
    USE_FIRST = "use_first"
    USE_LAST = "use_last"
    ERROR = "error"

    def __repr__(self):
        return str(self)


class _LineType(enum.Enum):
    BLANK = enum.auto()
    COMMENT = enum.auto()
    STRING = enum.auto()
    LIST_ITEM = enum.auto()
    OBJECT_ITEM = enum.auto()
    OBJECT_KEY = enum.auto()

    def __repr__(self):
        return str(self)

    def is_ignorable(self) -> bool:
        return self in [self.BLANK, self.COMMENT]


class _Line(collections.namedtuple("_Line", "text, lineno, kind, depth, value")):
    def __new__(
        cls,
        text: str,
        lineno: int,
        kind: _LineType,
        depth: int,
        value: Union[None, str, Tuple[str, Optional[str]]],
    ):
        return super().__new__(cls, text, lineno, kind, depth, value)


class _InvalidLineType(enum.Enum):
    NON_SPACE_INDENT = enum.auto()
    UNRECOGNISED = enum.auto()

    def __repr__(self):
        return str(self)


class _InvalidLine(collections.namedtuple("_InvalidLine", "text, lineno, kind, colno")):
    def __new__(
        cls,
        text: str,
        lineno: int,
        kind: _InvalidLineType,
        colno: int,
    ):
        return super().__new__(cls, text, lineno, kind, colno)


class _LinesIter(Iterable[_Line]):
    def __init__(self, lines: Iterable[str]):
        self._generator = self._read_lines(lines)
        self._next_line: Optional[_Line] = self._advance_to_next_content_line()

    def __iter__(self):
        return self

    def __next__(self) -> _Line:
        if self._next_line is None:
            raise StopIteration

        this_line = self._next_line
        self._next_line = self._advance_to_next_content_line()
        return this_line

    def _read_lines(self, lines: Iterable[str]):
        for idx, line in enumerate(lines):
            if not line.strip():
                yield _Line(line, idx + 1, _LineType.BLANK, 0, None)
                continue

            text = line.rstrip("\r\n")

            # Comments can have any leading whitespace.
            if text.lstrip()[0] == "#":
                yield _Line(line, idx + 1, _LineType.COMMENT, 0, text.lstrip()[1:])
                continue

            stripped = text.lstrip(" ")
            depth = len(text) - len(stripped)

            # Otherwise check leading whitespace consists only of spaces.
            if len(stripped.lstrip()) < len(stripped):
                yield _InvalidLine(
                    line, idx + 1, _InvalidLineType.NON_SPACE_INDENT, depth
                )
                continue

            # Now handle normal content lines!
            if stripped == "-" or stripped.startswith("- "):
                kind = _LineType.LIST_ITEM
                value = stripped[2:] or None
            elif stripped == ">" or stripped.startswith("> "):
                kind = _LineType.STRING
                # Include end-of-line characters.
                value = re.sub(r"> ?", "", line.lstrip(" "), count=1)
            elif stripped == ":" or stripped.startswith(": "):
                kind = _LineType.OBJECT_KEY
                # Include end-of-line characters.
                value = re.sub(r": ?", "", line.lstrip(" "), count=1)
            else:
                match = re.fullmatch(r"(?P<key>.+?)\s*:(?: (?P<value>.*))?", stripped)
                if match:
                    kind = _LineType.OBJECT_ITEM
                    value = tuple(match.groups())
                else:
                    yield _InvalidLine(
                        line, idx + 1, _InvalidLineType.UNRECOGNISED, depth
                    )
                    continue

            yield _Line(line, idx + 1, kind, depth, value)

    def _advance_to_next_content_line(self) -> Optional[_Line]:
        """Advance the generator the next useful line and return it."""
        while True:
            next_line = next(self._generator, None)
            if isinstance(next_line, _InvalidLine):
                _report("invalid line", next_line, colno=next_line.colno)
            if next_line is None or not next_line.kind.is_ignorable():
                break
        return next_line

    def peek_next(self) -> Optional[_Line]:
        return self._next_line


def _read_value(
    lines: _LinesIter, depth: int, on_dup: DuplicateFieldBehaviour
) -> Union[str, List, Dict]:
    if lines.peek_next().kind is _LineType.LIST_ITEM:
        return _read_list(lines, depth, on_dup)
    if lines.peek_next().kind in [_LineType.OBJECT_ITEM, _LineType.OBJECT_KEY]:
        return _read_object(lines, depth, on_dup)
    if lines.peek_next().kind is _LineType.STRING:
        return _read_string(lines, depth)
    _report("unrecognized line", next(lines))


def _read_list(
    lines: _LinesIter, depth: int, on_dup: DuplicateFieldBehaviour
) -> List[NestedtextType]:
    data = []
    while lines.peek_next() and lines.peek_next().depth >= depth:
        line = next(lines)
        if line.depth != depth:
            _indentation_error(line, depth)
        if line.kind is not _LineType.LIST_ITEM:
            _report("expected list item", line, colno=depth)
        if line.value:
            data.append(line.value)
        else:
            # Value may simply be empty, or it may be on next line, in which
            # case it must be indented.
            if lines.peek_next() is None:
                value = ""
            else:
                depth_of_next = lines.peek_next().depth
                if depth_of_next > depth:
                    value = _read_value(lines, depth_of_next, on_dup)
                else:
                    value = ""
            data.append(value)
    return data


def _read_object(
    lines: _LinesIter, depth: int, on_dup: DuplicateFieldBehaviour
) -> Dict[str, NestedtextType]:
    data = {}
    while lines.peek_next() and lines.peek_next().depth >= depth:
        line = lines.peek_next()
        if line.depth != depth:
            _indentation_error(line, depth)
        if line.kind is _LineType.OBJECT_ITEM:
            next(lines)  # Advance the iterator
            key, value = line.value
        elif line.kind is _LineType.OBJECT_KEY:
            key = _read_object_key(lines, depth)
            value = None
        else:
            _report("expected object item", line, colno=depth)
        if not value:
            if lines.peek_next() is None:
                if line.kind is _LineType.OBJECT_KEY:
                    raise NestedtextError("expected value after multiline object key")
                value = ""
            else:
                depth_of_next = lines.peek_next().depth
                if depth_of_next > depth:
                    value = _read_value(lines, depth_of_next, on_dup)
                elif line.kind is _LineType.OBJECT_KEY:
                    raise NestedtextError("expected value after multiline object key")
                else:
                    value = ""
        if key in data:
            # Found duplicate key.
            if on_dup == DuplicateFieldBehaviour.USE_FIRST:
                continue
            elif on_dup == DuplicateFieldBehaviour.USE_LAST:
                pass
            elif on_dup == DuplicateFieldBehaviour.ERROR:
                _report("duplicate key", line, colno=depth)
        data[key] = value
    return data


def _read_object_key(lines: _LinesIter, depth: int) -> str:
    data = []
    while (
        lines.peek_next()
        and lines.peek_next().kind is _LineType.OBJECT_KEY
        and lines.peek_next().depth == depth
    ):
        line = next(lines)
        data.append(line.value)
    data[-1] = data[-1].rstrip("\r\n")
    return "".join(data)


def _read_string(lines: _LinesIter, depth: int) -> str:
    data = []
    while (
        lines.peek_next()
        and lines.peek_next().kind is _LineType.STRING
        and lines.peek_next().depth >= depth
    ):
        line = next(lines)
        data.append(line.value)
        if line.depth != depth:
            _indentation_error(line, depth)
    data[-1] = data[-1].rstrip("\r\n")
    return "".join(data)


def _read_all(lines: Iterable[str], on_dup: DuplicateFieldBehaviour):
    lines = _LinesIter(lines)
    if lines.peek_next() is None:
        return None
    return _read_value(lines, 0, on_dup)


def loads(
    content: str, *, on_dup=DuplicateFieldBehaviour.ERROR
) -> Optional[NestedtextType]:
    return _read_all(content.splitlines(), on_dup)


def load(
    fp: os.PathLike, *, on_dup=DuplicateFieldBehaviour.ERROR
) -> Optional[NestedtextType]:
    # Do not invoke the read method as that would read in the entire contents of
    # the file, possibly consuming a lot of memory. Instead pass the file
    # pointer into _read_all(), it will iterate through the lines, discarding
    # them once they are no longer needed, which reduces the memory usage.
    with open(fp, "r", encoding="utf-8") as f:
        return _read_all(f, on_dup=on_dup)


# ------------------------------------------------------------------------------
# Dumping logic
# ------------------------------------------------------------------------------


def _render_key(s):
    if not isinstance(s, str):
        raise NestedtextError("keys must be strings")
    stripped = s.strip(" ")
    if "\n" in s:
        raise NestedtextError("keys must not contain newlines")
    if (
        len(stripped) < len(s)
        or s[:1] in ["#", "'", '"']
        or s.startswith("- ")
        or s.startswith("> ")
        or ": " in s
    ):
        if "'" in s:
            quotes = '"', "'"
        else:
            quotes = "'", '"'

        # try extracting key using various both quote characters
        # if extracted key matches given key, accept
        for quote_char in quotes:
            key = quote_char + s + quote_char
            # matches = dict_item_recognizer.fullmatch(key + ":")
            # if matches and matches.group("key") == s:
            #     return key
        raise NestedtextError("cannot disambiguate key")
    return s


def _add_leader(s, leader):
    # split into separate lines
    # add leader to each non-blank line
    # add right-stripped leader to each blank line
    # rejoin and return
    return "\n".join(
        leader + line if line else leader.rstrip() for line in s.split("\n")
    )


def _add_prefix(prefix, suffix):
    # A simple formatting of dict and list items will result in a space
    # after the colon or dash if the value is placed on next line.
    # This, function simply eliminates that space.
    if not suffix or suffix.startswith("\n"):
        return prefix + suffix
    return prefix + " " + suffix


def dumps(obj, *, sort_keys=False, indent=4):
    raise NotImplementedError


def dump(obj, fp, **kwargs):
    fp.write(dumps(obj, **kwargs))
