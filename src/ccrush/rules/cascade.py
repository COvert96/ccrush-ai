"""Cascade simulation engine.

Orchestrates the match → clear → gravity → refill loop after a swap,
tracking cascade depth and cumulative results.  Terminates when no further
matches are found or the configurable ``max_depth`` is reached.
"""
from __future__ import annotations

import random

from ccrush.rules.gravity import GravityEngine
from ccrush.rules.match import MatchDetector
from ccrush.state.models import (
    CandyColor,
    GameState,
    Move,
    SimResult,
    SpecialType,
)

# Colors eligible for random refill (excludes UNKNOWN).
_REFILL_COLORS: list[CandyColor] = [c for c in CandyColor if c != CandyColor.UNKNOWN]

_DEFAULT_MAX_DEPTH: int = 50


class CascadeSimulator:
    """Simulate the full cascade resulting from a single swap.

    Parameters
    ----------
    max_depth : int
        Maximum number of cascade iterations before forced termination.
    refill_seed : int | None
        If provided, the random refill of vacated cells is seeded for
        deterministic results.  ``None`` leaves refills as ``UNKNOWN``
        (suitable for pure-logic tests where refill content is irrelevant).
    """

    def __init__(
        self,
        max_depth: int = _DEFAULT_MAX_DEPTH,
        refill_seed: int | None = None,
    ) -> None:
        self.max_depth = max_depth
        self._refill_seed = refill_seed
        self._match_detector = MatchDetector()
        self._gravity = GravityEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(self, state: GameState, move: Move) -> SimResult:
        """Simulate *move* on a copy of *state* and return the outcome.

        Parameters
        ----------
        state : GameState
            Pre-move board snapshot.
        move : Move
            The swap to apply.

        Returns
        -------
        SimResult
            Aggregated cascade outcome.
        """
        rng = (
            random.Random(self._refill_seed)
            if self._refill_seed is not None
            else None
        )
        board = state.model_copy(deep=True)
        self._apply_swap(board, move)

        total_cleared = 0
        specials: list[SpecialType] = []
        depth = 0

        while depth < self.max_depth:
            matches = self._match_detector.find_matches(board)
            if not matches:
                break

            depth += 1

            # Clear matched cells and accumulate metadata.
            for m in matches:
                total_cleared += len(m.cells)
                if m.special_created != SpecialType.NONE:
                    specials.append(m.special_created)
                for r, c in m.cells:
                    board.cells[r][c].color = CandyColor.UNKNOWN

            # Gravity compaction.
            board = self._gravity.apply(board)

            # Refill vacated (UNKNOWN + playable) cells.
            self._refill(board, rng)

        return SimResult(
            move=move,
            cleared_count=total_cleared,
            specials_created=specials,
            cascade_depth=depth,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_swap(board: GameState, move: Move) -> None:
        """Swap colors of the two cells indicated by *move* in-place."""
        a = board.cells[move.r1][move.c1]
        b = board.cells[move.r2][move.c2]
        a.color, b.color = b.color, a.color

    def _refill(self, board: GameState, rng: random.Random | None) -> None:
        """Fill vacated (UNKNOWN + playable) cells.

        If a seed-driven RNG is available, assign random candy colors.
        Otherwise leave cells as ``UNKNOWN`` (they won't form matches).
        """
        if rng is None:
            return
        rows = board.geometry.rows
        cols = board.geometry.cols
        for r in range(rows):
            for c in range(cols):
                cell = board.cells[r][c]
                if cell.playable and cell.color == CandyColor.UNKNOWN:
                    cell.color = rng.choice(_REFILL_COLORS)
