import textwrap

import pytest

import nestedtext as nt


lines_iter_cases = {
    "valid-mixture": (
        textwrap.dedent(
            """\
            - list item
            -
              - nested
              -
              > string
              key1: val
              key2 :
            """
        ),
        [
            nt._Line("- list item\n", 1, nt._LineType.LIST_ITEM, 0, "list item"),
            nt._Line("-\n", 2, nt._LineType.LIST_ITEM, 0, None),
            nt._Line("  - nested\n", 3, nt._LineType.LIST_ITEM, 2, "nested"),
            nt._Line("  -\n", 4, nt._LineType.LIST_ITEM, 2, None),
            nt._Line("  > string\n", 5, nt._LineType.STRING, 2, "string\n"),
            nt._Line("  key1: val\n", 6, nt._LineType.OBJECT_ITEM, 2, ("key1", "val")),
            nt._Line("  key2 :\n", 7, nt._LineType.OBJECT_ITEM, 2, ("key2", None)),
        ],
    )
}


@pytest.mark.parametrize(
    "input_text, expected", lines_iter_cases.values(), ids=lines_iter_cases.keys()
)
def test_lines_iter(input_text, expected):
    iterator = nt._LinesIter(input_text.splitlines(keepends=True))
    assert list(iterator) == expected
