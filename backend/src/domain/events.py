"""Domain events — placeholder for future event-driven patterns."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ZoomEvent:
    """Represents a zoom/emphasis event at a specific timestamp."""
    time: float
    intensity: float = 1.0
    duration: float = 0.5
