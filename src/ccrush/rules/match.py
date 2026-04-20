"""Match detection for the rules engine.

Scans a board for runs of 3+ same-color cells in rows and columns, merges
overlapping runs into composite shapes (T/L), and determines what special
candy each match creates.

**MVP note on T/L merge semantics**: Overlapping horizontal and vertical runs
that share at least one cell are merged into a single match tagged as
``SpecialType.WRAPPED``. This is an approximation; exact Candy Crush SA
behaviour is proprietary and will be refined via divergence telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass

from ccrush.state.models import CandyColor, GameState, SpecialType


@dataclass(frozen=True, slots=True)
class MatchResult:
    """A single detected match on the board.

    Attributes
    ----------
    cells : frozenset[tuple[int, int]]
        The ``(row, col)`` positions that participate in this match.
    color : CandyColor
        The candy color of the matched cells.
    special_created : SpecialType
        The special candy this match produces (``NONE`` for a plain 3-match).
    """

    cells: frozenset[tuple[int, int]]
    color: CandyColor
    special_created: SpecialType = SpecialType.NONE


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scan_runs(
    state: GameState,
    dr: int,
    dc: int,
) -> list[tuple[CandyColor, list[tuple[int, int]]]]:
    """Scan the board along one axis and return raw runs of length ≥ 3.

    Parameters
    ----------
    dr, dc : int
        Direction vector — ``(0, 1)`` for horizontal, ``(1, 0)`` for vertical.
    """
    rows = state.geometry.rows
    cols = state.geometry.cols
    runs: list[tuple[CandyColor, list[tuple[int, int]]]] = []

    # Determine iteration order: outer loop perpendicular, inner along direction.
    if dr == 0 and dc == 1:
        outers = range(rows)
        inners = range(cols)
    else:
        outers = range(cols)
        inners = range(rows)

    for outer in outers:
        run_color: CandyColor | None = None
        run_cells: list[tuple[int, int]] = []

        for inner in inners:
            r = outer if dr == 0 else inner
            c = inner if dr == 0 else outer
            cell = state.cell(r, c)

            if (
                cell.playable
                and cell.color != CandyColor.UNKNOWN
                and cell.color == run_color
            ):
                run_cells.append((r, c))
            else:
                if len(run_cells) >= 3 and run_color is not None:
                    runs.append((run_color, list(run_cells)))
                # Start new run
                if cell.playable and cell.color != CandyColor.UNKNOWN:
                    run_color = cell.color
                    run_cells = [(r, c)]
                else:
                    run_color = None
                    run_cells = []

        # Flush trailing run
        if len(run_cells) >= 3 and run_color is not None:
            runs.append((run_color, list(run_cells)))

    return runs


def _special_for_run(length: int, direction: tuple[int, int]) -> SpecialType:
    """Determine what special a straight-line run creates."""
    if length >= 5:
        return SpecialType.COLOR_BOMB
    if length == 4:
        # 4-horizontal → vertical stripe; 4-vertical → horizontal stripe
        if direction == (0, 1):
            return SpecialType.STRIPED_V
        return SpecialType.STRIPED_H
    return SpecialType.NONE


def _merge_runs(
    h_runs: list[tuple[CandyColor, list[tuple[int, int]]]],
    v_runs: list[tuple[CandyColor, list[tuple[int, int]]]],
) -> list[MatchResult]:
    """Merge horizontal/vertical runs into ``MatchResult`` objects.

    Overlapping runs of the same color are combined into a single match
    tagged as ``WRAPPED`` (T/L shape heuristic).
    """
    # Build initial match entries keyed by frozenset of cells.
    pending: list[tuple[CandyColor, set[tuple[int, int]], SpecialType]] = []

    for color, cells in h_runs:
        special = _special_for_run(len(cells), (0, 1))
        pending.append((color, set(cells), special))

    for color, cells in v_runs:
        special = _special_for_run(len(cells), (1, 0))
        pending.append((color, set(cells), special))

    # Merge overlapping entries of the same color.
    merged = True
    while merged:
        merged = False
        new_pending: list[tuple[CandyColor, set[tuple[int, int]], SpecialType]] = []
        used: set[int] = set()
        for i in range(len(pending)):
            if i in used:
                continue
            c_i, cells_i, sp_i = pending[i]
            for j in range(i + 1, len(pending)):
                if j in used:
                    continue
                c_j, cells_j, sp_j = pending[j]
                if c_i == c_j and cells_i & cells_j:
                    # Merge: union cells, promote to WRAPPED since we have
                    # runs in two directions intersecting.
                    cells_i = cells_i | cells_j
                    sp_i = SpecialType.WRAPPED
                    used.add(j)
                    merged = True
            new_pending.append((c_i, cells_i, sp_i))
            used.add(i)
        pending = new_pending

    return [
        MatchResult(
            cells=frozenset(cells),
            color=color,
            special_created=special,
        )
        for color, cells, special in pending
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class MatchDetector:
    """Scan a ``GameState`` for all matches (3+ same-color runs).

    Returns a list of ``MatchResult`` objects with merged T/L shapes.
    """

    def find_matches(self, state: GameState) -> list[MatchResult]:
        """Return all matches found on the board.

        Parameters
        ----------
        state : GameState
            The board snapshot to scan.

        Returns
        -------
        list[MatchResult]
        """
        h_runs = _scan_runs(state, dr=0, dc=1)
        v_runs = _scan_runs(state, dr=1, dc=0)

        if not h_runs and not v_runs:
            return []

        return _merge_runs(h_runs, v_runs)
