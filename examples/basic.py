#!/usr/bin/env python3

from pprint import pprint

import nestedtext as nt


nt_string = """
int: 1
float: 3.14
str: foo
multiline:
  > hello
  > world
list:
  - foo
  - bar
"""


pprint(nt.loads(nt_string))
