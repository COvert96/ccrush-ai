"""Unit tests for ccrush.state.models — all Pydantic v2 domain models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ccrush.state.models import (
    BoardBounds,
    CandyColor,
    CellState,
    GameState,
    GridGeometry,
    Move,
    PolicyContext,
    RankedMove,
    SimResult,
    SpecialType,
)

# ---------------------------------------------------------------------------
# CandyColor enum
# ---------------------------------------------------------------------------

class TestCandyColor:
    def test_unknown_is_zero(self) -> None:
        assert CandyColor.UNKNOWN == 0

    def test_all_six_named_colors_exist(self) -> None:
        names = {"RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"}
        actual = {c.name for c in CandyColor if c != CandyColor.UNKNOWN}
        assert actual == names

    def test_values_are_sequential(self) -> None:
        expected = list(range(7))
        assert [c.value for c in CandyColor] == expected


# ---------------------------------------------------------------------------
# SpecialType enum
# ---------------------------------------------------------------------------

class TestSpecialType:
    def test_none_is_zero(self) -> None:
        assert SpecialType.NONE == 0

    def test_required_members_exist(self) -> None:
        required = {
            "NONE", "STRIPED_H", "STRIPED_V", "WRAPPED",
            "COLOR_BOMB", "JELLY", "BLOCKER", "EMPTY", "UNKNOWN",
        }
        actual = {s.name for s in SpecialType}
        assert required <= actual


# ---------------------------------------------------------------------------
# CellState
# ---------------------------------------------------------------------------

class TestCellState:
    def test_defaults(self) -> None:
        cell = CellState(row=0, col=0, playable=True)
        assert cell.color == CandyColor.UNKNOWN
        assert cell.special == SpecialType.NONE
        assert cell.confidence == 1.0
        assert cell.locked is False
        assert cell.lock_layers == 0
        assert cell.blocker_hp == 0

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            CellState(row=0, col=0, playable=True, confidence=1.5)
        with pytest.raises(ValidationError):
            CellState(row=0, col=0, playable=True, confidence=-0.1)

    def test_explicit_values(self) -> None:
        cell = CellState(
            row=3, col=5, playable=True,
            color=CandyColor.RED, special=SpecialType.WRAPPED,
            confidence=0.85, locked=True, lock_layers=2, blocker_hp=1,
        )
        assert cell.row == 3
        assert cell.col == 5
        assert cell.color == CandyColor.RED
        assert cell.special == SpecialType.WRAPPED
        assert cell.locked is True


# ---------------------------------------------------------------------------
# GridGeometry
# ---------------------------------------------------------------------------

class TestGridGeometry:
    def test_basic_construction(self) -> None:
        g = GridGeometry(rows=9, cols=9, cell_w=71.0, cell_h=71.0,
                         offset_x=10.0, offset_y=20.0)
        assert g.rows == 9
        assert g.cols == 9


# ---------------------------------------------------------------------------
# BoardBounds
# ---------------------------------------------------------------------------

class TestBoardBounds:
    def test_basic_construction(self) -> None:
        b = BoardBounds(x=100, y=200, w=640, h=640)
        assert b.confidence == 1.0

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            BoardBounds(x=0, y=0, w=1, h=1, confidence=2.0)


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

class TestGameState:
    @staticmethod
    def _make_cells(rows: int = 3, cols: int = 3) -> list[list[CellState]]:
        return [
            [CellState(row=r, col=c, playable=True, color=CandyColor.RED)
             for c in range(cols)]
            for r in range(rows)
        ]

    @staticmethod
    def _make_geometry(rows: int = 3, cols: int = 3) -> GridGeometry:
        return GridGeometry(rows=rows, cols=cols, cell_w=50.0, cell_h=50.0,
                            offset_x=0.0, offset_y=0.0)

    @staticmethod
    def _make_bounds() -> BoardBounds:
        return BoardBounds(x=0, y=0, w=150, h=150)

    def test_cell_accessor(self) -> None:
        gs = GameState(cells=self._make_cells(), geometry=self._make_geometry(),
                       bounds=self._make_bounds())
        assert gs.cell(1, 2).row == 1
        assert gs.cell(1, 2).col == 2

    def test_playable_mask(self) -> None:
        gs = GameState(cells=self._make_cells(), geometry=self._make_geometry(),
                       bounds=self._make_bounds())
        mask = gs.playable_mask()
        assert all(all(row) for row in mask)

    def test_playable_count(self) -> None:
        gs = GameState(cells=self._make_cells(4, 5), geometry=self._make_geometry(4, 5),
                       bounds=self._make_bounds())
        assert gs.playable_count() == 20

    def test_optional_fields_default_none(self) -> None:
        gs = GameState(cells=self._make_cells(), geometry=self._make_geometry(),
                       bounds=self._make_bounds())
        assert gs.turn is None
        assert gs.score is None
        assert gs.max_turns is None

    def test_rejects_mismatched_cell_coordinates(self) -> None:
        cells = self._make_cells()
        cells[1][1] = CellState(row=0, col=0, playable=True, color=CandyColor.RED)

        with pytest.raises(ValidationError):
            GameState(
                cells=cells,
                geometry=self._make_geometry(),
                bounds=self._make_bounds(),
            )


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------

class TestMove:
    def test_adjacent_horizontal(self) -> None:
        assert Move(r1=0, c1=0, r2=0, c2=1).is_adjacent()

    def test_adjacent_vertical(self) -> None:
        assert Move(r1=0, c1=0, r2=1, c2=0).is_adjacent()

    def test_not_adjacent_diagonal(self) -> None:
        assert not Move(r1=0, c1=0, r2=1, c2=1).is_adjacent()

    def test_not_adjacent_far(self) -> None:
        assert not Move(r1=0, c1=0, r2=0, c2=3).is_adjacent()

    def test_same_cell_not_adjacent(self) -> None:
        assert not Move(r1=2, c1=2, r2=2, c2=2).is_adjacent()


# ---------------------------------------------------------------------------
# SimResult
# ---------------------------------------------------------------------------

class TestSimResult:
    def test_defaults(self) -> None:
        m = Move(r1=0, c1=0, r2=0, c2=1)
        sr = SimResult(move=m)
        assert sr.cleared_count == 0
        assert sr.specials_created == []
        assert sr.cascade_depth == 0
        assert sr.score_estimate == 0.0


# ---------------------------------------------------------------------------
# RankedMove
# ---------------------------------------------------------------------------

class TestRankedMove:
    def test_construction(self) -> None:
        m = Move(r1=0, c1=0, r2=0, c2=1)
        sr = SimResult(move=m, cleared_count=3)
        rm = RankedMove(move=m, sim_result=sr, policy_score=42.0,
                        policy_name="greedy")
        assert rm.rank == 0
        assert rm.policy_name == "greedy"


# ---------------------------------------------------------------------------
# PolicyContext
# ---------------------------------------------------------------------------

class TestPolicyContext:
    def test_defaults(self) -> None:
        pc = PolicyContext(turns_left=None, board_playable_fraction=0.9,
                           unknown_cell_fraction=0.0)
        assert pc.time_budget_ms == 800.0
        assert pc.objective == "score"
