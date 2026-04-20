"""Unit tests for ccrush.simulator.board — SyntheticBoard generator."""
from __future__ import annotations

from ccrush.simulator.board import SyntheticBoard
from ccrush.state.models import CandyColor, GameState, SpecialType


class TestSyntheticBoard:
    def test_generates_game_state(self) -> None:
        board = SyntheticBoard(rows=5, cols=5, seed=42)
        state = board.generate()
        assert isinstance(state, GameState)

    def test_correct_dimensions(self) -> None:
        state = SyntheticBoard(rows=7, cols=9, seed=0).generate()
        assert len(state.cells) == 7
        assert all(len(row) == 9 for row in state.cells)
        assert state.geometry.rows == 7
        assert state.geometry.cols == 9

    def test_deterministic_with_same_seed(self) -> None:
        s1 = SyntheticBoard(rows=5, cols=5, seed=123).generate()
        s2 = SyntheticBoard(rows=5, cols=5, seed=123).generate()
        colors1 = [[c.color for c in row] for row in s1.cells]
        colors2 = [[c.color for c in row] for row in s2.cells]
        assert colors1 == colors2

    def test_different_seeds_differ(self) -> None:
        s1 = SyntheticBoard(rows=9, cols=9, seed=1).generate()
        s2 = SyntheticBoard(rows=9, cols=9, seed=2).generate()
        colors1 = [[c.color for c in row] for row in s1.cells]
        colors2 = [[c.color for c in row] for row in s2.cells]
        assert colors1 != colors2

    def test_all_cells_playable_by_default(self) -> None:
        state = SyntheticBoard(rows=5, cols=5, seed=0).generate()
        assert state.playable_count() == 25

    def test_only_named_candy_colors_used(self) -> None:
        """No UNKNOWN colors in a freshly generated board."""
        state = SyntheticBoard(rows=9, cols=9, seed=99).generate()
        for row in state.cells:
            for cell in row:
                assert cell.color != CandyColor.UNKNOWN

    def test_minimum_board_size(self) -> None:
        state = SyntheticBoard(rows=3, cols=3, seed=0).generate()
        assert len(state.cells) == 3

    def test_non_playable_holes(self) -> None:
        """Holes specified as (row, col) tuples are marked non-playable."""
        holes = [(0, 0), (2, 2)]
        state = SyntheticBoard(rows=5, cols=5, seed=0, holes=holes).generate()
        assert not state.cell(0, 0).playable
        assert not state.cell(2, 2).playable
        assert state.cell(1, 1).playable

    def test_specials_are_none_by_default(self) -> None:
        state = SyntheticBoard(rows=5, cols=5, seed=0).generate()
        for row in state.cells:
            for cell in row:
                assert cell.special == SpecialType.NONE
