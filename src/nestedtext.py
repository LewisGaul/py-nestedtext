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
import io
import json
import os
import re
from typing import Any, Dict, Iterable, Iterator, List, NoReturn, Optional, Tuple, Union


NestedtextType = Union[str, List["NestedtextType"], Dict[str, "NestedTextType"]]
NestedtextContainerType = Union[List[NestedtextType], Dict[str, NestedtextType]]


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
    INLINE_CONTAINER = enum.auto()

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

    def _read_lines(self, lines: Iterable[str]) -> Iterator[Union[_Line, _InvalidLine]]:
        for idx, line in enumerate(lines):
            yield self._read_line(line, idx + 1)

    def _read_line(self, line: str, lineno: int) -> Union[_Line, _InvalidLine]:
        if not line.strip():
            return _Line(line, lineno, _LineType.BLANK, 0, None)

        text = line.rstrip("\r\n")

        # Comments can have any leading whitespace.
        if text.lstrip()[0] == "#":
            return _Line(line, lineno, _LineType.COMMENT, 0, text.lstrip()[1:])

        stripped = text.lstrip(" ")
        depth = len(text) - len(stripped)

        # Otherwise check leading whitespace consists only of spaces.
        if len(stripped.lstrip()) < len(stripped):
            return _InvalidLine(line, lineno, _InvalidLineType.NON_SPACE_INDENT, depth)

        def _read_content_line() -> Optional[Tuple[_LineType, Any]]:
            # Now handle normal content lines!
            if stripped == "-" or stripped.startswith("- "):
                return _LineType.LIST_ITEM, stripped[2:] or None
            elif stripped == ">" or stripped.startswith("> "):
                # Include end-of-line characters.
                value = re.sub(r"> ?", "", line.lstrip(" "), count=1)
                return _LineType.STRING, value
            elif stripped == ":" or stripped.startswith(": "):
                # Include end-of-line characters.
                value = re.sub(r": ?", "", line.lstrip(" "), count=1)
                return _LineType.OBJECT_KEY, value
            elif stripped[0] in "[{":
                return _LineType.INLINE_CONTAINER, stripped

            # Object item?
            match = re.fullmatch(r"(?P<key>.+?)\s*:(?: (?P<value>.*))?", stripped)
            if match:
                return _LineType.OBJECT_ITEM, tuple(match.groups())

            return None

        result = _read_content_line()
        if result:
            return _Line(line, lineno, result[0], depth, result[1])
        else:
            return _InvalidLine(line, lineno, _InvalidLineType.UNRECOGNISED, depth)

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


class _Parser:
    def __init__(self, *, on_dup=DuplicateFieldBehaviour.ERROR):
        self.on_dup = on_dup

    def parse(self, lines: Iterable[str]):
        lines = _LinesIter(lines)
        if lines.peek_next() is None:
            return None
        return self._read_value(lines, 0)

    def _read_value(self, lines: _LinesIter, depth: int) -> Union[str, List, Dict]:
        if lines.peek_next().kind is _LineType.STRING:
            return self._read_string(lines, depth)
        elif lines.peek_next().kind is _LineType.LIST_ITEM:
            return self._read_list(lines, depth)
        elif lines.peek_next().kind in [_LineType.OBJECT_ITEM, _LineType.OBJECT_KEY]:
            return self._read_object(lines, depth)
        elif lines.peek_next().kind is _LineType.INLINE_CONTAINER:
            return self._read_inline_container(lines, depth)
        _report("unrecognized line", next(lines))

    def _read_string(self, lines: _LinesIter, depth: int) -> str:
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

    def _read_list(self, lines: _LinesIter, depth: int) -> List[NestedtextType]:
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
                        value = self._read_value(lines, depth_of_next)
                    else:
                        value = ""
                data.append(value)
        return data

    def _read_object(self, lines: _LinesIter, depth: int) -> Dict[str, NestedtextType]:
        data = {}
        while lines.peek_next() and lines.peek_next().depth >= depth:
            line = lines.peek_next()
            if line.depth != depth:
                _indentation_error(line, depth)
            if line.kind is _LineType.OBJECT_ITEM:
                next(lines)  # Advance the iterator
                key, value = line.value
            elif line.kind is _LineType.OBJECT_KEY:
                key = self._read_object_key(lines, depth)
                value = None
            else:
                _report("expected object item", line, colno=depth)
            if not value:
                if lines.peek_next() is None:
                    if line.kind is _LineType.OBJECT_KEY:
                        raise NestedtextError(
                            "expected value after multiline object key"
                        )
                    value = ""
                else:
                    depth_of_next = lines.peek_next().depth
                    if depth_of_next > depth:
                        value = self._read_value(lines, depth_of_next)
                    elif line.kind is _LineType.OBJECT_KEY:
                        raise NestedtextError(
                            "expected value after multiline object key"
                        )
                    else:
                        value = ""
            if key in data:
                # Found duplicate key.
                if self.on_dup == DuplicateFieldBehaviour.USE_FIRST:
                    continue
                elif self.on_dup == DuplicateFieldBehaviour.USE_LAST:
                    pass
                elif self.on_dup == DuplicateFieldBehaviour.ERROR:
                    _report("duplicate key", line, colno=depth)
            data[key] = value
        return data

    def _read_object_key(self, lines: _LinesIter, depth: int) -> str:
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

    def _read_inline_container(
        self, lines: _LinesIter, depth: int
    ) -> NestedtextContainerType:
        line = next(lines)
        assert line.kind is _LineType.INLINE_CONTAINER
        line_text = line.value
        # Convert into valid JSON!
        line_text.replace('"', '\\"')  # Escape quotes
        line_text.replace("\t", "\\t")  # Escape tabs
        # Quote list items.
        line_text = re.sub(
            r"([\[,])\s*([^\[\]\{\}]+?)\s*(?=[,\]])", r'\1"\2"', line_text
        )
        # Quote dict keys.
        line_text = re.sub(r"([\{,])\s*([^\[\]\{\}:]+?)\s*(?=:)", r'\1"\2"', line_text)
        # Quote dict values.
        line_text = re.sub(
            r"([\{,][^\[\]]+?):\s*([^\[\]\{\}:]+?)\s*(?=[,\}])", r'\1:"\2"', line_text
        )
        try:
            return json.loads(line_text)
        except json.JSONDecodeError:
            _report("Invalid inline list/object", line)


def loads(
    content: str, *, on_dup=DuplicateFieldBehaviour.ERROR
) -> Optional[NestedtextType]:
    """
    Deserialize 'content' (a NestedText document) to a Python object.
    """
    return load(io.StringIO(content), on_dup=on_dup)


def load(
    stream: Iterable, *, on_dup=DuplicateFieldBehaviour.ERROR
) -> Optional[NestedtextType]:
    """
    Deserialize 'stream' (an iterable of lines corresponding to a NestedText
    document) to a Python object.
    """
    return _Parser(on_dup=on_dup).parse(stream)


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


def _dump_internal(obj, writer, sort_keys=False, indent=4):
    pass


class _Dumper:
    def __init__(self, sort_keys: bool, indent: int):
        self.sort_keys = sort_keys
        self.indent_size = indent

    def dump(self, obj, writer):
        if isinstance(obj, str):
            self._dump_multiline_str(obj, writer, 0)
        elif isinstance(obj, list):
            self._dump_list(obj, writer, 0)
        elif isinstance(obj, dict):
            self._dump_object(obj, writer, 0)
        else:
            raise NestedtextError(
                "Unsupported type to dump {!r}".format(type(obj).__name__)
            )

    def _dump_multiline_str(self, string: str, writer, indent: int):
        lines = string.splitlines(keepends=True)
        for line in lines:
            writer.write(" " * indent)
            writer.write("> " if line.strip("\r\n") else ">")
            writer.write(line)
        if string == "" or string[-1] in "\r\n":
            writer.write(" " * indent)
            writer.write(">")

    def _dump_list(self, values: list, writer, indent: int):
        if len(values) == 0:
            writer.write(" " * indent)
            writer.write("[]\n")
            return
        for value in values:
            writer.write(" " * indent)
            writer.write("-")
            if isinstance(value, str):
                if "\r" in value or "\n" in value:
                    writer.write("\n")
                    self._dump_multiline_str(value, writer, indent + self.indent_size)
                elif value:
                    writer.write(" ")
                    writer.write(value)
                writer.write("\n")
            elif isinstance(value, list):
                writer.write("\n")
                self._dump_list(value, writer, indent + self.indent_size)
            elif isinstance(value, dict):
                writer.write("\n")
                self._dump_object(value, writer, indent + self.indent_size)
            else:
                raise NestedtextError(
                    "Unsupported type to dump {!r}".format(type(value).__name__)
                )

    def _dump_object(self, obj: dict, writer, indent: int):
        if len(obj) == 0:
            writer.write(" " * indent)
            writer.write("{}\n")
            return
        for key, value in obj.items():
            if not isinstance(key, str):
                raise NestedtextError("Unsupported object key type to dump")
            if not re.fullmatch(r"[^\[\{:\->\s][^:\r\n]*", key):
                self._dump_multiline_object_key(key, writer, indent)
                force_multiline = True
            else:
                writer.write(" " * indent)
                writer.write(key)
                writer.write(":")
                force_multiline = False

            if isinstance(value, str):
                if "\r" in value or "\n" in value or force_multiline:
                    writer.write("\n")
                    self._dump_multiline_str(value, writer, indent + self.indent_size)
                elif value:
                    writer.write(" ")
                    writer.write(value)
                writer.write("\n")
            elif isinstance(value, list):
                writer.write("\n")
                self._dump_list(value, writer, indent + self.indent_size)
            elif isinstance(value, dict):
                writer.write("\n")
                self._dump_object(value, writer, indent + self.indent_size)
            else:
                raise NestedtextError(
                    "Unsupported type to dump {!r}".format(type(value).__name__)
                )

    def _dump_multiline_object_key(self, key: str, writer, indent: int):
        lines = key.splitlines(keepends=True)
        for line in lines:
            writer.write(" " * indent)
            writer.write(": " if line.strip("\r\n") else ":")
            writer.write(line)
        if key == "" or key[-1] in "\r\n":
            writer.write(" " * indent)
            writer.write(":")


def dumps(obj, *, sort_keys: bool = False, indent: int = 4) -> str:
    """
    Serialize 'obj' to NestedText and return the result.
    """
    string = io.StringIO()
    dump(obj, string, sort_keys=sort_keys, indent=indent)
    return string.getvalue()


def dump(obj, writer, *, sort_keys: bool = False, indent: int = 4) -> None:
    """
    Serialize 'obj' to NestedText and write out to 'writer' (an object that
    supports the '.write()' method).
    """
    _Dumper(sort_keys, indent).dump(obj, writer)
