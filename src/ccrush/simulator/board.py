"""Synthetic board generator for offline testing and policy comparison.

The simulator is a **policy-comparison environment**, not a verified model of
the live game.  Boards are generated with a deterministic seed so that test
results are reproducible.
"""
from __future__ import annotations

import random

from ccrush.state.models import (
    BoardBounds,
    CandyColor,
    CellState,
    GameState,
    GridGeometry,
    SpecialType,
)

# Named candy colors (excludes UNKNOWN = 0).
_CANDY_COLORS: list[CandyColor] = [
    CandyColor.RED,
    CandyColor.ORANGE,
    CandyColor.YELLOW,
    CandyColor.GREEN,
    CandyColor.BLUE,
    CandyColor.PURPLE,
]


class SyntheticBoard:
    """Generate reproducible boards of configurable size.

    Parameters
    ----------
    rows : int
        Number of rows (≥ 3).
    cols : int
        Number of columns (≥ 3).
    seed : int
        RNG seed for deterministic generation.
    holes : list[tuple[int, int]] | None
        Positions ``(row, col)`` to mark as non-playable structural holes.
    """

    def __init__(
        self,
        rows: int = 9,
        cols: int = 9,
        seed: int = 0,
        holes: list[tuple[int, int]] | None = None,
    ) -> None:
        self.rows = rows
        self.cols = cols
        self.seed = seed
        self.holes: set[tuple[int, int]] = set(holes) if holes else set()

    def generate(self) -> GameState:
        """Build and return a fresh ``GameState``."""
        rng = random.Random(self.seed)

        cells: list[list[CellState]] = []
        for r in range(self.rows):
            row: list[CellState] = []
            for c in range(self.cols):
                playable = (r, c) not in self.holes
                color = rng.choice(_CANDY_COLORS) if playable else CandyColor.UNKNOWN
                special = SpecialType.EMPTY if not playable else SpecialType.NONE
                row.append(
                    CellState(
                        row=r,
                        col=c,
                        playable=playable,
                        color=color,
                        special=special,
                    )
                )
            cells.append(row)

        geometry = GridGeometry(
            rows=self.rows,
            cols=self.cols,
            cell_w=50.0,
            cell_h=50.0,
            offset_x=0.0,
            offset_y=0.0,
        )
        bounds = BoardBounds(
            x=0, y=0,
            w=int(self.cols * 50),
            h=int(self.rows * 50),
        )
        return GameState(cells=cells, geometry=geometry, bounds=bounds)
