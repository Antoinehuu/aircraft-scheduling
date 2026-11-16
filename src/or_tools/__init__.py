"""OR-Tools (CP-SAT) backend for the aircraft scheduling model."""

from .model import (
    build_and_solve
)

__all__ = [
    'build_and_solve'
]
