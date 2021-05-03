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


def dumps(obj, *, sort_keys=False, indent=4, renderers=None, default=None, level=0):
    """Recursively convert object to *NestedText* string.

    Args:
        obj:
            The object to convert to *NestedText*.
        sort_keys (bool or func):
            Dictionary items are sorted by their key if *sort_keys* is true.
            If a function is passed in, it is used as the key function.
        indent (int):
            The number of spaces to use to represent a single level of
            indentation.  Must be one or greater.
        renderers (dict):
            A dictionary where the keys are types and the values are render
            functions (functions that take an object and convert it to a string).
            These will be used to convert values to strings during the
            conversion.
        default (func or 'strict'):
            The default renderer. Use to render otherwise unrecognized objects
            to strings. If not provided an error will be raised for unsupported
            data types. Typical values are *repr* or *str*. If 'strict' is
            specified then only dictionaries, lists, strings, and those types
            specified in *renderers* are allowed. If *default* is not specified
            then a broader collection of value types are supported, including
            *None*, *bool*, *int*, *float*, and *list*- and *dict*-like objects.
            In this case Booleans is rendered as 'True' and 'False' and None and
            empty lists and dictionaries are rendered as empty strings.
        level (int):
            The number of indentation levels.  When dumps is invoked recursively
            this is used to increment the level and so the indent.  Generally
            not specified by the user, but can be useful in unusual situations
            to specify an initial indent.

    Returns:
        The *NestedText* content.

    Raises:
        NestedTextError: if there is a problem in the input data.

    Examples:

        .. code-block:: python

            >>> import nestedtext as nt

            >>> data = {
            ...     'name': 'Kristel Templeton',
            ...     'sex': 'female',
            ...     'age': '74',
            ... }

            >>> try:
            ...     print(nt.dumps(data))
            ... except nt.NestedTextError as e:
            ...     print(str(e))
            name: Kristel Templeton
            sex: female
            age: 74

        The *NestedText* format only supports dictionaries, lists, and strings
        and all leaf values must be strings.  By default, *dumps* is configured
        to be rather forgiving, so it will render many of the base Python data
        types, such as *None*, *bool*, *int*, *float* and list-like types such
        as *tuple* and *set* by converting them to the types supported by the
        format.  This implies that a round trip through *dumps* and *loads*
        could result in the types of values being transformed. You can restrict
        *dumps* to only supporting the native types of *NestedText* by passing
        `default='strict'` to *dumps*.  Doing so means that values that are not
        dictionaries, lists, or strings generate exceptions; as do empty
        dictionaries and lists.

        .. code-block:: python

            >>> data = {'key': 42, 'value': 3.1415926, 'valid': True}

            >>> try:
            ...     print(nt.dumps(data))
            ... except nt.NestedTextError as e:
            ...     print(str(e))
            key: 42
            value: 3.1415926
            valid: True

            >>> try:
            ...     print(nt.dumps(data, default='strict'))
            ... except nt.NestedTextError as e:
            ...     print(str(e))
            42: unsupported type.

        Alternatively, you can specify a function to *default*, which is used
        to convert values to strings.  It is used if no other converter is
        available.  Typical values are *str* and *repr*.

        .. code-block:: python

            >>> class Color:
            ...     def __init__(self, color):
            ...         self.color = color
            ...     def __repr__(self):
            ...         return f'Color({self.color!r})'
            ...     def __str__(self):
            ...         return self.color

            >>> data['house'] = Color('red')
            >>> print(nt.dumps(data, default=repr))
            key: 42
            value: 3.1415926
            valid: True
            house: Color('red')

            >>> print(nt.dumps(data, default=str))
            key: 42
            value: 3.1415926
            valid: True
            house: red

        You can also specify a dictionary of renderers. The dictionary maps the
        object type to a render function.

        .. code-block:: python

            >>> renderers = {
            ...     bool: lambda b: 'yes' if b else 'no',
            ...     int: hex,
            ...     float: lambda f: f'{f:0.3}',
            ...     Color: lambda c: c.color,
            ... }

            >>> try:
            ...    print(nt.dumps(data, renderers=renderers))
            ... except nt.NestedTextError as e:
            ...     print(str(e))
            key: 0x2a
            value: 3.14
            valid: yes
            house: red

        If the dictionary maps a type to *None*, then the default behavior is
        used for that type. If it maps to *False*, then an exception is raised.

        .. code-block:: python

            >>> renderers = {
            ...     bool: lambda b: 'yes' if b else 'no',
            ...     int: hex,
            ...     float: False,
            ...     Color: lambda c: c.color,
            ... }

            >>> try:
            ...    print(nt.dumps(data, renderers=renderers))
            ... except nt.NestedTextError as e:
            ...     print(str(e))
            3.1415926: unsupported type.

        Both *default* and *renderers* may be used together. *renderers* has
        priority over the built-in types and *default*.  When a function is
        specified as *default*, it is always applied as a last resort.
    """

    # define sort function
    if sort_keys:

        def sort(keys):
            return sorted(keys, key=sort_keys if callable(sort_keys) else None)

    else:

        def sort(keys):
            return keys

    # define object type identification functions
    if default == "strict":
        is_a_dict = lambda obj: (obj or level == 0) and isinstance(obj, dict)
        is_a_list = lambda obj: (obj or level == 0) and isinstance(obj, list)
        is_a_str = lambda obj: isinstance(obj, str)
        is_a_scalar = lambda obj: False
    else:
        is_a_dict = is_mapping
        is_a_list = is_collection
        is_a_str = is_str
        is_a_scalar = lambda obj: obj is None or isinstance(obj, (bool, int, float))
        if is_str(default):
            raise NotImplementedError(default)

    # define dumps function for recursion
    def rdumps(v):
        return dumps(
            v,
            sort_keys=sort_keys,
            indent=indent,
            renderers=renderers,
            default=default,
            level=level + 1,
        )

    # render content
    assert indent > 0
    error = None
    need_indented_block = is_collection(obj)
    content = ""
    render = renderers.get(type(obj)) if renderers else None
    if render is False:
        error = "unsupported type."
    elif render:
        content = render(obj)
        if "\n" in content or ('"' in content and "'" in content):
            need_indented_block = True
    elif is_a_dict(obj):
        content = "\n".join(
            _add_prefix(_render_key(k) + ":", rdumps(obj[k])) for k in sort(obj)
        )
    elif is_a_list(obj):
        content = "\n".join(_add_prefix("-", rdumps(v)) for v in obj)
    elif is_a_str(obj):
        text = obj.replace("\r\n", "\n").replace("\r", "\n")
        if "\n" in text or level == 0:
            content = _add_leader(text, "> ")
            need_indented_block = True
        else:
            content = text
    elif is_a_scalar(obj):
        if obj is None:
            content = ""
        else:
            content = str(obj)
    elif default and callable(default):
        content = default(obj)
    else:
        error = "unsupported type."

    if need_indented_block and content and level:
        content = "\n" + _add_leader(content, indent * " ")

    if error:
        raise NestedTextError(obj, template=error, culprit=repr(obj))

    return content


def dump(obj, f, **kwargs):
    """Write the *NestedText* representation of the given object to the given file.

    Args:
        obj:
            The object to convert to *NestedText*.
        f (str, os.PathLike, io.TextIOBase):
            The file to write the *NestedText* content to.  The file can be
            specified either as a path (e.g. a string or a `pathlib.Path`) or
            as a text IO instance (e.g. an open file).  If a path is given, the
            will be opened, written, and closed.  If an IO object is given, it
            must have been opened in a mode that allows writing (e.g.
            ``open(path, 'w')``), if applicable.  It will be written and not
            closed.

            The name used for the file is arbitrary but it is tradition to use a
            .nt suffix.  If you also wish to further distinguish the file type
            by giving the schema, it is recommended that you use two suffixes,
            with the suffix that specifies the schema given first and .nt given
            last. For example: flicker.sig.nt.

        kwargs:
            See :func:`dumps` for optional arguments.

    Returns:
        The *NestedText* content.

    Raises:
        NestedTextError: if there is a problem in the input data.
        OSError: if there is a problem opening the file.

    Examples:

        This example writes to a pointer to an open file.

        .. code-block:: python

            >>> import nestedtext as nt
            >>> from inform import fatal, os_error

            >>> data = {
            ...     'name': 'Kristel Templeton',
            ...     'sex': 'female',
            ...     'age': '74',
            ... }

            >>> try:
            ...     with open('data.nt', 'w', encoding='utf-8') as f:
            ...         nt.dump(data, f)
            ... except nt.NestedTextError as e:
            ...     e.terminate()
            ... except OSError as e:
            ...     fatal(os_error(e))

        This example writes to a file specified by file name.  In general, the
        file name and extension are arbitrary. However, by convention a
        '.nt' suffix is generally used for *NestedText* files.

        .. code-block:: python

            >>> try:
            ...     nt.dump(data, 'data.nt')
            ... except nt.NestedTextError as e:
            ...     e.terminate()
            ... except OSError as e:
            ...     fatal(os_error(e))

    """
    content = dumps(obj, **kwargs)

    # Avoid nested try-except blocks, since they lead to chained exceptions
    # (e.g. if the file isn't found, etc.) that unnecessarily complicate the
    # stack trace.

    try:
        f.write(content)
    except AttributeError:
        pass
    else:
        return

    with open(f, "w", encoding="utf-8") as fp:
        fp.write(content)
