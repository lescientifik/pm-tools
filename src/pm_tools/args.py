"""Shared argparse utilities for pm-tools CLI."""

from __future__ import annotations

import argparse


def positive_int(value: str) -> int:
    """Argparse type: positive integer.

    Raises:
        argparse.ArgumentTypeError: If value is not a positive integer.
    """
    try:
        n = int(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got '{value}'") from err
    if n <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {n}")
    return n
