"""Local alert simulation."""

from __future__ import annotations

import time
from typing import Iterable


class LocalAlert:
    def __init__(self, methods: Iterable[str] | None = None) -> None:
        self.methods = list(methods or ["console"])

    def trigger(self, message: str) -> None:
        if "console" in self.methods:
            print(f"[ALERT] {time.strftime('%Y-%m-%d %H:%M:%S')} {message}")
