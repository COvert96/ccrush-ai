"""Gravity resolution for the rules engine.

After cells are cleared (color set to ``CandyColor.UNKNOWN``), surviving cells
drop downward within each playable column.  Vacated positions at the top are
filled with ``CandyColor.UNKNOWN`` (representing stochastic refill in live play
or deterministic refill in the simulator).
"""
from __future__ import annotations

from ccrush.state.models import CandyColor, GameState


class GravityEngine:
    """Apply downward gravity to a ``GameState``.

    Cleared cells are identified by ``color == CandyColor.UNKNOWN`` while still
    ``playable``.  Non-playable cells (structural holes) are never moved.
    """

    def apply(self, state: GameState) -> GameState:
        """Return a new ``GameState`` with gravity applied column-by-column.

        Parameters
        ----------
        state : GameState
            Board snapshot with some cells cleared (``UNKNOWN`` color).

        Returns
        -------
        GameState
            A deep-copied state with surviving cells compacted downward.
        """
        new_state = state.model_copy(deep=True)
        rows = new_state.geometry.rows
        cols = new_state.geometry.cols

        for c in range(cols):
            # Collect playable cells in this column (top-to-bottom order).
            playable_indices = [r for r in range(rows) if new_state.cell(r, c).playable]
            if not playable_indices:
                continue

            # Extract non-cleared colors from bottom to top.
            surviving: list[CandyColor] = []
            for r in reversed(playable_indices):
                cell = new_state.cell(r, c)
                if cell.color != CandyColor.UNKNOWN:
                    surviving.append(cell.color)

            # surviving is bottom-to-top; fill from the bottom of playable slots.
            for idx, r in enumerate(reversed(playable_indices)):
                cell = new_state.cells[r][c]
                if idx < len(surviving):
                    cell.color = surviving[idx]
                else:
                    cell.color = CandyColor.UNKNOWN

        return new_state
