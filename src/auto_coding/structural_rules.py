"""Shared structural thresholds — single source of truth for text-length classification.

Import from here instead of writing bare numbers (3, 5, 10, 100, 120) in other modules.
"""

SHORT_TEXT_MAX_CHARS = 3   # ≤ this → short_text
LONG_TEXT_MIN_CHARS = 120   # ≥ this → long_text
