"""HiGHS backend for the aircraft scheduling model."""

from .model import build_and_solve_model

__all__ = [
    'build_and_solve_model',
]
