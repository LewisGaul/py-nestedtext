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

__all__ = ("load", "loads", "dump", "dumps", "NestedTextError")


import collections
import collections.abc
import enum
import re
import textwrap
from typing import Callable, Dict, Iterable, List, Optional, Union


class NestedTextError(ValueError):
    r"""
    The *load* and *dump* functions all raise *NestedTextError* when they
    discover an error. *NestedTextError* subclasses both the Python *ValueError*
    and the *Error* exception from *Inform*.  You can find more documentation on
    what you can do with this exception in the `Inform documentation
    <https://inform.readthedocs.io/en/stable/api.html#exceptions>`_.

    The exception provides the following attributes:

    source:

        The source of the *NestedText* content, if given. This is often a
        filename.

    line:

        The text of the line of *NestedText* content where the problem was found.

    lineno:

        The number of the line where the problem was found.

    colno:

        The number of the character where the problem was found on *line*.

    prev_line:

        The text of the meaningful line immediately before where the problem was
        found.  This would not be a comment or blank line.

    template:

        The possibly parameterized text used for the error message.

    As with most exceptions, you can simply cast it to a string to get a
    reasonable error message.

    .. code-block:: python

        >>> from textwrap import dedent
        >>> import nestedtext as nt

        >>> content = dedent('''
        ...     name1: value1
        ...     name1: value2
        ...     name3: value3
        ... ''').strip()

        >>> try:
        ...     print(nt.loads(content))
        ... except nt.NestedTextError as e:
        ...     print(str(e))
        2: duplicate key: name1.

    You can also use the *_report* method to print the message directly. This is
    appropriate if you are using *inform* for your messaging as it follows
    *inform*'s conventions::

        >> try:
        ..     print(nt.loads(content))
        .. except nt.NestedTextError as e:
        ..     e._report()
        error: 2: duplicate key: name1.
            «name1: value2»
             ▲

    The *terminate* method prints the message directly and exits::

        >> try:
        ..     print(nt.loads(content))
        .. except nt.NestedTextError as e:
        ..     e.terminate()
        error: 2: duplicate key: name1.
            «name1: value2»
             ▲

    With exceptions generated from :func:`load` or :func:`loads` you may see
    extra lines at the end of the message that show the problematic lines if
    you have the exception _report itself as above.  Those extra lines are
    referred to as the codicil and they can be very helpful in illustrating the
    actual problem. You do not get them if you simply cast the exception to a
    string, but you can access them using :meth:`NestedTextError.get_codicil`.
    The codicil or codicils are returned as a tuple.  You should join them with
    newlines before printing them.

    .. code-block:: python

        >>> try:
        ...     print(nt.loads(content))
        ... except nt.NestedTextError as e:
        ...     print(e.get_message())
        ...     print(*e.get_codicil(), sep="\n")
        duplicate key: name1.
           1 «name1: value1»
           2 «name1: value2»
              ▲

    Note the « and » characters in the codicil. They delimit the extend of the
    text on each line and help you see troublesome leading or trailing white
    space.

    Exceptions produced by *NestedText* contain a *template* attribute that
    contains the basic text of the message. You can change this message by
    overriding the attribute using the *template* argument when using *_report*,
    *terminate*, or *render*.  *render* is like casting the exception to a
    string except that allows for the passing of arguments.  For example, to
    convert a particular message to Spanish, you could use something like the
    following.

    .. code-block:: python

        >>> try:
        ...     print(nt.loads(content))
        ... except nt.NestedTextError as e:
        ...     template = None
        ...     if e.template == 'duplicate key: {}.':
        ...         template = 'llave duplicada: {}.'
        ...     print(e.render(template=template))
        2: llave duplicada: name1.

    """

    def __init__(self, template: str, culprit=None):
        super().__init__(template)


# Converts NestedText into Python data hierarchies.

# regular expressions used to recognize dict items
dict_item_regex = r"""
    (?P<quote>["']?)       # leading quote character, optional
    (?P<key>.*?)           # key
    (?P=quote)             # matching quote character
    \s*                    # optional white space
    :                      # separator
    (?:\ (?P<value>.*))?   # value
"""
dict_item_recognizer = re.compile(dict_item_regex, re.VERBOSE)


def _report(message, line, *args, colno=None, **kwargs):
    raise NestedTextError(template=message)


def _indentation_error(line, depth):
    assert line.depth != depth
    prev_line = line.prev_line
    if not line.prev_line and depth == 0:
        msg = "top-level content must start in column 1"
    elif (
        prev_line
        and prev_line.value
        and prev_line.depth < line.depth
        and prev_line.kind in [_LineType.LIST, _LineType.DICT]
    ):
        if prev_line.value.strip() == "":
            obs = ", which in this case consists only of whitespace"
        else:
            obs = ""
        msg = " ".join(
            [
                "invalid indentation.",
                "An indent may only follow a dictionary or list item that does",
                f"not already have a value{obs}.",
            ]
        )
    elif prev_line and prev_line.depth > line.depth:
        msg = "invalid indentation, partial dedent"
    else:
        msg = "invalid indentation"
    _report(textwrap.fill(msg), line, colno=depth)


_Line = collections.namedtuple(
    "_Line", "text, lineno, kind, depth, key, value, prev_line"
)


class _LineType(enum.Enum):
    BLANK = enum.auto()
    COMMENT = enum.auto()
    STRING = enum.auto()
    LIST = enum.auto()
    DICT = enum.auto()
    EOF = enum.auto()
    UNRECOGNISED = enum.auto()

    def __repr__(self):
        return str(self)

    def is_ignorable(self) -> bool:
        return self in [self.BLANK, self.COMMENT]


class _LinesIter(Iterable[_Line]):
    def __init__(self, lines):
        self._generator = self._read_lines(lines)
        self._next_line: Optional[_Line] = self._advance_to_next_content_line()

    def __iter__(self):
        return self

    def __next__(self) -> _Line:
        if self._next_line is None:
            raise StopIteration

        this_line = self._next_line
        self._next_line = self._advance_to_next_content_line()
        if this_line.kind is _LineType.UNRECOGNISED:
            _report("unrecognized line", this_line)
        return this_line

    def _read_lines(self, lines):
        prev_line = None
        for lineno, line in enumerate(lines):
            depth = None
            key = None
            value = None
            line = line.rstrip("\n")

            # compute indentation
            stripped = line.lstrip()
            depth = len(line) - len(stripped)

            # determine line type and extract values
            if stripped == "":
                kind = _LineType.BLANK
                value = None
                depth = None
            elif stripped[0] == "#":
                kind = _LineType.COMMENT
                value = line[1:].strip()
                depth = None
            elif stripped == "-" or stripped.startswith("- "):
                kind = _LineType.LIST
                value = stripped[2:]
            elif stripped == ">" or stripped.startswith("> "):
                kind = _LineType.STRING
                value = stripped[2:]
            else:
                matches = dict_item_recognizer.fullmatch(stripped)
                if matches:
                    kind = _LineType.DICT
                    key = matches.group("key")
                    value = matches.group("value")
                    if value is None:
                        value = ""
                else:
                    kind = _LineType.UNRECOGNISED
                    value = line

            # bundle information about line
            the_line = _Line(
                text=line,
                lineno=lineno + 1,
                kind=kind,
                depth=depth,
                key=key,
                value=value,
                prev_line=None,
            )
            if not kind.is_ignorable():
                prev_line = the_line

            # check the indent for non-spaces
            if depth:
                first_non_space = len(line) - len(line.lstrip(" "))
                if first_non_space < depth:
                    _report(
                        f"invalid character in indentation: {line[first_non_space]!r}.",
                        the_line,
                        colno=first_non_space,
                    )

            yield the_line

        yield _Line(None, None, _LineType.EOF, 0, None, None, None)

    def _advance_to_next_content_line(self) -> Optional[_Line]:
        """Advance the generator the next useful line and return it."""
        next_line = next(self._generator, None)
        while next_line and next_line.kind.is_ignorable():
            next_line = next(self._generator, None)
        return next_line

    def peek_next(self) -> Optional[_Line]:
        return self._next_line


def _read_value(lines: _LinesIter, depth: int, on_dup) -> Union[str, List, Dict]:
    if lines.peek_next().kind is _LineType.LIST:
        return _read_list(lines, depth, on_dup)
    if lines.peek_next().kind is _LineType.DICT:
        return _read_dict(lines, depth, on_dup)
    if lines.peek_next().kind is _LineType.STRING:
        return _read_string(lines, depth)
    _report("unrecognized line", next(lines))


def _read_list(lines: _LinesIter, depth: int, on_dup) -> List:
    data = []
    while lines.peek_next().depth >= depth:
        line = next(lines)
        if line.kind is _LineType.EOF:
            break
        if line.depth != depth:
            _indentation_error(line, depth)
        if line.kind is not _LineType.LIST:
            _report("expected list item", line, colno=depth)
        if line.value:
            data.append(line.value)
        else:
            # Value may simply be empty, or it may be on next line, in which
            # case it must be indented.
            depth_of_next = lines.peek_next().depth
            if depth_of_next > depth:
                value = _read_value(lines, depth_of_next, on_dup)
            else:
                value = ""
            data.append(value)
    return data


def _read_dict(lines: _LinesIter, depth: int, on_dup) -> Dict:
    data = {}
    while lines.peek_next().depth >= depth:
        line = next(lines)
        if line.kind is _LineType.EOF:
            break
        if line.depth != depth:
            _indentation_error(line, depth)
        if line.kind is not _LineType.DICT:
            _report("expected dictionary item", line, colno=depth)
        key = line.key
        value = line.value
        if not value:
            depth_of_next = lines.peek_next().depth
            if depth_of_next > depth:
                value = _read_value(lines, depth_of_next, on_dup)
            else:
                value = ""
        if line.key in data:
            # Found duplicate key.
            if on_dup is None:
                _report("duplicate key: {}", line, line.key, colno=depth)
            if on_dup == "ignore":
                continue
            if isinstance(on_dup, dict):
                key = on_dup["_callback_func"](key, value, data, on_dup)
                assert key not in data
            elif on_dup != "replace":
                raise ValueError(f"{on_dup}: unknown value for on_dup")
        data[key] = value
    return data


def _read_string(lines: _LinesIter, depth: int) -> str:
    data = []
    next_line = lines.peek_next()
    while next_line.kind is _LineType.STRING and next_line.depth >= depth:
        line = next(lines)
        data.append(line.value)
        if line.depth != depth:
            _indentation_error(line, depth)
        next_line = lines.peek_next()
    return "\n".join(data)


def _read_all(lines, on_dup):
    if callable(on_dup):
        on_dup = dict(_callback_func=on_dup)

    lines = _LinesIter(lines)

    if lines.peek_next().kind is _LineType.EOF:
        return None
    return _read_value(lines, 0, on_dup)


def loads(
    content: str, *, on_dup: Optional[Union[Callable, str]] = None
) -> Union[str, List, Dict, None]:
    r"""
    Loads *NestedText* from string.

    Args:
        content (str):
            String that contains encoded data.
        on_dup (str or func):
            Indicates how duplicate keys in dictionaries should be handled. By
            default they raise exceptions. Specifying 'ignore' causes them to be
            ignored (first wins). Specifying 'replace' results in them replacing
            earlier items (last wins). By specifying a function, the keys can be
            de-duplicated.  This call-back function returns a new key and takes
            four arguments:

            1. The new key (duplicates an existing key).
            2. The new value.
            3. The entire dictionary as it is at the moment the duplicate key is
               found.
            4. The state; a dictionary that is created as the *loads* is called
               and deleted as it returns. Values placed in this dictionary are
               retained between multiple calls to this call back function.

    Returns:
        The extracted data.

    Raises:
        NestedTextError: if there is a problem in the *NextedText* content.

    Examples:

        *NestedText* is specified to *loads* in the form of a string:

        .. code-block:: python

            >>> import nestedtext as nt

            >>> contents = '''
            ... name: Kristel Templeton
            ... sex: female
            ... age: 74
            ... '''

            >>> try:
            ...     data = nt.loads(contents)
            ... except nt.NestedTextError as e:
            ...     print("ERROR:", e)

            >>> print(data)
            {'name': 'Kristel Templeton', 'sex': 'female', 'age': '74'}

        Here is a typical example of reading *NestedText* from a file:

        .. code-block:: python

            >>> filename = 'examples/duplicate-keys.nt'
            >>> try:
            ...     with open(filename, encoding='utf-8') as f:
            ...         addresses = nt.loads(f.read())
            ... except nt.NestedTextError as e:
            ...     print("ERROR:", e)

        Notice in the above example the encoding is explicitly specified as
        'utf-8'.  *NestedText* files should always be read and written using
        *utf-8* encoding.

        The following examples demonstrate the various ways of handling
        duplicate keys:

        .. code-block:: python

            >>> content = '''
            ... key: value 1
            ... key: value 2
            ... key: value 3
            ... name: value 4
            ... name: value 5
            ... '''

            >>> print(nt.loads(content))
            Traceback (most recent call last):
            ...
            nestedtext.NestedTextError: 3: duplicate key: key.

            >>> print(nt.loads(content, on_dup='ignore'))
            {'key': 'value 1', 'name': 'value 4'}

            >>> print(nt.loads(content, on_dup='replace'))
            {'key': 'value 3', 'name': 'value 5'}

            >>> def de_dup(key, value, data, state):
            ...     if key not in state:
            ...         state[key] = 1
            ...     state[key] += 1
            ...     return f"{key}#{state[key]}"

            >>> print(nt.loads(content, on_dup=de_dup))
            {'key': 'value 1', 'key#2': 'value 2', 'key#3': 'value 3', 'name': 'value 4', 'name#2': 'value 5'}

    """
    return _read_all(content.splitlines(), on_dup)


def load(
    f, *, on_dup: Optional[Union[Callable, str]] = None
) -> Union[str, List, Dict, None]:
    r"""
    Loads *NestedText* from file or stream.

    Is the same as :func:`loads` except the *NextedText* is accessed by reading
    a file rather than directly from a string. It does not keep the full
    contents of the file in memory and so is more memory efficient with large
    files.

    Args:
        f (str, os.PathLike, io.TextIOBase, collections.abc.Iterator):
            The file to read the *NestedText* content from.  This can be
            specified either as a path (e.g. a string or a `pathlib.Path`),
            as a text IO object (e.g. an open file), or as an iterator.  If a
            path is given, the file will be opened, read, and closed.  If an IO
            object is given, it will be read and not closed; utf-8 encoding
            should be used..  If an iterator is given, it should generate full
            lines in the same manner that iterating on a file descriptor would.

        kwargs:
            See :func:`loads` for optional arguments.

    Returns:
        The extracted data.
        See :func:`loads` description of the return value.

    Raises:
        NestedTextError: if there is a problem in the *NextedText* content.
        OSError: if there is a problem opening the file.

    Examples:

        Load from a path specified as a string:

        .. code-block:: python

            >>> import nestedtext as nt
            >>> print(open('examples/groceries.nt').read())
            groceries:
              - Bread
              - Peanut butter
              - Jam
            <BLANKLINE>

            >>> nt.load('examples/groceries.nt')
            {'groceries': ['Bread', 'Peanut butter', 'Jam']}

        Load from a `pathlib.Path`:

        .. code-block:: python

            >>> from pathlib import Path
            >>> nt.load(Path('examples/groceries.nt'))
            {'groceries': ['Bread', 'Peanut butter', 'Jam']}

        Load from an open file object:

        .. code-block:: python

            >>> with open('examples/groceries.nt') as f:
            ...     nt.load(f)
            ...
            {'groceries': ['Bread', 'Peanut butter', 'Jam']}

    """

    # Do not invoke the read method as that would read in the entire contents of
    # the file, possibly consuming a lot of memory. Instead pass the file
    # pointer into _read_all(), it will iterate through the lines, discarding
    # them once they are no longer needed, which reduces the memory usage.

    if isinstance(f, collections.abc.Iterator):
        return _read_all(f, on_dup)
    else:
        source = str(f)
        with open(f, encoding="utf-8") as fp:
            return _read_all(fp, on_dup)


# Convert Python data hierarchies to NestedText.


def _render_key(s):
    if not isinstance(s, str):
        raise NestedTextError(template="keys must be strings.", culprit=s)
    stripped = s.strip(" ")
    if "\n" in s:
        raise NestedTextError("keys must not contain newlines", culprit=repr(s))
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
            matches = dict_item_recognizer.fullmatch(key + ":")
            if matches and matches.group("key") == s:
                return key
        raise NestedTextError("cannot disambiguate key", culprit=key)
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
    pass


def dump(obj, fp, **kwargs):
    fp.write(dumps(obj, **kwargs))
