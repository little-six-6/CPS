"""Base classes for edge-side modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModuleState:
    running: bool = False
    initialized: bool = False


class BaseModule(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self.state = ModuleState()

    @abstractmethod
    def start(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError
