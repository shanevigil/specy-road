#!/usr/bin/env python3
"""PM-oriented roadmap CRUD: list/show/add/edit/archive nodes in chunk YAML."""

from __future__ import annotations

import sys

from roadmap_crud_argparse import build_parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()
