#!/usr/bin/env python3
"""Atheris harness for NEMA DSL parser."""

from __future__ import annotations

import sys

import atheris

from nema.dsl.parser import parse


def TestOneInput(data: bytes) -> None:
    try:
        parse(data.decode("utf-8", errors="ignore"))
    except Exception:
        # Parser exceptions are expected for malformed inputs.
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
