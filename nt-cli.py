#!/usr/bin/env python3

"""
CLI tool for converting between NestedText, JSON and YAML.
"""

import argparse
import enum
import logging
import sys


logger = logging.getLogger(__name__)


class Format(enum.Enum):
    NESTEDTEXT = enum.auto()
    JSON = enum.auto()
    YAML = enum.auto()

    @classmethod
    def from_str(cls, fmt: str):
        fmt = fmt.lower()
        if fmt in ["nt", "nestedtext"]:
            return cls.NESTEDTEXT
        elif fmt == "json":
            return cls.JSON
        elif fmt == "yaml":
            return cls.YAML
        else:
            raise NotImplementedError

    def load(self, fp):
        if self is Format.NESTEDTEXT:
            import nestedtext as nt

            return nt.load(fp)
        elif self is Format.JSON:
            import json

            return json.load(fp)
        elif self is Format.YAML:
            import yaml

            return yaml.safe_load(fp)
        else:
            raise NotImplementedError

    def dump(self, obj, fp):
        if self is Format.NESTEDTEXT:
            import nestedtext as nt

            return nt.dump(obj, fp)
        elif self is Format.JSON:
            import json

            return json.dump(obj, fp)
        elif self is Format.YAML:
            import yaml

            return yaml.dump(obj, fp)
        else:
            raise NotImplementedError


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--infile", help="Input file (defaults to stdin)")
    parser.add_argument("-o", "--outfile", help="Output file (defaults to stdout)")
    parser.add_argument(
        "-F",
        "--infmt",
        type=Format.from_str,
        default=Format.NESTEDTEXT,
        help="Input format (defaults to 'nt')",
    )
    parser.add_argument(
        "-O",
        "--outfmt",
        type=Format.from_str,
        default=Format.JSON,
        help="Output format (defaults to 'json')",
    )
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)

    if args.infile:
        with open(args.infile, "r") as f:
            obj = args.infmt.load(f)
    else:
        obj = args.infmt.load(sys.stdin)

    if args.outfile:
        with open(args.outfile, "w") as f:
            obj = args.outfmt.dump(obj, f)
    else:
        obj = args.outfmt.dump(obj, sys.stdout)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        logger.info("Exiting on Ctrl+C")
