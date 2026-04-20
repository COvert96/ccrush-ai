"""Core domain models for ccrush-ai game state.

All structured state objects are Pydantic v2 models. These contracts are consumed
by the rules engine, strategy engine, simulator, and vision pipeline.

Match-shape merge semantics (e.g. T/L overlap interpretation) are MVP approximations
and subject to empirical correction via live-vs-sim divergence telemetry.
"""
from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CandyColor(IntEnum):
    """Candy color classification.

    ``UNKNOWN`` is used for cells not yet classified or new refill cells.
    """

    UNKNOWN = 0
    RED = 1
    ORANGE = 2
    YELLOW = 3
    GREEN = 4
    BLUE = 5
    PURPLE = 6


class SpecialType(IntEnum):
    """Special candy overlay or cell modifier.

    Values beyond ``COLOR_BOMB`` represent objective-layer or structural states
    that are carried on the cell but not treated as candy specials by the
    Epic 1.1 rules engine.
    """

    NONE = 0
    STRIPED_H = 1
    STRIPED_V = 2
    WRAPPED = 3
    COLOR_BOMB = 4
    JELLY = 5
    BLOCKER = 6
    EMPTY = 7
    UNKNOWN = 8


# ---------------------------------------------------------------------------
# Cell and geometry value objects
# ---------------------------------------------------------------------------

class CellState(BaseModel):
    """State of a single board cell."""

    row: int
    col: int
    playable: bool
    color: CandyColor = CandyColor.UNKNOWN
    special: SpecialType = SpecialType.NONE
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    locked: bool = False
    lock_layers: int = 0
    blocker_hp: int = 0


class GridGeometry(BaseModel):
    """Board grid dimensions and cell sizing."""

    rows: int
    cols: int
    cell_w: float
    cell_h: float
    offset_x: float
    offset_y: float


class BoardBounds(BaseModel):
    """Pixel bounding box of the detected board within a captured frame."""

    x: int
    y: int
    w: int
    h: int
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Game state aggregate
# ---------------------------------------------------------------------------

class GameState(BaseModel):
    """Complete snapshot of the board at one point in time."""

    cells: list[list[CellState]]
    geometry: GridGeometry
    bounds: BoardBounds
    turn: int | None = None
    score: int | None = None
    max_turns: int | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    frame_id: int = 0

    @model_validator(mode="after")
    def _validate_cell_coordinates(self) -> GameState:
        """Ensure each cell's embedded coordinates match its grid position."""
        for r, row in enumerate(self.cells):
            for c, cell in enumerate(row):
                if cell.row != r or cell.col != c:
                    raise ValueError(
                        f"Cell at index ({r}, {c}) has mismatched coordinates "
                        f"({cell.row}, {cell.col})"
                    )
        return self

    def cell(self, r: int, c: int) -> CellState:
        """Return the cell at ``(r, c)``."""
        return self.cells[r][c]

    def playable_mask(self) -> list[list[bool]]:
        """Return a row-major boolean mask of playable cells."""
        return [[cell.playable for cell in row] for row in self.cells]

    def playable_count(self) -> int:
        """Count the number of playable cells on the board."""
        return sum(cell.playable for row in self.cells for cell in row)


# ---------------------------------------------------------------------------
# Move and simulation result
# ---------------------------------------------------------------------------

class Move(BaseModel):
    """A swap between two board positions."""

    r1: int
    c1: int
    r2: int
    c2: int

    def is_adjacent(self) -> bool:
        """Return whether the two positions are orthogonally adjacent."""
        dr = abs(self.r2 - self.r1)
        dc = abs(self.c2 - self.c1)
        return (dr == 1 and dc == 0) or (dr == 0 and dc == 1)


class SimResult(BaseModel):
    """Outcome of simulating a single move through the cascade engine."""

    move: Move
    cleared_count: int = 0
    specials_created: list[SpecialType] = Field(default_factory=list)
    cascade_depth: int = 0
    # Reserved for policy/scoring layer (not populated by Epic 1.1 cascade loop).
    score_estimate: float = 0.0
    # Reserved for blocker objective tracking in later epics.
    blocker_progress: int = 0
    # Reserved for jelly objective tracking in later epics.
    jelly_cleared: int = 0


class RankedMove(BaseModel):
    """A move annotated with simulation result and policy evaluation score."""

    move: Move
    sim_result: SimResult
    policy_score: float
    policy_name: str
    rank: int = 0


# ---------------------------------------------------------------------------
# Policy context (consumed by strategy engine in later epics)
# ---------------------------------------------------------------------------

class PolicyContext(BaseModel):
    """Inputs the strategy dispatcher uses to select and configure a policy."""

    turns_left: int | None
    board_playable_fraction: float
    unknown_cell_fraction: float
    time_budget_ms: float = 800.0
    objective: str = "score"
