"""Unit tests for ``MoveGenerator``.

The generator enumerates all legal adjacent swaps that produce at least one
match under the current rules engine.
"""
from __future__ import annotations

from ccrush.rules.moves import MoveGenerator
from ccrush.state.models import Move
from tests.helpers import make_board


class TestMoveGenerator:
    """Verify legal move enumeration, filtering, and edge cases."""

    def test_finds_productive_swap(self) -> None:
        """A board with an obvious match-producing swap emits that move."""
        # Swap (1,0) R <-> (1,1) G creates R R R on row 1.
        state = make_board(
            """
            G B P O G
            R G R R B
            O Y B P Y
            """
        )
        gen = MoveGenerator()
        moves = gen.generate(state)

        # The swap at (1,0)<->(1,1) should be among the results.
        expected = Move(r1=1, c1=0, r2=1, c2=1)
        move_set = {(m.r1, m.c1, m.r2, m.c2) for m in moves}
        assert (expected.r1, expected.c1, expected.r2, expected.c2) in move_set

    def test_all_moves_are_adjacent(self) -> None:
        """Every emitted move is an orthogonally adjacent swap."""
        state = make_board(
            """
            R G B G R
            G R G R G
            B G R G B
            """
        )
        gen = MoveGenerator()
        moves = gen.generate(state)

        for move in moves:
            assert move.is_adjacent(), f"Non-adjacent move: {move}"

    def test_all_moves_produce_match(self) -> None:
        """Every emitted move produces at least one match when applied."""
        from ccrush.rules.match import MatchDetector

        state = make_board(
            """
            R G B G R
            G R G R G
            B G R G B
            """
        )
        gen = MoveGenerator()
        detector = MatchDetector()
        moves = gen.generate(state)

        for move in moves:
            swapped = state.model_copy(deep=True)
            a = swapped.cells[move.r1][move.c1]
            b = swapped.cells[move.r2][move.c2]
            a.color, b.color = b.color, a.color
            matches = detector.find_matches(swapped)
            assert len(matches) > 0, f"Move {move} produces no match"

    def test_no_productive_swaps_returns_empty(self) -> None:
        """A board with no match-producing swaps returns an empty list."""
        # 3-color cycle pattern — no adjacent swap creates 3-in-a-row.
        state = make_board(
            """
            R G B R G
            G B R G B
            B R G B R
            R G B R G
            """
        )
        gen = MoveGenerator()
        moves = gen.generate(state)

        assert moves == []

    def test_excludes_non_playable_cells(self) -> None:
        """Moves involving non-playable (hole) cells are never emitted."""
        state = make_board(
            """
            R R . R R
            G B . B G
            R G . G R
            """
        )
        gen = MoveGenerator()
        moves = gen.generate(state)

        for move in moves:
            c1 = state.cell(move.r1, move.c1)
            c2 = state.cell(move.r2, move.c2)
            assert c1.playable, f"Move uses non-playable cell: ({move.r1},{move.c1})"
            assert c2.playable, f"Move uses non-playable cell: ({move.r2},{move.c2})"

    def test_no_duplicate_moves(self) -> None:
        """Each unique swap pair appears at most once (no (a,b) and (b,a))."""
        state = make_board(
            """
            R G B G R
            G R G R G
            B G R G B
            """
        )
        gen = MoveGenerator()
        moves = gen.generate(state)

        # Normalise each swap so (min, max) ordering is consistent.
        seen: set[tuple[int, int, int, int]] = set()
        for m in moves:
            key = (
                min(m.r1, m.r2), min(m.c1, m.c2),
                max(m.r1, m.r2), max(m.c1, m.c2),
            )
            assert key not in seen, f"Duplicate move: {m}"
            seen.add(key)

    def test_single_row_board(self) -> None:
        """Generator works on a degenerate single-row board."""
        state = make_board("R G R R G")
        gen = MoveGenerator()
        moves = gen.generate(state)

        # Swap (0,0) R <-> (0,1) G creates G R R R G → RRR at cols 1,2,3.
        expected = Move(r1=0, c1=0, r2=0, c2=1)
        move_set = {(m.r1, m.c1, m.r2, m.c2) for m in moves}
        assert (expected.r1, expected.c1, expected.r2, expected.c2) in move_set
