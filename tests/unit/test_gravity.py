"""Unit tests for ccrush.rules.gravity — GravityEngine."""
from __future__ import annotations

from ccrush.rules.gravity import GravityEngine
from ccrush.state.models import CandyColor
from tests.helpers import make_board


class TestGravityBasic:
    def test_cells_fall_into_cleared_gap(self) -> None:
        """Cleared (UNKNOWN) cells in the middle — candy above should drop."""
        state = make_board("""
            R B G
            G R B
            Y O P
        """)
        # Clear the middle row by setting colors to UNKNOWN (simulating a match clear).
        for cell in state.cells[1]:
            cell.color = CandyColor.UNKNOWN

        engine = GravityEngine()
        result = engine.apply(state)

        # After gravity: row 0 should drop to row 1, row 1 (cleared) fills from top.
        assert result.cell(2, 0).color == CandyColor.YELLOW
        assert result.cell(2, 1).color == CandyColor.ORANGE
        assert result.cell(2, 2).color == CandyColor.PURPLE
        # Row 1 should now have what was in row 0
        assert result.cell(1, 0).color == CandyColor.RED
        assert result.cell(1, 1).color == CandyColor.BLUE
        assert result.cell(1, 2).color == CandyColor.GREEN
        # Row 0 should be UNKNOWN (new refill)
        assert result.cell(0, 0).color == CandyColor.UNKNOWN

    def test_bottom_row_cleared(self) -> None:
        state = make_board("""
            R B G
            G R B
            Y O P
        """)
        # Clear bottom row
        for cell in state.cells[2]:
            cell.color = CandyColor.UNKNOWN
        result = GravityEngine().apply(state)
        # Row 1 contents drop to row 2
        assert result.cell(2, 0).color == CandyColor.GREEN
        assert result.cell(2, 1).color == CandyColor.RED
        # Row 0 drops to row 1
        assert result.cell(1, 0).color == CandyColor.RED
        # New refills at top
        assert result.cell(0, 0).color == CandyColor.UNKNOWN


class TestGravityNonPlayable:
    def test_non_playable_cells_are_not_moved(self) -> None:
        """Holes (non-playable) should stay in place and not participate."""
        state = make_board("""
            R . G
            B . P
            Y . O
        """)
        # Clear row 2 playable cells
        state.cells[2][0].color = CandyColor.UNKNOWN
        state.cells[2][2].color = CandyColor.UNKNOWN
        result = GravityEngine().apply(state)
        # Hole column 1 stays non-playable throughout
        assert not result.cell(0, 1).playable
        assert not result.cell(1, 1).playable
        assert not result.cell(2, 1).playable


class TestGravityNoClears:
    def test_no_change_when_nothing_cleared(self) -> None:
        state = make_board("""
            R B G
            G R B
            Y O P
        """)
        result = GravityEngine().apply(state)
        for r in range(3):
            for c in range(3):
                assert result.cell(r, c).color == state.cell(r, c).color


class TestGravityMultipleGaps:
    def test_multiple_cleared_rows(self) -> None:
        state = make_board("""
            R B G
            Y O P
            G R B
            P Y O
        """)
        # Clear rows 1 and 2
        for cell in state.cells[1]:
            cell.color = CandyColor.UNKNOWN
        for cell in state.cells[2]:
            cell.color = CandyColor.UNKNOWN
        result = GravityEngine().apply(state)
        # Bottom row stays, row 0 drops down 2 positions to row 2
        assert result.cell(3, 0).color == CandyColor.PURPLE
        assert result.cell(2, 0).color == CandyColor.RED
        # Top two rows refilled with UNKNOWN
        assert result.cell(0, 0).color == CandyColor.UNKNOWN
        assert result.cell(1, 0).color == CandyColor.UNKNOWN
