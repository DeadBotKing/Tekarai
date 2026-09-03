"""Backward-compatible import surface for the Phase 13 AI errors.

The package ``apps.ai.domain.exceptions`` is authoritative. This module is
kept as a compatibility marker for older tooling that expects exceptions.py.
"""

from apps.ai.domain.exceptions.aiExceptions import *  # noqa: F401,F403
