"""Legal move generation for the rules engine.

Enumerates all adjacent, playable swaps that produce at least one match
under the current ``MatchDetector``.
"""
from __future__ import annotations

from ccrush.rules.match import MatchDetector
from ccrush.state.models import CandyColor, GameState, Move

# Orthogonal direction vectors: right and down only (avoids duplicates).
_DIRECTIONS: list[tuple[int, int]] = [(0, 1), (1, 0)]


class MoveGenerator:
    """Enumerate legal moves on a ``GameState``.

    A move is *legal* when it swaps two orthogonally adjacent, playable
    cells and the resulting board contains at least one match.

    Parameters
    ----------
    detector : MatchDetector | None
        Optional custom detector instance.  Defaults to a new one.
    """

    def __init__(self, detector: MatchDetector | None = None) -> None:
        self._detector = detector or MatchDetector()

    def generate(self, state: GameState) -> list[Move]:
        """Return all legal moves for the current board.

        Parameters
        ----------
        state : GameState
            Board snapshot to analyse.

        Returns
        -------
        list[Move]
            Legal moves.  May be empty when no productive swap exists.
        """
        rows = state.geometry.rows
        cols = state.geometry.cols
        moves: list[Move] = []

        for r in range(rows):
            for c in range(cols):
                cell = state.cell(r, c)
                if not cell.playable or cell.color == CandyColor.UNKNOWN:
                    continue

                for dr, dc in _DIRECTIONS:
                    nr, nc = r + dr, c + dc
                    if nr >= rows or nc >= cols:
                        continue
                    neighbor = state.cell(nr, nc)
                    if not neighbor.playable or neighbor.color == CandyColor.UNKNOWN:
                        continue
                    if cell.color == neighbor.color:
                        continue  # swapping identical colors is pointless

                    # Trial swap in place, then restore immediately.
                    a = state.cells[r][c]
                    b = state.cells[nr][nc]
                    a.color, b.color = b.color, a.color
                    try:
                        if self._detector.find_matches(state):
                            moves.append(Move(r1=r, c1=c, r2=nr, c2=nc))
                    finally:
                        a.color, b.color = b.color, a.color

        return moves
