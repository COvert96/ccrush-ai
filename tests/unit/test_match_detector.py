"""Unit tests for ccrush.rules.match — MatchDetector."""
from __future__ import annotations

from ccrush.rules.match import MatchDetector
from ccrush.state.models import SpecialType
from tests.helpers import make_board


class TestHorizontalMatches:
    def test_simple_3_in_a_row(self) -> None:
        state = make_board("""
            R R R B G
            G B P R O
            Y B Y G B
        """)
        results = MatchDetector().find_matches(state)
        # Row 0: R R R
        matched_positions = {pos for m in results for pos in m.cells}
        assert (0, 0) in matched_positions
        assert (0, 1) in matched_positions
        assert (0, 2) in matched_positions

    def test_4_in_a_row_creates_striped(self) -> None:
        state = make_board("""
            R R R R G
            G B P Y O
            Y B Y G B
        """)
        results = MatchDetector().find_matches(state)
        striped = [m for m in results if m.special_created in (
            SpecialType.STRIPED_H, SpecialType.STRIPED_V)]
        assert len(striped) >= 1

    def test_5_in_a_row_creates_color_bomb(self) -> None:
        state = make_board("""
            R R R R R
            G B P Y O
            Y B Y G B
        """)
        results = MatchDetector().find_matches(state)
        bombs = [m for m in results if m.special_created == SpecialType.COLOR_BOMB]
        assert len(bombs) == 1


class TestVerticalMatches:
    def test_simple_3_in_column(self) -> None:
        state = make_board("""
            R G B
            R B P
            R Y O
        """)
        results = MatchDetector().find_matches(state)
        matched_positions = {pos for m in results for pos in m.cells}
        assert (0, 0) in matched_positions
        assert (1, 0) in matched_positions
        assert (2, 0) in matched_positions

    def test_vertical_4_creates_striped(self) -> None:
        state = make_board("""
            R G B
            R B P
            R Y O
            R G B
        """)
        results = MatchDetector().find_matches(state)
        striped = [m for m in results if m.special_created in (
            SpecialType.STRIPED_H, SpecialType.STRIPED_V)]
        assert len(striped) >= 1


class TestTLShapes:
    def test_t_shape_creates_wrapped(self) -> None:
        state = make_board("""
            G R G
            R R R
            G R G
        """)
        results = MatchDetector().find_matches(state)
        wrapped = [m for m in results if m.special_created == SpecialType.WRAPPED]
        assert len(wrapped) >= 1

    def test_l_shape_creates_wrapped(self) -> None:
        state = make_board("""
            R G B
            R G B
            R R R
        """)
        results = MatchDetector().find_matches(state)
        wrapped = [m for m in results if m.special_created == SpecialType.WRAPPED]
        assert len(wrapped) >= 1


class TestNoMatch:
    def test_no_matches(self) -> None:
        state = make_board("""
            R G B
            G B R
            B R G
        """)
        results = MatchDetector().find_matches(state)
        assert results == []


class TestNonPlayableCells:
    def test_holes_break_runs(self) -> None:
        """A '.' hole in the middle should prevent a 3-match."""
        state = make_board("""
            R . R R G
            G B P Y O
            Y B Y G B
        """)
        results = MatchDetector().find_matches(state)
        # The hole at (0,1) breaks the R run; only (0,2)-(0,3) is length 2 — no match.
        matched_positions = {pos for m in results for pos in m.cells}
        assert (0, 0) not in matched_positions


class TestMatchResultContract:
    def test_match_result_has_required_fields(self) -> None:
        state = make_board("""
            R R R B G
            G B P R O
            Y B Y G B
        """)
        results = MatchDetector().find_matches(state)
        assert len(results) >= 1
        m = results[0]
        assert hasattr(m, "cells")
        assert hasattr(m, "color")
        assert hasattr(m, "special_created")
        assert isinstance(m.cells, (list, tuple, set, frozenset))
