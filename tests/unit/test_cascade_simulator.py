"""Unit tests for ``CascadeSimulator``.

The simulator orchestrates match → clear → gravity → repeat until stable,
tracking depth and cumulative results in ``SimResult``.
"""
from __future__ import annotations

from ccrush.rules.cascade import CascadeSimulator
from ccrush.state.models import Move, SpecialType
from tests.helpers import make_board


class TestCascadeSimulator:
    """Verify cascade loop logic, depth tracking, and termination."""

    def test_single_match_no_cascade(self) -> None:
        """A swap that creates one match and then stabilises after gravity."""
        state = make_board(
            """
            G B P O G
            R G R R B
            O Y B P Y
            """
        )
        sim = CascadeSimulator()
        # Swap (1,0) R <-> (1,1) G → row 1: G R R R B → R R R 3-match
        move = Move(r1=1, c1=0, r2=1, c2=1)
        result = sim.simulate(state, move)

        assert result.move == move
        assert result.cleared_count >= 3
        assert result.cascade_depth == 1

    def test_chain_cascade(self) -> None:
        """A swap that triggers a multi-step cascade (depth >= 2).

        Board:
            P G R B P
            B G B R G
            R B P G B
            G G R B P

        Swap (1,1) G <-> (2,1) B:
          Row 1 becomes B B B R G → BBB 3-match cleared (depth 1).
        After gravity col 1 survivors [G(0), G(2), G(3)] compact:
          Col 1 rows 1-3 become G G G → vertical 3-match cascade (depth 2).
        """
        state = make_board(
            """
            P G R B P
            B G B R G
            R B P G B
            G G R B P
            """
        )
        sim = CascadeSimulator()
        move = Move(r1=1, c1=1, r2=2, c2=1)
        result = sim.simulate(state, move)

        assert result.cascade_depth >= 2
        assert result.cleared_count == 6  # 3 (BBB) + 3 (GGG)
        assert result.move == move

    def test_max_depth_terminates(self) -> None:
        """Simulator stops at ``max_depth`` even if matches remain."""
        state = make_board(
            """
            P G R B P
            B G B R G
            R B P G B
            G G R B P
            """
        )
        sim = CascadeSimulator(max_depth=1)
        move = Move(r1=1, c1=1, r2=2, c2=1)
        result = sim.simulate(state, move)

        assert result.cascade_depth == 1

    def test_no_match_after_swap(self) -> None:
        """A swap that creates no match returns zero cleared and depth 0."""
        state = make_board(
            """
            R G B
            G B R
            B R G
            """
        )
        sim = CascadeSimulator()
        move = Move(r1=0, c1=0, r2=0, c2=1)
        result = sim.simulate(state, move)

        assert result.cleared_count == 0
        assert result.cascade_depth == 0

    def test_specials_created_tracked(self) -> None:
        """A 5-match produces COLOR_BOMB tracked in ``SimResult``."""
        # Swap (0,2) G <-> (1,2) R → row 1: G G G G G → 5-match → COLOR_BOMB
        state = make_board(
            """
            P B G B P
            G G R G G
            B R P R B
            """
        )
        sim = CascadeSimulator()
        move = Move(r1=0, c1=2, r2=1, c2=2)
        result = sim.simulate(state, move)

        assert SpecialType.COLOR_BOMB in result.specials_created

    def test_deterministic_refill(self) -> None:
        """With a seed, refill colors are deterministic across runs."""
        state = make_board(
            """
            R G B
            G R G
            R R G
            """
        )
        sim = CascadeSimulator(refill_seed=42)
        move = Move(r1=0, c1=0, r2=0, c2=1)
        result1 = sim.simulate(state, move)

        sim2 = CascadeSimulator(refill_seed=42)
        result2 = sim2.simulate(state, move)

        assert result1.cleared_count == result2.cleared_count
        assert result1.cascade_depth == result2.cascade_depth

    def test_reused_simulator_is_deterministic_per_call(self) -> None:
        """Reusing one seeded simulator keeps each call deterministic.

        Candidate move evaluation in strategy code reuses simulator instances.
        Determinism must not depend on prior simulate() calls.
        """
        state = make_board(
            """
            P G R B P
            B G B R G
            R B P G B
            G G R B P
            """
        )
        move_a = Move(r1=1, c1=1, r2=2, c2=1)
        move_b = Move(r1=0, c1=1, r2=1, c2=1)

        reused = CascadeSimulator(refill_seed=42)
        first_a = reused.simulate(state, move_a)
        reused.simulate(state, move_b)
        second_a = reused.simulate(state, move_a)

        fresh_a_1 = CascadeSimulator(refill_seed=42).simulate(state, move_a)
        fresh_a_2 = CascadeSimulator(refill_seed=42).simulate(state, move_a)

        assert first_a.cleared_count == fresh_a_1.cleared_count
        assert first_a.cascade_depth == fresh_a_1.cascade_depth
        assert first_a.specials_created == fresh_a_1.specials_created

        assert second_a.cleared_count == fresh_a_2.cleared_count
        assert second_a.cascade_depth == fresh_a_2.cascade_depth
        assert second_a.specials_created == fresh_a_2.specials_created

    def test_default_max_depth(self) -> None:
        """Default max_depth is a reasonable finite value (not unbounded)."""
        sim = CascadeSimulator()
        assert sim.max_depth > 0
        assert sim.max_depth <= 100
