"""Integration regression: offline workflow from board to cascade outcome.

Validates the core developer workflow: deterministic board creation →
legal move enumeration → cascade simulation, exercising the cross-module
contract that Epic 1.1 exists to establish.
"""
from __future__ import annotations

from ccrush.rules.cascade import CascadeSimulator
from ccrush.rules.moves import MoveGenerator
from ccrush.simulator.board import SyntheticBoard
from ccrush.state.models import CandyColor, SimResult
from tests.helpers import make_board


class TestOfflineWorkflow:
    """End-to-end integration regression for the offline rules engine."""

    def test_synthetic_board_to_move_to_cascade(self) -> None:
        """SyntheticBoard → MoveGenerator → CascadeSimulator round-trip."""
        board = SyntheticBoard(rows=7, cols=7, seed=42)
        state = board.generate()
        gen = MoveGenerator()
        moves = gen.generate(state)

        # A 7×7 seeded board should have at least one legal move.
        assert len(moves) > 0, "Expected at least one legal move on a 7×7 seeded board"

        sim = CascadeSimulator(refill_seed=99)
        result = sim.simulate(state, moves[0])

        assert isinstance(result, SimResult)
        assert result.cleared_count >= 3, "A legal move must clear at least 3 cells"
        assert result.cascade_depth >= 1, "At least one cascade step expected"

    def test_make_board_to_move_to_cascade(self) -> None:
        """make_board fixture → MoveGenerator → CascadeSimulator round-trip."""
        state = make_board("""
            G B P O G
            R G R R B
            O Y B P Y
        """)
        gen = MoveGenerator()
        moves = gen.generate(state)

        assert len(moves) > 0, "Expected at least one legal move on the fixture board"

        sim = CascadeSimulator(refill_seed=7)
        result = sim.simulate(state, moves[0])

        assert isinstance(result, SimResult)
        assert result.cleared_count >= 3

    def test_determinism_across_repeated_runs(self) -> None:
        """Same seed → same board → same moves → same cascade outcome."""
        results: list[SimResult] = []
        for _ in range(3):
            board = SyntheticBoard(rows=7, cols=7, seed=42)
            state = board.generate()
            moves = MoveGenerator().generate(state)
            sim = CascadeSimulator(refill_seed=99)
            result = sim.simulate(state, moves[0])
            results.append(result)

        assert all(r.cleared_count == results[0].cleared_count for r in results)
        assert all(r.cascade_depth == results[0].cascade_depth for r in results)
        assert all(r.specials_created == results[0].specials_created for r in results)

    def test_no_moves_on_homogeneous_board(self) -> None:
        """A board with all identical colors produces no legal moves."""
        state = make_board("""
            R R R R R
            R R R R R
            R R R R R
        """)
        gen = MoveGenerator()
        moves = gen.generate(state)

        assert moves == [], "Homogeneous board should yield no legal moves"

    def test_move_colors_are_never_unknown(self) -> None:
        """Every cell involved in a legal move has a known candy color."""
        board = SyntheticBoard(rows=9, cols=9, seed=123)
        state = board.generate()
        moves = MoveGenerator().generate(state)

        for m in moves:
            assert state.cell(m.r1, m.c1).color != CandyColor.UNKNOWN
            assert state.cell(m.r2, m.c2).color != CandyColor.UNKNOWN
