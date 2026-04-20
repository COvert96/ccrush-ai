"""Property-based tests for move legality invariants.

Uses Hypothesis to validate:
- Every generated move is adjacent.
- Every generated move produces at least one match.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ccrush.rules.match import MatchDetector
from ccrush.rules.moves import MoveGenerator
from ccrush.simulator.board import SyntheticBoard
from ccrush.state.models import CandyColor


@st.composite
def random_board(draw: st.DrawFn):
    """Strategy that produces a random ``GameState`` via ``SyntheticBoard``."""
    rows = draw(st.integers(min_value=3, max_value=9))
    cols = draw(st.integers(min_value=3, max_value=9))
    seed = draw(st.integers(min_value=0, max_value=2**31))
    board = SyntheticBoard(rows=rows, cols=cols, seed=seed)
    return board.generate()


@given(state=random_board())
@settings(max_examples=50, deadline=5000)
def test_generated_moves_are_adjacent(state):
    """Every move from MoveGenerator is orthogonally adjacent."""
    gen = MoveGenerator()
    for move in gen.generate(state):
        assert move.is_adjacent()


@given(state=random_board())
@settings(max_examples=50, deadline=5000)
def test_generated_moves_produce_match(state):
    """Every move from MoveGenerator produces at least one match."""
    gen = MoveGenerator()
    detector = MatchDetector()
    for move in gen.generate(state):
        trial = state.model_copy(deep=True)
        a = trial.cells[move.r1][move.c1]
        b = trial.cells[move.r2][move.c2]
        a.color, b.color = b.color, a.color
        matches = detector.find_matches(trial)
        assert len(matches) > 0, f"Move {move} produced no match on board"


@given(state=random_board())
@settings(max_examples=50, deadline=5000)
def test_no_unknown_in_generated_moves(state):
    """No generated move involves an UNKNOWN-color cell."""
    gen = MoveGenerator()
    for move in gen.generate(state):
        assert state.cell(move.r1, move.c1).color != CandyColor.UNKNOWN
        assert state.cell(move.r2, move.c2).color != CandyColor.UNKNOWN
