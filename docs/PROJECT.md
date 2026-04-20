# ccrush-ai — Product Roadmap

**Last Updated**: 2026-04-20  
**Roadmap Owner**: roadmap agent  
**Strategic Vision**: Build a production-quality Windows Python application that
autonomously plays Candy Crush-style match-3 games, maximizes score by applying
planning algorithms over a fully modelled game state, and adapts to any board
layout, skin, or resolution through a profile-driven calibration system — all
without any game-specific SDK access or memory reading.

---

## Change Log

| Date & Time | Change | Rationale |
|---|---|---|
| 2026-04-20 09:00 | Initial roadmap created | Project inception |

---

## Master Product Objective

> **Enable any Windows user to run a Python bot that reliably plays Candy
> Crush-style games, achieves scores in the top percentile of human players,
> and can be adapted to a new board layout or game skin in under 30 minutes
> through a guided calibration wizard — without writing any code.**

*This section is immutable. Only the user may change it.*

---

## Release v0.1.0 — Foundation & Greedy Bot

**Target Date**: 2026-05-18  
**Strategic Goal**: Demonstrate end-to-end autonomous play on a single known
board layout. Validate the core capture → vision → rules → execute loop.
Establish the testing foundation for all future work.

---

### Epic 1.1: Core Data Models and Rules Engine

**Priority**: P0  
**Status**: Planned

**User Story**:  
As a developer building on this codebase,  
I want a complete, well-tested game-state model and rules engine,  
So that I can reason about board state, moves, and cascades without any
dependency on a live game or screen capture.

**Business Value**:
- All other epics depend on this foundation.
- A correct rules engine means the bot never executes illegal moves.
- Enables offline simulator testing, which reduces live-play risk.
- Measurable success: 100% of unit + property tests pass; rules engine
  divergence rate vs. live game < 2% by end of Phase 3.

**Dependencies**:
- None (EPO — no prior epics required).

**Acceptance Criteria**:
- [ ] `CandyColor`, `SpecialType`, `CellState`, `GameState`, `Move`, `SimResult`,
      `RankedMove` models defined with Pydantic v2.
- [ ] `MatchDetector` correctly identifies 3-, 4-, 5-in-a-row and T/L shapes.
- [ ] `GravityEngine` correctly drops cells after clearing.
- [ ] `CascadeSimulator` iterates until stable with correct depth tracking.
- [ ] `MoveGenerator` produces only legal, adjacent moves that produce at least
      one match.
- [ ] `SyntheticBoard` generates reproducible boards of configurable size.
- [ ] Unit tests with > 80% function coverage.
- [ ] Hypothesis property tests: all generated moves are adjacent and produce a match.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

### Epic 1.2: Screen Capture and Vision Pipeline

**Priority**: P0  
**Status**: Planned

**User Story**:  
As the system running on Windows,  
I want to capture the game window's board region and classify every candy cell
in under 30 ms,  
So that the planning loop has accurate, low-latency game state to work with.

**Business Value**:
- Without reliable vision, no other capability is possible.
- Achieving < 30 ms vision latency keeps the total loop under 500 ms.
- Measurable success: ≥ 95% cell classification accuracy on the calibrated
  profile when tested against 10 saved screenshot fixtures.

**Dependencies**:
- Epic 1.1: `GameState` model must exist to populate.

**Acceptance Criteria**:
- [ ] `WindowManager` finds and focuses the game window by title fragment.
- [ ] `CaptureEngine` delivers a board-ROI NumPy array in < 5 ms using dxcam
      (mss fallback).
- [ ] `BoardDetector` locates the board bounds with confidence > 0.85 on
      calibrated profiles.
- [ ] `GridCalibrator` infers rows, cols, cell size using Sobel peak detection.
- [ ] `CellClassifier` assigns `CandyColor` using LAB nearest-centroid matching.
- [ ] `AnimationDetector` correctly reports animating vs stable in < 2 ms.
- [ ] Vision replay test with ≥ 1 screenshot fixture passes.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

### Epic 1.3: Greedy Bot with Windows Input Execution

**Priority**: P0  
**Status**: Planned

**User Story**:  
As a user who has calibrated the bot,  
I want to run `python -m ccrush play --profile myprofile` and have the bot
automatically play the game by executing drag moves,  
So that I can validate the full pipeline end-to-end on a real game.

**Business Value**:
- Delivers the first user-observable outcome: the bot actually plays.
- Validates coordinate transformation and input reliability.
- Establishes the baseline score that later strategy upgrades must beat.
- Measurable success: bot completes a full game turn sequence without manual
  intervention on a calibrated level.

**Dependencies**:
- Epic 1.1 (rules engine).
- Epic 1.2 (vision pipeline).

**Acceptance Criteria**:
- [ ] `GreedyPolicy` ranks all legal moves using the `EvalFunction`.
- [ ] `CoordTransformer` maps board coordinates to screen coordinates correctly
      on 100% and 125% DPI.
- [ ] `SendInputDriver` executes drags via `SendInput` (ctypes).
- [ ] `MoveVerifier` detects successful vs failed swaps.
- [ ] `--dry-run` mode logs intended moves without executing them.
- [ ] Manual end-to-end test: bot plays 5 moves on a live game without error.
- [ ] `MetricsLogger` records per-move timing with all required fields.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

## Release v0.2.0 — Planning Engine and Calibration Wizard

**Target Date**: 2026-06-15  
**Strategic Goal**: Upgrade the strategy from greedy to beam search, establish
a user-facing calibration workflow so that any layout can be onboarded without
code changes, and add OCR for turn and score tracking.

---

### Epic 2.1: Beam Search and MCTS Policy Engine

**Priority**: P0  
**Status**: Planned

**User Story**:  
As the strategy engine evaluating a move,  
I want to explore multiple candidate move sequences several turns deep,  
So that the bot can plan special candy combos and avoid greedy traps, achieving
a materially higher score than pure greedy.

**Business Value**:
- Simulator benchmarks (to be run post-Phase 2) should demonstrate > 5% mean
  score improvement vs greedy.
- Enables future tuning via configurable `depth` and `beam_width`.
- MCTS provides a testbed for future learned policy integration.

**Dependencies**:
- Epic 1.1 (rules engine for simulation).
- Epic 1.3 (greedy baseline to beat).

**Acceptance Criteria**:
- [ ] `BeamSearchPolicy` implemented with configurable `depth` (1–5) and
      `beam_width` (1–12).
- [ ] `MCTSPolicy` implemented with configurable simulation count and UCB1
      selection.
- [ ] `StrategyDispatcher` selects policy based on `PolicyContext`
      (turns_left, time_budget_ms).
- [ ] Simulator benchmark: `BeamSearch(d=3, k=8)` achieves > 5% higher mean
      score than `GreedyPolicy` over 200 synthetic games.
- [ ] Worst-case per-move latency for `BeamSearch(d=3, k=8)` < 200 ms.
- [ ] `LearnedPolicy` stub compiles and raises `NotImplementedError` with
      clear message.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

### Epic 2.2: Special Candy Detection and Interaction Rules

**Priority**: P1  
**Status**: Planned

**User Story**:  
As the bot evaluating a game state,  
I want to detect and correctly model striped, wrapped, and color-bomb candies,  
So that the strategy engine can deliberately plan combos that the greedy
baseline would miss.

**Business Value**:
- Special candy combos (especially color bomb + wrapped or color bomb + color
  bomb) provide the largest score multipliers in match-3 games.
- Correctly modeling them is the single highest-leverage accuracy improvement
  after basic color classification.

**Dependencies**:
- Epic 1.2 (cell classifier must first identify candy color).
- Epic 2.1 (strategy engine to plan combos).

**Acceptance Criteria**:
- [ ] `SpecialCandyDetector` correctly identifies STRIPED_H, STRIPED_V,
      WRAPPED, COLOR_BOMB via template matching (threshold 0.65).
- [ ] `SpecialCandyRules` table encodes all known interaction outcomes.
- [ ] `CascadeSimulator` applies special interactions during cascades.
- [ ] Unit tests for each special type interaction.
- [ ] False-positive rate in replay fixtures < 5%.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

### Epic 2.3: Calibration Wizard and Profile System

**Priority**: P1  
**Status**: Planned

**User Story**:  
As a user who wants to run the bot on a new Candy Crush level or resolution,  
I want a guided calibration wizard that steps me through board detection,
grid confirmation, candy labeling, and profile saving in under 30 minutes,  
So that I can onboard a new configuration without editing any code or YAML by hand.

**Business Value**:
- Eliminates the biggest adoption barrier: today, users must hand-craft a
  profile YAML, which requires technical knowledge.
- Profile system also enables safe upgrades: calibrate once, reuse across game
  updates until a skin change breaks it.
- Measurable: a non-technical user can complete calibration for a new layout in
  < 30 minutes on first attempt.

**Dependencies**:
- Epic 1.2 (board detection and grid calibration are the calibration backend).

**Acceptance Criteria**:
- [ ] `CalibrationWizard` guides the user through all 8 steps defined in
      `ARCHITECTURE.md § 13.1`.
- [ ] `ProfileManager` selects the active profile using the fingerprint-based
      matching pipeline defined in `ARCHITECTURE.md § 4.8`: board fingerprint
      (primary), grid geometry signature, UI-anchor confidence, window title
      (tie-breaker), resolution (weak hint only).
- [ ] `ProfileManager` raises `NoMatchingProfileError` and prompts the user to
      calibrate when no profile exceeds the match threshold.
- [ ] Profile selection is logged at INFO with all candidate scores.
- [ ] Profile YAML structure matches spec in `ARCHITECTURE.md § 13.2`.
- [ ] `calibrate` CLI subcommand works: `python -m ccrush calibrate`.
- [ ] Snapshot test: loading a saved fixture profile produces identical
      `GridGeometry` on re-detection.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

### Epic 2.4: OCR — Turn Counter and Score Reading

**Priority**: P2  
**Status**: Planned

**User Story**:  
As the strategy engine selecting a policy,  
I want to know how many turns remain and the current score,  
So that I can switch to a high-value, burn-resources policy when turns are
running out rather than behaving identically throughout the whole game.

**Business Value**:
- Turn-aware policy switching is a key differentiator from simple greedy bots.
- Without it, the bot cannot distinguish "save specials for later" from
  "use specials now before I run out of turns".

**Dependencies**:
- Epic 2.3 (profiles store OCR region coordinates).

**Acceptance Criteria**:
- [ ] `OCRReader` extracts an integer from the turns region with > 95% accuracy
      on 5 fixture screenshots per profile.
- [ ] OCR skipped (gracefully, no crash) when region not found in profile.
- [ ] Turn counter feeds `PolicyContext.turns_left`.
- [ ] `StrategyDispatcher` uses `turns_left` to select the correct policy tier.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

## Release v0.3.0 — Robustness, Recovery, and Observability

**Target Date**: 2026-07-13  
**Strategic Goal**: Harden the bot for unattended multi-game sessions. Handle
popups, animations, unexpected game states, and input failures without human
intervention. Provide telemetry to support ongoing tuning.

---

### Epic 3.1: Recovery Manager and Resilient Main Loop

**Priority**: P0  
**Status**: Planned

**User Story**:  
As the bot running unattended for multiple games,  
I want the system to detect and recover from unexpected states (popups, failed
swaps, stuck animations, game over screens),  
So that the session continues without human intervention.

**Business Value**:
- Without recovery, a single unexpected popup ends the entire session.
- Unattended operation is required for the product goal of "autonomous play."

**Dependencies**:
- Epic 1.3 (main loop and executor).
- Epic 2.3 (profile stores popup button templates).

**Acceptance Criteria**:
- [ ] `RecoveryManager` handles: window focus lost, no board found, > 20%
      unknown cells, failed move verification, 3 consecutive no-move states.
- [ ] Popup dismissal via template matching on "OK" / "Continue" overlays.
- [ ] `abort_event` (Ctrl+C or F12) stops the loop cleanly within 1 second.
- [ ] After recovery, board detection and calibration are re-run from scratch.
- [ ] Integration test: inject a "no moves" state; verify recovery is triggered.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

### Epic 3.2: Metrics, Telemetry, and Replay Logging

**Priority**: P1  
**Status**: Planned

**User Story**:  
As a developer tuning the bot's strategy weights,  
I want structured per-move logs including timing, policy scores, and board
confidence metrics,  
So that I can identify which moves are weak and adjust eval weights accordingly.

**Business Value**:
- Tuning eval weights without data is guesswork.
- Structured logs enable A/B comparison across profiles and policy configurations.
- Replay logs (screenshots at each move) allow after-the-fact debugging of
  vision failures.

**Dependencies**:
- Epic 1.3 (main loop already has timing instrumentation skeleton).

**Acceptance Criteria**:
- [ ] Each move produces a JSON log line with all fields from `ARCHITECTURE.md § 4.9`.
- [ ] Optional `--save-frames` mode saves a screenshot before each move for
      replay debugging.
- [ ] `python -m ccrush summary <log_file>` prints per-session stats.
- [ ] Timer overhead < 0.5 ms per loop iteration.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

### Epic 3.3: Objective-Aware Policy and Multi-Level Type Support

**Priority**: P1  
**Status**: Planned

**User Story**:  
As a user playing jelly or blocker-clearing level types,  
I want the bot to automatically recognize the level objective and switch its
evaluation weights accordingly,  
So that it progresses through those levels instead of optimizing purely for
score and ignoring the actual win condition.

**Business Value**:
- Score-only weight preset is nearly useless on jelly and blocker levels.
- Supporting multiple objectives dramatically increases the range of playable
  levels and therefore the product's usefulness.

**Dependencies**:
- Epic 2.2 (jelly layer and blocker detection in vision).
- Epic 2.1 (weighted eval function in `EvalFunction`).

**Acceptance Criteria**:
- [ ] `WEIGHT_PRESETS` implemented for `score`, `jelly`, `blocker`, `ingredient`.
- [ ] `StrategyDispatcher` selects preset based on `PolicyContext.objective`.
- [ ] Automatic objective inference from vision (jelly cell detection, blocker
      fraction) works for at least 2 objective types.
- [ ] Simulator runs on synthetic jelly and blocker board types.

**Status Notes**:
- 2026-04-20: Epic defined at project inception.

---

## Backlog / Future Consideration

### Epic B.1: CNN Candy Classifier

**Priority**: P3  
**Status**: Planned

**User Story**:  
As the vision pipeline classifying a candy cell under a new or animated skin,  
I want a trained CNN to classify cell crops independently of hand-tuned color
clusters,  
So that calibration is more robust and less sensitive to lighting/effects.

**Business Value**:
- Removes the most fragile part of the rule-based classifier.
- Enables "zero-shot" transfer when the game updates its candy skin.
- Only justified once a labeled dataset of > 5,000 cell crops is available.

**Constraints**:
- Not worth implementing until the LAB color-cluster classifier is proven
  insufficient in practice. Ship the simple thing first.

---

### Epic B.2: Learned Policy (DQN / AlphaZero-style)

**Priority**: P3  
**Status**: Planned

**User Story**:  
As the strategy engine on a complex board with many specials,  
I want a policy trained via self-play on the `SyntheticBoard` simulator,  
So that it discovers combo sequences that beam search cannot find within the
time budget.

**Business Value**:
- Highest expected score ceiling of any policy.
- Only justified once beam search is tuned and simulator data is plentiful.
- Requires GPU training infrastructure out of scope for the initial project.

---

### Epic B.3: Web-Based Calibration Overlay

**Priority**: P3  
**Status**: Planned

**User Story**:  
As a non-technical user,  
I want to calibrate the bot through a browser tab that shows my game screen
with click-to-label overlays,  
So that I don't need to use a terminal at all.

---

## Active Release Tracker

**Current Working Release**: v0.1.0

| Plan ID | Title | UAT Status | Committed |
|---|---|---|---|
| — | Epic 1.1: Core Data Models | Not started | ✗ |
| — | Epic 1.2: Vision Pipeline | Not started | ✗ |
| — | Epic 1.3: Greedy Bot | Not started | ✗ |

**Release Status**: 0 of 3 epics started  
**Ready for Release**: No  
**Blocking Items**: All Phase 0 implementation work pending.

### Previous Releases

| Version | Date | Epics Included | Status |
|---|---|---|---|
| — | — | — | — |

---

## Document Lifecycle

See `docs/ARCHITECTURE.md` for Agent Output document conventions.
Orphan sweep: scan `agent-output/*/` directories excluding `closed/` for
documents with terminal Status not yet moved to `closed/`.
