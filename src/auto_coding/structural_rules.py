"""Shared structural thresholds — single source of truth for text-length classification.

Import from here instead of writing bare numbers (3, 5, 10, 100, 120) in other modules.
"""

SHORT_TEXT_MAX_CHARS = 3   # ≤ this → short_text (unit_table_validator flag)
LONG_TEXT_MIN_CHARS = 120   # ≥ this → long_text (unit_table_validator flag)

# Pilot sampler uses slightly different thresholds for structural difficulty
# sampling, but must reference these constants, not hardcode bare numbers.
PILOT_SHORT_TEXT_CHARS = 5   # sampler fallback: len(text) ≤ this
PILOT_LONG_TEXT_CHARS = 120  # sampler fallback: len(text) ≥ this
