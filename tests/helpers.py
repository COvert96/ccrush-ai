"""Shared test helpers for building board fixtures concisely."""
from __future__ import annotations

from ccrush.state.models import (
    BoardBounds,
    CandyColor,
    CellState,
    GameState,
    GridGeometry,
    SpecialType,
)

# Single-character shorthand → CandyColor mapping.
_CHAR_MAP: dict[str, CandyColor] = {
    "R": CandyColor.RED,
    "O": CandyColor.ORANGE,
    "Y": CandyColor.YELLOW,
    "G": CandyColor.GREEN,
    "B": CandyColor.BLUE,
    "P": CandyColor.PURPLE,
    ".": CandyColor.UNKNOWN,  # non-playable hole
}


def make_board(text: str) -> GameState:
    """Build a ``GameState`` from a human-readable text grid.

    Characters:
        R O Y G B P — candy colors
        .           — non-playable hole (``playable=False``)

    Example::

        state = make_board('''
            R R R B G
            G B P R O
            Y Y Y G B
        ''')

    Parameters
    ----------
    text : str
        Multi-line whitespace-separated grid of single-letter color codes.

    Returns
    -------
    GameState
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    rows_data: list[list[str]] = [line.split() for line in lines]
    n_rows = len(rows_data)
    n_cols = len(rows_data[0]) if n_rows else 0

    cells: list[list[CellState]] = []
    for r, row_tokens in enumerate(rows_data):
        row: list[CellState] = []
        for c, token in enumerate(row_tokens):
            color = _CHAR_MAP.get(token, CandyColor.UNKNOWN)
            playable = token != "."
            special = SpecialType.EMPTY if not playable else SpecialType.NONE
            row.append(
                CellState(
                    row=r, col=c, playable=playable,
                    color=color, special=special,
                )
            )
        cells.append(row)

    geometry = GridGeometry(
        rows=n_rows, cols=n_cols,
        cell_w=50.0, cell_h=50.0,
        offset_x=0.0, offset_y=0.0,
    )
    bounds = BoardBounds(x=0, y=0, w=n_cols * 50, h=n_rows * 50)
    return GameState(cells=cells, geometry=geometry, bounds=bounds)


def color_grid(state: GameState) -> list[list[CandyColor]]:
    """Extract a row-major color matrix from a ``GameState``."""
    return [[cell.color for cell in row] for row in state.cells]
