"""Undo/redo manager using Scenario snapshots."""

from __future__ import annotations
import copy
from typing import Optional, List
from models import Scenario


class UndoManager:
    """Snapshot-based undo/redo. Call `push(scenario)` immediately BEFORE
    mutating the scenario, to record the state that should be restored."""

    def __init__(self, max_history: int = 50):
        self._undo_stack: List[Scenario] = []
        self._redo_stack: List[Scenario] = []
        self.max_history = max_history

    def push(self, scenario: Scenario) -> None:
        self._undo_stack.append(copy.deepcopy(scenario))
        if len(self._undo_stack) > self.max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self, current: Scenario) -> Optional[Scenario]:
        if not self._undo_stack:
            return None
        self._redo_stack.append(copy.deepcopy(current))
        return self._undo_stack.pop()

    def redo(self, current: Scenario) -> Optional[Scenario]:
        if not self._redo_stack:
            return None
        self._undo_stack.append(copy.deepcopy(current))
        return self._redo_stack.pop()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
