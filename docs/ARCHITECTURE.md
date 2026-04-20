# ccrush-ai — Technical Architecture

**Version**: 0.1.0  
**Last Updated**: 2026-04-20  
**Status**: Initial Design

---

## 1. Executive Summary

`ccrush-ai` is a Windows desktop automation application that autonomously plays
Candy Crush-style match-3 games. It captures the screen in real time, locates
the game board, classifies every candy cell, generates all legal swap moves,
evaluates them with a pluggable strategy engine, and executes the highest-ranked
move — all in under 1.5 seconds per iteration.

The design is **mask-aware rectangular-grid**: it makes no hardcoded assumptions
about cell count, resolution, DPI scale, or skin, and supports irregular boards
through a per-cell playability mask. Richer topologies (portals, split gravity,
non-uniform adjacency) are not modeled at this stage; if required, the state
model would need an explicit adjacency graph. Every board-specific constant is
isolated inside a **calibration profile** (a YAML file) that is created once
per game variant and reused automatically on subsequent runs.

The primary strategy is **beam search with a greedy fallback**. MCTS and a
learned policy are defined only as extension points behind the same `Policy`
protocol and are excluded from MVP scope until beam search performance is
empirically plateaued.

The codebase follows the Python conventions in `.github/instructions/python.instructions.md`:
`from __future__ import annotations` everywhere, Pydantic v2 for all value
objects, typed Protocols for module interfaces, and async I/O where applicable.

---

## 2. Recommended Tech Stack

| Layer | Package | Justification |
|---|---|---|
| Screen capture | **dxcam** (primary), **mss** (fallback) | `dxcam` uses DXGI Desktop Duplication — the fastest Python-accessible path to the framebuffer on Windows (~5 ms, no GDI overhead, no UAC issues). `mss` is cross-platform and used as a fallback when `dxcam` init fails (e.g. RDP session). |
| Image processing | **OpenCV** (`cv2`) | Industry-standard for contour detection, template matching, color space transforms, and edge detection. No equivalent pure-Python alternative at this performance level. |
| Numerical array ops | **NumPy** | All board matrices, image arrays, and histogram operations. Required by OpenCV anyway. |
| Data models | **Pydantic v2** | Already in `pyproject.toml`. Provides validated, serializable state objects with minimal boilerplate. Profile YAMLs are loaded as Pydantic settings. |
| Windows input | **ctypes** (SendInput) + **pywin32** | `ctypes` `SendInput` is the most reliable path for injecting mouse events in games — it bypasses some hooks that `pyautogui` or `pynput` can trigger. `pywin32` covers window management (`win32gui`, `win32api`). |
| OCR | **pytesseract** + **Tesseract 5** | Only used for the turn counter and score region. Digit-only mode is fast (~10 ms) and accurate on clean UI text after thresholding. |
| Settings / profiles | **pydantic-settings** | Profile YAML ↔ Pydantic model with validation. Already in `pyproject.toml`. |
| Logging / metrics | **loguru** | Structured, human-readable logs with no-config setup. Beats `logging` for observability. |
| Calibration TUI | **rich** | Interactive overlay-style display for the calibration wizard without a full GUI framework. |
| Testing | **pytest** + **hypothesis** | pytest already in dev deps. `hypothesis` adds property-based testing for move legality. |
| Optional ML | **PyTorch** (lazy import) | Only imported if a trained model file exists. Used for CNN candy classifier or DQN policy. Not a hard dependency. |

**Intentionally excluded:**
- `pyautogui` — too slow for full-screen search; uses GDI screenshot path.
- `Pillow` — OpenCV covers all image I/O needs at higher performance.
- Any game SDK or memory-reading library — we treat the game as a black box.

---

## 3. High-Level Architecture Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Main Loop (async)                            │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
          ┌─────────────────────────▼──────────────────────────┐
          │                   Session Manager                   │
          │  (window focus, loop control, abort signal handler) │
          └──────┬──────────────────────────────┬──────────────┘
                 │                              │
    ┌────────────▼───────────┐    ┌─────────────▼────────────┐
    │    Capture Engine      │    │   Recovery / Resync Mgr  │
    │  (dxcam / mss ROI)     │    │  (detects stale state,   │
    │  < 5 ms per frame      │    │   popups, game-over)     │
    └────────────┬───────────┘    └─────────────┬────────────┘
                 │                              │
    ┌────────────▼───────────────────────────────▼────────────┐
    │                     Vision Pipeline                      │
    │  BoardDetector → GridCalibrator → CellClassifier         │
    │  SpecialCandyDetector → AnimationDetector → OCR          │
    └────────────────────────────┬─────────────────────────────┘
                                 │  GameState
    ┌────────────────────────────▼─────────────────────────────┐
    │                     Rules Engine                          │
    │  MoveGenerator → MatchDetector → GravityEngine           │
    │  CascadeSimulator → SpecialCandyRules                    │
    └────────────────────────────┬─────────────────────────────┘
                                 │  [Move, SimResult]
    ┌────────────────────────────▼─────────────────────────────┐
    │                   Strategy Engine                         │
    │  StrategyDispatcher                                       │
    │    ├── GreedyPolicy                                       │
    │    ├── BeamSearchPolicy  ◄── default hybrid              │
    │    ├── MCTSPolicy                                         │
    │    └── LearnedPolicy (stub)                               │
    └────────────────────────────┬─────────────────────────────┘
                                 │  BestMove
    ┌────────────────────────────▼─────────────────────────────┐
    │                  Action Executor                          │
    │  CoordTransformer → SendInputDriver → MoveVerifier        │
    └────────────────────────────┬─────────────────────────────┘
                                 │
    ┌────────────────────────────▼─────────────────────────────┐
    │              Metrics / Telemetry Logger                   │
    │  (loguru structured JSON, timing, move history)           │
    └──────────────────────────────────────────────────────────┘

Supporting subsystems (not in hot path):
  CalibrationWizard ──► ProfileManager ──► profiles/<name>.yaml
  TestHarness / SyntheticBoard ──► offline strategy evaluation
```

---

## 4. Detailed Module Design

### 4.1 `capture/` — Screen Capture

**`CaptureEngine`**
- **Responsibility**: Deliver a NumPy `uint8` BGR array of the game window's
  client region as fast as possible.
- **Inputs**: Window rect `(x, y, w, h)` from `SessionManager`.
- **Outputs**: `np.ndarray` (H×W×3 BGR).
- **Implementation**:
  - On init, try `dxcam.create(region=...)`. If unavailable, fall back to `mss`.
  - Expose `capture() -> np.ndarray` that grabs the latest frame.
  - Cache last frame internally; expose `frame_diff(prev, curr) -> float` for
    animation detection.
- **Failure modes**: DXGI unavailable (RDP, VM) → `mss` fallback. Window
  minimized → raises `WindowNotVisibleError`.

**`WindowManager`**
- **Responsibility**: Find, focus, and track the game window.
- **Inputs**: Process name glob or window title pattern (from profile).
- **Outputs**: HWND, client rect `(left, top, right, bottom)`.
- **Implementation**:
  - `win32gui.EnumWindows` with title substring match.
  - `win32gui.SetForegroundWindow` to focus (with `win32gui.ShowWindow` if
    minimized).
  - Monitors window rect changes (resize/move) and notifies `CaptureEngine`.
- **Failure modes**: Window not found → `GameWindowNotFoundError`.
  Window moved mid-session → rect invalidated, triggers recapture + grid
  recalibration.

---

### 4.2 `vision/` — Image Recognition Pipeline

**`BoardDetector`**
- **Responsibility**: Locate the board bounding box within the captured frame.
- **Inputs**: Full frame `np.ndarray`.
- **Outputs**: `BoardBounds(x, y, w, h, confidence: float)`.
- **Approach 1 (preferred, rule-based)**:
  1. Convert to LAB color space.
  2. Apply Gaussian blur, Canny edge detection.
  3. Find rectangular contours with area > min_board_fraction of frame.
  4. Score by squareness (aspect ratio close to known board ratio) and grid-
     like internal structure.
  5. Cache result; re-run only if window rect changes or recovery is triggered.
- **Approach 2 (fallback)**: Template match on known UI chrome corners (profile
  stores corner templates). More robust if the board background blends into the
  screen.
- **Failure modes**: No high-confidence region found → raise
  `BoardNotFoundError`, trigger recovery loop.

**`GridCalibrator`**
- **Responsibility**: Infer row count, column count, cell size, and origin offset
  from the board crop.
- **Inputs**: Board crop `np.ndarray`, hint from profile (optional).
- **Outputs**: `GridGeometry(rows, cols, cell_w, cell_h, offset_x, offset_y)`.
- **Algorithm**:
  1. Apply horizontal Sobel → sum columns → find peaks (column separators).
  2. Apply vertical Sobel → sum rows → find peaks (row separators).
  3. Check peak spacing consistency (coefficient of variation < 0.1).
  4. Infer cell size from median peak spacing.
  5. Cross-validate: total peaks * cell_size ≈ board dimension.
- **Caching**: Geometry is cached per-session. Re-run if `BoardDetector` rect
  changes by > 5 px (user scrolled or resized).
- **Failure modes**: Irregular peak spacing → fall back to profile hint or ask
  user to recalibrate.

**`CellClassifier`**
- **Responsibility**: For each cell, return `(CandyColor, confidence)`.
- **Inputs**: Board crop, `GridGeometry`, color clusters from profile.
- **Outputs**: `list[list[ColorResult]]`.
- **Algorithm (rule-based)**:
  1. For each cell center, extract inner ROI (60% of cell_w × cell_h).
  2. Convert to LAB.
  3. Compute mean LAB value.
  4. Nearest-centroid match against profile's `color_clusters`.
  5. Confidence = 1 - (distance / max_cluster_radius).
- **Algorithm (optional CNN)**:
  - Batch all cell crops → 32×32 resize → forward pass through a small
    MobileNetV3-style head → softmax over candy classes.
  - ~3 ms for a 9×9 board on modern GPU; ~15 ms on CPU.
  - When to use: when color-cluster approach confidence < 0.7 for > 20% of
    cells (e.g. heavily-animated skins).
- **Failure modes**: Confidence < threshold → mark cell `CandyColor.UNKNOWN`,
  flag to `RecoveryManager`.

**`SpecialCandyDetector`**
- **Responsibility**: For each cell already classified as a candy, detect whether
  it carries a special overlay (striped, wrapped, color bomb).
- **Inputs**: Cell crop, `SpecialType` templates from profile.
- **Outputs**: `SpecialType` enum per cell.
- **Algorithm**:
  1. For each template (striped_h, striped_v, wrapped, color_bomb), run
     `cv2.matchTemplate(cell_crop, template, TM_CCOEFF_NORMED)`.
  2. If max score > threshold (default 0.65) → assign that `SpecialType`.
  3. If multiple match → take highest score.
- **Failure modes**: No template library in profile → all cells classified as
  `SpecialType.NONE` (safe degradation).

**`AnimationDetector`**
- **Responsibility**: Return `True` if the board is currently animating (candies
  falling, clearing effects, etc.).
- **Inputs**: Two successive frames.
- **Outputs**: `bool`.
- **Algorithm**: Compute `np.mean(np.abs(frame2.astype(int) - frame1.astype(int)))`
  restricted to the board region. If > `animation_threshold` (profile default
  8.0) → animating.
- **Caching**: Reuses last frame from `CaptureEngine`.

---

### 4.3 `state/` — Game State Models

See **Section 6** for full Pydantic definitions.

**`StateBuilder`**
- Combines outputs of `CellClassifier`, `SpecialCandyDetector`, OCR results, and
  `PlayableMaskDetector` into a single `GameState` object.
- Emits a `confidence` score = mean classification confidence across all playable
  cells.

**`PlayableMaskDetector`**
- Scans each candidate cell position for "empty / non-playable" patterns.
- Rule: cells with very low color saturation (S < 15 in HSV) and low entropy
  (std of pixel values < 10) are marked `playable=False`.
- Profile can also provide a static mask that overrides this.

---

### 4.4 `rules/` — Game Rules Engine

**`MoveGenerator`**
- Enumerates all adjacent (horizontal + vertical) swaps between two playable
  cells and returns only those that produce at least one 3-match after the swap.
- See pseudocode in **Section 7**.

**`MatchDetector`**
- Scans a board matrix for runs of 3+ same-color cells in any row or column.
- Returns a `MatchSet`: list of matched cell positions, `SpecialType` created
  (if applicable), and score contribution.
- Match-length → special: 3=none, 4=striped, 5=color_bomb, L/T=wrapped.

**`GravityEngine`**
- After cells are cleared, shifts non-empty cells downward (or per-direction if
  the profile specifies a different gravity vector).
- New cells entering from top are assigned `CandyColor.UNKNOWN` (stochastic
  fill).

**`CascadeSimulator`**
- Iteratively applies `MatchDetector` → `GravityEngine` until no new matches
  form.
- Returns `CascadeResult(depth, total_cleared, specials_triggered,
  score_estimate)`.

**`SpecialCandyRules`**
- Encodes known special interactions as a lookup table + fallback heuristics:
  - Striped + Striped → cross (+/×) clear.
  - Striped + Wrapped → 3 striped explosions.
  - Wrapped + Wrapped → larger explosion.
  - Color bomb + Candy → clears all candies of that color.
  - Color bomb + Color bomb → clears entire board.
- **Assumption**: These interactions are approximated; exact Candy Crush SA
  behavior is proprietary. The rule table is profile-configurable. Empirical
  corrections are logged during live play.

---

### 4.5 `strategy/` — Strategy and Policy Engine

**`StrategyDispatcher`**
- Chooses one of four policies based on `PolicyContext` (turns left, board
  mobility, time budget).
- Exposes `select_move(state: GameState, moves: list[Move]) -> RankedMove`.

**`GreedyPolicy`**  
**`BeamSearchPolicy`**  
**`MCTSPolicy`**  
**`LearnedPolicy`**  
See **Section 8** for full per-policy breakdown.

---

### 4.6 `executor/` — Action Execution

**`CoordTransformer`**
- Maps `(row, col)` board coordinates → screen pixel coordinates.
- Formula:
  ```
  screen_x = window_left + board_x + offset_x + col * cell_w + cell_w / 2
  screen_y = window_top  + board_y + offset_y + row * cell_h + cell_h / 2
  ```
- Accounts for DPI scaling via `win32api.GetDpiForSystem()` ratio.

**`SendInputDriver`**
- Performs mouse drag via Windows `SendInput` API (ctypes).
- Sequence: `MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE` to source →
  `MOUSEEVENTF_LEFTDOWN` → interpolated moves (5 steps) →
  `MOUSEEVENTF_LEFTUP` at destination.
- Sleep between steps configurable (default 30 ms step).
- Uses absolute coordinates in the range [0, 65535].

**`MoveVerifier`**
- After `wait_for_animation()`, re-classifies the two swapped cells.
- If the expected candy types have moved → success.
- If unchanged → swap was invalid or rejected by the game → increment
  `failed_move_count`, trigger `RecoveryManager` if count > 2.

---

### 4.7 `recovery/` — Failure Recovery

**`RecoveryManager`**
- Triggered by: `BoardNotFoundError`, high `unknown_cell_count`, failed move
  verification, unexpected popup.
- Actions (in order):
  1. Re-focus window.
  2. Wait 1 second, recapture.
  3. Re-run full board detection.
  4. If still failing, dismiss popups (look for known "OK"/"Continue" button
     templates, click centroid).
  5. If still failing after 3 attempts → pause bot, alert user via console.
- Uses `RobotState.RECOVERY` flag to prevent the main loop from executing moves
  during recovery.

---

### 4.8 `calibration/` — Calibration and Profiles

**`CalibrationWizard`**
- Rich-TUI guided flow (see **Section 13**).

**`ProfileManager`**
- Loads/saves `CalibrationProfile` (Pydantic model) from `profiles/<name>.yaml`.
- **Profile selection pipeline** (evaluated in order; first match above threshold wins):
  1. `board_fingerprint` match — SHA-256 of binarised board-detection crop at
     a fixed 128×128 resolution. Profiles store a set of up to 5 reference
     fingerprints. Cosine similarity against stored fingerprints; threshold 0.90.
  2. `grid_geometry_signature` match — (rows, cols, cell_w±2, cell_h±2) tuple
     compared to each profile's stored geometry. Exact match on rows/cols; fuzzy
     on cell size.
  3. `ui_anchor_confidence` — if the profile has corner templates, run
     `cv2.matchTemplate` and require score > 0.80.
  4. `window_title_fragment` substring match — tie-breaker only.
  5. `resolution` — weak hint; never sole criterion.
- If no profile scores above threshold, `ProfileManager` raises
  `NoMatchingProfileError` and the CLI prompts the user to calibrate.
- All board-specific constants (grid size, cell size, color clusters, templates,
  OCR regions, special weights) live in the profile.
- Profile selection is logged at INFO level with all candidate scores for
  observability.

---

### 4.9 `telemetry/` — Metrics and Logging

**`MetricsLogger`**
- Wraps `loguru` with structured JSON output.
- Timing via `time.perf_counter_ns()`.
- Exposes `summary()` for end-of-session statistics.
- Two telemetry tiers controlled by `--verbose` flag:

**Normal telemetry** (always on):
```json
{
  "move_id": 42, "profile_id": "myprofile", "policy": "beam",
  "move": {"r1": 4, "c1": 3, "r2": 4, "c2": 4},
  "loop_ms": 612, "capture_ms": 4, "vision_ms": 22,
  "strategy_ms": 187, "execute_ms": 310,
  "state_confidence": 0.94, "cleared_count": 9, "cascade_depth": 2,
  "eval_score": 72.3, "recovery_reason": null
}
```

**Debug telemetry** (`--verbose`, not for production runs):
- Per-cell confidence maps (81-element array for a 9×9 board).
- Template-match score per `SpecialType` per cell.
- Top-5 ranked move scores from the strategy engine.
- Simulator rollout depth trace.
- Classification overlay images (saved to `debug_frames/` if `--save-frames`).

**Profile selection telemetry** (logged at INFO on startup):
```
[profile] Candidates: myprofile(fp=0.96, geo=exact, anchor=0.89, title=yes) | default(fp=0.41)
[profile] Selected: myprofile
```

**Move-outcome telemetry** (live-vs-sim divergence tracking):
```json
{
  "move_id": 42,
  "predicted_cleared": 9, "observed_cleared": 12,
  "predicted_specials": ["STRIPED_H"], "observed_specials": ["STRIPED_H", "WRAPPED"],
  "divergence": true
}
```
This stream feeds the long-term divergence rate metric that characterises how
accurately `CascadeSimulator` approximates live game behaviour.

---

### 4.10 `simulator/` — Synthetic Board & Test Harness

**`SyntheticBoard`**
- Generates random boards of configurable size with optional holes and
  pre-placed specials.
- Supports deterministic seed for reproducible tests.
- After each AI move, applies the same `CascadeSimulator` + `GravityEngine`
  code. Note: the simulator is a **policy-comparison environment**, not a
  verified model of the live game. Sources of live-vs-sim divergence include:
  imperfect cell classification, stochastic incoming fills, proprietary
  special-candy semantics, and execution latency. Divergence must be measured
  empirically via the move-outcome telemetry described in §4.9.
- Enables offline policy comparison: run 1000 games, compare mean scores.
- See §4.9 for the `predicted_vs_observed` telemetry stream that quantifies
  live-vs-sim divergence over time.

---

## 5. Project Folder Structure

```
ccrush-ai/
├── pyproject.toml
├── README.md
├── docs/
│   ├── PROJECT.md           # Product roadmap
│   └── ARCHITECTURE.md      # This document
├── profiles/
│   └── default.yaml         # Starter calibration profile
├── src/
│   └── ccrush/
│       ├── __init__.py
│       ├── __main__.py      # Entry point: python -m ccrush [play|calibrate|test]
│       ├── settings.py      # App-level settings (pydantic-settings)
│       ├── capture/
│       │   ├── __init__.py
│       │   ├── engine.py    # CaptureEngine
│       │   └── window.py    # WindowManager
│       ├── vision/
│       │   ├── __init__.py
│       │   ├── board.py     # BoardDetector
│       │   ├── grid.py      # GridCalibrator
│       │   ├── classify.py  # CellClassifier
│       │   ├── special.py   # SpecialCandyDetector
│       │   └── motion.py    # AnimationDetector
│       ├── state/
│       │   ├── __init__.py
│       │   ├── models.py    # All Pydantic models
│       │   └── builder.py   # StateBuilder, PlayableMaskDetector
│       ├── rules/
│       │   ├── __init__.py
│       │   ├── moves.py     # MoveGenerator
│       │   ├── match.py     # MatchDetector
│       │   ├── gravity.py   # GravityEngine
│       │   ├── cascade.py   # CascadeSimulator
│       │   └── specials.py  # SpecialCandyRules
│       ├── strategy/
│       │   ├── __init__.py
│       │   ├── base.py      # Policy Protocol + RankedMove
│       │   ├── greedy.py    # GreedyPolicy
│       │   ├── beam.py      # BeamSearchPolicy
│       │   ├── mcts.py      # MCTSPolicy
│       │   ├── learned.py   # LearnedPolicy (stub)
│       │   ├── eval.py      # EvalFunction + weights
│       │   └── dispatcher.py # StrategyDispatcher
│       ├── executor/
│       │   ├── __init__.py
│       │   ├── transform.py # CoordTransformer
│       │   ├── input.py     # SendInputDriver
│       │   └── verify.py    # MoveVerifier
│       ├── recovery/
│       │   ├── __init__.py
│       │   └── manager.py   # RecoveryManager
│       ├── calibration/
│       │   ├── __init__.py
│       │   ├── wizard.py    # CalibrationWizard
│       │   ├── profile.py   # CalibrationProfile Pydantic model
│       │   └── manager.py   # ProfileManager
│       ├── telemetry/
│       │   ├── __init__.py
│       │   └── logger.py    # MetricsLogger
│       └── simulator/
│           ├── __init__.py
│           └── board.py     # SyntheticBoard
└── tests/
    ├── unit/
    │   ├── test_match_detector.py
    │   ├── test_gravity.py
    │   ├── test_move_generator.py
    │   ├── test_cascade_simulator.py
    │   └── test_eval_function.py
    ├── property/
    │   └── test_move_legality.py   # hypothesis
    ├── vision/
    │   ├── fixtures/               # saved screenshots + expected states
    │   └── test_classifier_replay.py
    ├── integration/
    │   └── test_full_pipeline_dryrun.py
    └── simulator/
        ├── test_synthetic_board.py
        └── benchmark_policies.py
```

---

## 6. Data Model Definitions

```python
# src/ccrush/state/models.py
from __future__ import annotations

from enum import IntEnum
from typing import Protocol

import numpy as np
from pydantic import BaseModel, Field


class CandyColor(IntEnum):
    UNKNOWN = 0
    RED     = 1
    ORANGE  = 2
    YELLOW  = 3
    GREEN   = 4
    BLUE    = 5
    PURPLE  = 6


class SpecialType(IntEnum):
    NONE       = 0  # plain candy
    STRIPED_H  = 1  # horizontal stripe
    STRIPED_V  = 2  # vertical stripe
    WRAPPED    = 3  # wrapped / bomb
    COLOR_BOMB = 4  # chocolate ball / all-color
    JELLY      = 5  # cell has jelly underneath (objective layer)
    BLOCKER    = 6  # licorice, toffee, marmalade, etc.
    EMPTY      = 7  # structural hole — never playable
    UNKNOWN    = 8  # classification failed


class CellState(BaseModel):
    row: int
    col: int
    playable: bool
    color: CandyColor = CandyColor.UNKNOWN
    special: SpecialType = SpecialType.NONE
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    locked: bool = False          # frosting, marmalade
    lock_layers: int = 0          # how many hits to unlock
    blocker_hp: int = 0           # HP remaining for breakable blockers


class GridGeometry(BaseModel):
    rows: int
    cols: int
    cell_w: float
    cell_h: float
    offset_x: float              # board origin within the window frame
    offset_y: float


class BoardBounds(BaseModel):
    x: int
    y: int
    w: int
    h: int
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GameState(BaseModel):
    cells: list[list[CellState]]  # [row][col]
    geometry: GridGeometry
    bounds: BoardBounds
    turn: int | None = None       # None if OCR unavailable
    score: int | None = None
    max_turns: int | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    frame_id: int = 0

    def cell(self, r: int, c: int) -> CellState:
        return self.cells[r][c]

    def playable_mask(self) -> list[list[bool]]:
        return [[cell.playable for cell in row] for row in self.cells]

    def playable_count(self) -> int:
        return sum(cell.playable for row in self.cells for cell in row)


class Move(BaseModel):
    r1: int
    c1: int
    r2: int
    c2: int

    def is_adjacent(self) -> bool:
        dr = abs(self.r2 - self.r1)
        dc = abs(self.c2 - self.c1)
        return (dr == 1 and dc == 0) or (dr == 0 and dc == 1)


class SimResult(BaseModel):
    move: Move
    cleared_count: int = 0
    specials_created: list[SpecialType] = Field(default_factory=list)
    cascade_depth: int = 0
    score_estimate: float = 0.0
    blocker_progress: int = 0    # blocker HP reduced
    jelly_cleared: int = 0


class RankedMove(BaseModel):
    move: Move
    sim_result: SimResult
    policy_score: float
    policy_name: str
    rank: int = 0


class PolicyContext(BaseModel):
    turns_left: int | None
    board_playable_fraction: float
    unknown_cell_fraction: float
    time_budget_ms: float = 800.0
    objective: str = "score"     # "score" | "jelly" | "blocker" | "ingredient"
```

---

## 7. Vision Pipeline — End-to-End

```
RAW FRAME (dxcam BGR numpy array)
       │
       ▼
 [AnimationDetector]
       │ still? → proceed
       │ moving? → sleep 50ms, loop back
       ▼
 [BoardDetector]
       │ BoardBounds (x,y,w,h)   ← cached after first detection
       ▼
 board_crop = frame[y:y+h, x:x+w]
       │
       ▼
 [GridCalibrator]
       │ GridGeometry             ← cached per session
       ▼
 [PlayableMaskDetector]
       │ playable_mask            ← re-run only on profile change
       ▼
 [CellClassifier]   (batch all ROIs)
       │ color, confidence per cell
       ▼
 [SpecialCandyDetector]  (template match within each colored cell ROI)
       │ SpecialType per cell
       ▼
 [OCR]  (pytesseract on cached turn/score regions)
       │ turn: int | None, score: int | None
       ▼
 [StateBuilder]
       │
       ▼
 GameState
```

### Step Detail: Board Detection

```python
def detect_board(frame: np.ndarray, profile: CalibrationProfile) -> BoardBounds:
    # 1. Try template-match on UI chrome corner (fast path, ~2ms)
    if profile.corner_templates:
        result = cv2.matchTemplate(frame, profile.corner_templates[0], cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        if score > 0.80:
            x, y = loc
            return BoardBounds(x=x, y=y, w=profile.board_w, h=profile.board_h, confidence=score)

    # 2. Edge + contour fallback (~8ms)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = [
        cv2.boundingRect(c) for c in contours
        if cv2.contourArea(c) > frame.shape[0] * frame.shape[1] * 0.05
    ]
    # Score by squareness, size, grid structure
    best = max(candidates, key=lambda r: score_board_candidate(frame, r))
    return BoardBounds(*best, confidence=compute_confidence(frame, best))
```

### Step Detail: Grid Geometry

```python
def infer_grid(crop: np.ndarray, hint: GridGeometry | None) -> GridGeometry:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Column separators: horizontal Sobel, sum rows
    sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    col_profile = np.sum(np.abs(sobel_x), axis=0)
    col_peaks = find_peaks(col_profile, min_distance=10, min_height=0.3*col_profile.max())

    # Row separators: vertical Sobel, sum cols
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    row_profile = np.sum(np.abs(sobel_y), axis=1)
    row_peaks = find_peaks(row_profile, min_distance=10, min_height=0.3*row_profile.max())

    cell_w = median_spacing(col_peaks)
    cell_h = median_spacing(row_peaks)
    cols   = len(col_peaks) - 1   # separators = cols+1
    rows   = len(row_peaks) - 1

    return GridGeometry(rows=rows, cols=cols, cell_w=cell_w, cell_h=cell_h,
                        offset_x=col_peaks[0], offset_y=row_peaks[0])
```

### Dealing with Animations and Particle Effects

- **Frame diff threshold**: If `mean_abs_diff(board_region) > 8.0` → board
  is animating. Poll every 50 ms until stable (max 5 s).
- **ROI shrink**: Reduce cell ROI to inner 50% during classification to avoid
  glowing edges contaminating color reads.
- **Multi-frame consensus**: If `confidence < 0.75` on first frame, capture a
  second frame 100 ms later and take majority vote between the two
  classifications per cell.
- **Cache between frames**: `BoardBounds` and `GridGeometry` are cached.
  Re-running them every frame is wasted CPU; only re-run if frame diff in the
  non-board area exceeds threshold (implies window move/resize).

### Confidence Scoring and Fallback

| Condition | Action |
|---|---|
| Cell confidence < 0.6 | Mark `UNKNOWN`, exclude from move gen |
| > 20% cells UNKNOWN | Skip move, wait + retry |
| No legal moves generated | Trigger `RecoveryManager` (board may have locked up) |
| Board confidence < 0.7 | Re-run `BoardDetector` |
| OCR fails 3 frames in a row | Set `turn = None`, continue with `max_turns` estimate |

---

## 8. Strategy Engine — Policy Comparison

### 8.1 Policy Protocol

```python
# src/ccrush/strategy/base.py
from __future__ import annotations

from typing import Protocol

from ccrush.state.models import GameState, Move, RankedMove, PolicyContext


class Policy(Protocol):
    def rank_moves(
        self, state: GameState, moves: list[Move], ctx: PolicyContext
    ) -> list[RankedMove]:
        ...
```

### 8.2 Policy Comparison Table

| Attribute | Greedy | Beam Search | MCTS | Learned Policy |
|---|---|---|---|---|
| **Representation** | Single-step simulation | Tree of depth d, width k | Monte Carlo game tree | CNN policy+value heads |
| **Compute cost** | O(M) ~1 ms | O(M × k^d) ~50–200 ms | O(simulations) ~300–800 ms | O(1) forward pass ~3–15 ms |
| **Expected strength** | Low–medium | Medium–high | High | Very high (if trained) |
| **Stochastic fill** | Ignored | Sampled or expected | Rollout simulates randomly | Learned implicitly |
| **Special combos** | Accidental | Partially planned | Explored via simulation | Learned if in training data |
| **Weaknesses** | Greedy traps, no lookahead | Exponential blowup at depth > 5 | Needs many simulations to converge | Requires large training corpus |
| **When to use** | Very short time budget (< 50 ms), fallback | Default for 5–20 turns | Long time budget, complex board | When a trained model is available |

### 8.3 Greedy Policy — Pseudocode

```python
def rank_moves(state, moves, ctx) -> list[RankedMove]:
    results = []
    for move in moves:
        sim = simulate_single_move(state, move)
        score = eval_function(state, sim, ctx)
        results.append(RankedMove(move=move, sim_result=sim, policy_score=score,
                                   policy_name="greedy"))
    return sorted(results, key=lambda r: r.policy_score, reverse=True)
```

### 8.4 Beam Search Policy — Pseudocode

```python
def rank_moves(state, moves, ctx) -> list[RankedMove]:
    depth   = min(ctx.turns_left or 10, config.max_depth)   # e.g. 3
    beam_k  = config.beam_width                              # e.g. 8
    deadline = time.monotonic() + ctx.time_budget_ms / 1000

    # Level 0: score initial moves
    beam = [(eval_function(state, sim_single(state, m), ctx), state, m_root=m, sim)
            for m in moves]
    beam = sorted(beam)[-beam_k:]

    for d in range(1, depth):
        if time.monotonic() > deadline:
            break
        next_beam = []
        for score, s, m_root, sim in beam:
            s2 = apply_sim(s, sim)
            child_moves = generate_legal_moves(s2)
            for cm in child_moves:
                cs = sim_single(s2, cm)
                child_score = score + discount^d * eval_function(s2, cs, ctx)
                next_beam.append((child_score, s2, m_root, cs))
        beam = sorted(next_beam)[-beam_k:]

    # Aggregate by root move
    move_scores = defaultdict(float)
    for score, _, m_root, _ in beam:
        move_scores[m_root] = max(move_scores[m_root], score)

    return [RankedMove(move=m, ..., policy_score=s, policy_name="beam")
            for m, s in sorted(move_scores.items(), key=lambda x: x[1], reverse=True)]
```

### 8.5 MCTS Policy — Pseudocode

```python
def rank_moves(state, moves, ctx) -> list[RankedMove]:
    root = MCTSNode(state=state, move=None, parent=None)
    for m in moves:
        root.add_child(m)

    deadline = time.monotonic() + ctx.time_budget_ms / 1000
    while time.monotonic() < deadline:
        node = select(root)          # UCB1 traversal
        child = expand(node)         # pick untried move
        reward = rollout(child)      # greedy/random playout
        backprop(child, reward)

    best = max(root.children, key=lambda n: n.visit_count)
    return root.children_ranked()
```

### 8.6 Recommended Default Hybrid Policy

```
StrategyDispatcher selects policy based on PolicyContext:

  turns_left <= 3    → BeamSearch(depth=2, beam=12)   "burn resources fast"
  turns_left <= 8    → BeamSearch(depth=3, beam=8)
  turns_left <= 20   → BeamSearch(depth=3, beam=6)    ← DEFAULT
  turns_left > 20    → BeamSearch(depth=4, beam=6)    "plan deeper, turns to burn"
  time_budget < 80ms → Greedy                         "fallback"
```

Rationale: BeamSearch is the operative strategy for all production use. The
Greedy fallback applies only when the time budget is too tight for even a
shallow beam (e.g. during recovery).

**MCTS and LearnedPolicy** are not part of the production dispatch table at
this stage. They exist behind the `Policy` protocol as opt-in extension points
activated by a `--policy mcts` CLI flag during benchmarking. They will be
promoted to the dispatch table only after simulator benchmarks confirm > 10%
mean score improvement over beam search with comparable latency.

---

## 9. Scoring / Evaluation Function

### 9.1 Formula

```
policy_score =
    w_clear    * immediate_clear_count
  + w_cascade  * cascade_potential_estimate
  + w_special  * specials_created_value
  + w_combo    * special_combo_bonus
  + w_lower    * lower_board_bonus
  + w_blocker  * blocker_progress
  + w_obj      * objective_progress
  + w_entropy  * board_entropy_delta
  - w_dead     * dead_board_risk
```

### 9.2 Term Definitions

| Term | Computation | Configurable? |
|---|---|---|
| `immediate_clear_count` | `sim_result.cleared_count` | No (ground truth) |
| `cascade_potential_estimate` | Blocked matches reachable in 1 hop from cleared region; estimate via neighbor scan | Yes (depth) |
| `specials_created_value` | Lookup by `SpecialType`: color_bomb=50, wrapped=30, striped=15, none=0 | Yes |
| `special_combo_bonus` | When two specials adjoin after move: lookup table (e.g. cb+cb=500, cb+wrapped=200) | Yes |
| `lower_board_bonus` | Sum of (rows-1-row) for each cleared cell / max_row | Yes |
| `blocker_progress` | `sim_result.blocker_progress` | Yes |
| `objective_progress` | Level-type dependent; e.g. jelly cleared count for jelly level | Yes |
| `board_entropy_delta` | After cascade, measure color distribution entropy change. High entropy → more future move diversity | Yes |
| `dead_board_risk` | legal_move_count_after / max_possible. Low count → high risk | Yes |

### 9.3 Default Weights

```yaml
# profiles/default.yaml (weights section)
eval_weights:
  w_clear:    10.0
  w_cascade:  6.0
  w_special:  1.0   # multiplied by specials_created_value lookup
  w_combo:    1.0   # multiplied by combo lookup
  w_lower:    4.0
  w_blocker:  8.0
  w_obj:      12.0
  w_entropy:  2.0
  w_dead:     15.0
```

All weights are profile-configurable. Running A/B tests on the simulator
(e.g. 500-game comparison) is the recommended tuning approach.

---

## 10. Adaptation Logic for Board Variations and Max Turns

### 10.1 Policy Switching

```python
def build_policy_context(state: GameState, config: AppConfig) -> PolicyContext:
    turns_left = state.turn  # from OCR or None
    if turns_left is None:
        turns_left = config.default_turns_fallback     # e.g. 15

    playable_fraction = state.playable_count() / (state.geometry.rows * state.geometry.cols)
    unknown_fraction  = unknown_cell_count(state) / max(state.playable_count(), 1)

    return PolicyContext(
        turns_left=turns_left,
        board_playable_fraction=playable_fraction,
        unknown_cell_fraction=unknown_fraction,
        time_budget_ms=config.time_budget_ms,
        objective=config.objective,
    )
```

### 10.2 Objective-Specific Weight Override

```python
WEIGHT_PRESETS = {
    "score":       EvalWeights(w_lower=4.0, w_obj=0.0, w_entropy=2.0),
    "jelly":       EvalWeights(w_lower=1.0, w_obj=20.0, w_entropy=1.0),
    "blocker":     EvalWeights(w_lower=1.0, w_blocker=20.0, w_obj=5.0),
    "ingredient":  EvalWeights(w_lower=12.0, w_obj=8.0),  # push items down
}
```

### 10.3 Board-Type Adaptations

| Scenario | Policy Adjustment |
|---|---|
| Few turns (≤ 5) | BeamSearch, maximize immediate score; raise `w_special` (combos now) |
| Many turns (> 25) | Deeper beam (d=4); raise `w_entropy` for future mobility |
| Open board (playable > 80%) | Standard weights |
| Constrained / irregular (playable < 50%) | Raise `w_blocker` + `w_dead`; avoid moves that isolate regions |
| Blockers present | `WEIGHT_PRESETS["blocker"]` until cleared |
| Score-only level | `WEIGHT_PRESETS["score"]` |
| Jelly level | `WEIGHT_PRESETS["jelly"]` |

### 10.4 Dynamic Objective Detection

If the profile does not specify an objective, the bot attempts to infer it from
the vision pipeline:
1. If a "jelly" cell layer is detected (underlying colored cell) → `"jelly"`.
2. If blockers occupy > 15% of playable cells → `"blocker"`.
3. Otherwise → `"score"`.

---

## 11. Performance Plan

### 11.1 Timing Targets

| Operation | Target | Notes |
|---|---|---|
| Frame capture (dxcam) | < 5 ms | DXGI, region-only |
| Animation check | < 2 ms | Frame diff on board ROI only |
| Board detection | < 3 ms | Cached; re-run only on window change |
| Grid calibration | < 3 ms | Cached |
| Cell classification (all cells) | < 15 ms | Batch numpy color ops |
| Special detection (templates) | < 10 ms | Per-cell match for colored cells only |
| OCR (turn + score) | < 15 ms | Small crops, digit-only mode |
| Move generation | < 5 ms | O(rows × cols) |
| **Greedy eval** | < 10 ms | |
| **Beam search (d=3, k=8)** | < 200 ms | |
| **MCTS (300 sims)** | < 900 ms | |
| Action execution + drag | 200–400 ms | Configurable step delay |
| Animation wait | 300–1500 ms | Variable; poll 50 ms |
| **Total loop (greedy)** | **< 500 ms** | |
| **Total loop (beam)** | **< 750 ms** | |

### 11.2 Profiling Toolchain

```
python -m ccrush play --profile-loop    # emit per-section ns timings via loguru
python -m ccrush benchmark              # run 100 synthetic games, report P50/P95 timings
```

Use `cProfile` + `snakeviz` for one-shot profiling. Use `line_profiler` for
hot paths in `classify.py` and `cascade.py`.

### 11.3 Key Optimizations

- **Region-only capture**: Pass exact board rect to `dxcam`. Never capture the
  full screen unless board detection is re-running.
- **Template caching**: Load and resize all `cv2.matchTemplate` templates once
  at startup. Store as `dict[SpecialType, np.ndarray]` in `SpecialCandyDetector`.
- **Batch color ops**: Extract all cell ROIs in one vectorized numpy slice
  operation; apply LAB mean in batch using `np.mean(..., axis=(1,2))`.
- **Move generator early exit**: Once a valid match is found after a swap, mark
  the swap legal immediately. No need to scan the full board for that swap.
- **Async capture + planning**: Run capture in a background thread. When the
  strategy engine is computing, the capture thread is already grabbing the next
  frame. Use a single-slot queue (`asyncio.Queue(maxsize=1)`) to hand off frames.
- **Skip OCR when unchanged**: Only re-run pytesseract if the pixel values in
  the OCR region changed by > threshold between frames.

---

## 12. Windows Automation Plan

### 12.1 Window Focus

```python
def safe_focus(hwnd: int) -> None:
    if win32gui.IsIconic(hwnd):    # minimized?
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.05)               # allow OS to complete focus switch
```

### 12.2 Coordinate Transformation

**Design principle**: declare the bot process as Per-Monitor-V2 DPI-aware
(application manifest or `SetProcessDpiAwarenessContext`), then work entirely
in client coordinates. The OS handles the DPI mapping; we never apply a manual
scale factor.

**Why not a DPI ratio?** A homegrown `actual_dpi / system_dpi` multiplier can
double-apply scaling when the game window is DPI-unaware (Windows virtualises
its coordinates) while the bot process is DPI-aware. The result is a click
offset that grows with DPI. Working in client space and using `ClientToScreen`
avoids this entirely.

```python
import ctypes
import win32gui
import win32con
import win32api

# --- Process-level DPI setup (call once at startup) ---
ctypes.windll.user32.SetProcessDpiAwarenessContext(
    ctypes.c_ssize_t(-4)   # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
)

def board_to_screen(r: int, c: int, geom: GridGeometry,
                    bounds: BoardBounds, hwnd: int) -> tuple[int, int]:
    """Convert board (row, col) → screen pixels via OS client-to-screen."""
    # 1. Board crop is already in client coordinates: board origin is bounds.(x,y)
    #    relative to the top-left of the window's client area.
    client_x = int(bounds.x + geom.offset_x + c * geom.cell_w + geom.cell_w / 2)
    client_y = int(bounds.y + geom.offset_y + r * geom.cell_h + geom.cell_h / 2)

    # 2. Convert client coords to screen coords. The OS applies per-monitor
    #    scaling if the game window is DPI-unaware; we never do it manually.
    pt = win32gui.ClientToScreen(hwnd, (client_x, client_y))
    return pt  # (screen_x, screen_y)


def to_absolute(x: int, y: int) -> tuple[int, int]:
    """Convert screen pixels → SendInput normalised [0, 65535] space."""
    # SM_CXVIRTUALSCREEN / SM_CYVIRTUALSCREEN covers multi-monitor setups.
    vw = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
    vh = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
    # Virtual screen origin may be non-zero on multi-monitor configs.
    vx = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
    vy = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
    abs_x = int((x - vx) * 65535 / vw)
    abs_y = int((y - vy) * 65535 / vh)
    return abs_x, abs_y
```

**Note on the game window DPI state**: if the game process is DPI-unaware,
Windows reports virtualised client coordinates to it and scales its rendering.
`ClientToScreen` from our DPI-aware process returns physical screen pixels,
which is exactly what `SendInput` requires. No manual scale factor is needed.

### 12.3 Drag Sequence

```python
def execute_drag(src: tuple[int,int], dst: tuple[int,int],
                 steps: int = 5, step_delay_ms: int = 30) -> None:
    sx, sy = to_absolute(*src)
    dx, dy = to_absolute(*dst)

    send_mouse_input(sx, sy, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    time.sleep(0.02)
    send_mouse_input(sx, sy, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE)
    time.sleep(0.02)

    for i in range(1, steps + 1):
        ix = sx + (dx - sx) * i // steps
        iy = sy + (dy - sy) * i // steps
        send_mouse_input(ix, iy, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
        time.sleep(step_delay_ms / 1000)

    send_mouse_input(dx, dy, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE)
```

### 12.4 Move Verification and Misclick Recovery

After the drag:
1. Wait `animation_timeout` ms (default 1500 ms) for animation to finish.
2. Re-classify the two swapped cells.
3. If cell colors switched as expected → success.
4. If unchanged → swap was rejected (no match created, game rule). This should
   not happen if `MoveGenerator` works correctly; increment error counter.
5. If completely wrong board state → trigger `RecoveryManager`.

### 12.5 Abort Mechanism

A `threading.Event` named `abort_event` is checked at the top of each loop
iteration. Press `Ctrl+C` or a hotkey (e.g. F12) sets this event. The main
loop exits cleanly; no partial drag is left pending.

---

## 13. Calibration UX

### 13.1 Calibration Flow

```
$ python -m ccrush calibrate [--profile myprofile]

Step 1: Detect game window
  ✓  Found "King" window at (0, 0, 1920, 1080)
  → Is this the correct window? [Y/n]

Step 2: Board bounds
  → Taking screenshot...
  ✓  Board detected at (420, 180, 640, 640) with confidence 0.87
  → Showing overlay. Press Enter to confirm or drag corners to adjust.

Step 3: Grid geometry
  ✓  Detected 9×9 grid, cell size 71×71 px
  → Showing grid overlay. Press Enter to confirm or type "rows=8 cols=9" to override.

Step 4: Playable mask
  → Detected 3 non-playable cells (dark/empty). Showing mask overlay.
  → Press Enter to confirm, or click cells to toggle.

Step 5: Candy color sampling
  → Found 6 distinct color clusters. Label each:
  Cluster 1 (shown in overlay): [red] _
  Cluster 2:                    [orange] _
  ...

Step 6: Special candy templates
  → For each special type, right-click a cell in the game that shows it,
    then press Enter. Press 'n' to skip a type.
  Collecting template: STRIPED_H ... ✓
  Collecting template: WRAPPED   ... ✓
  Collecting template: COLOR_BOMB ... n (skipped)

Step 7: OCR regions
  → Attempting auto-detect of turn counter and score regions...
  ✓  Turn counter detected at (862, 98, 80, 40)
  ✓  Score region detected at (700, 50, 300, 45)

Step 8: Save profile
  → Saving to profiles/myprofile.yaml
  ✓  Done. Run: python -m ccrush play --profile myprofile
```

### 13.2 Profile YAML Structure

```yaml
name: "myprofile"
version: 1
created: "2026-04-20"
resolution: [1920, 1080]
window_title_fragment: "King"  # or window class name

board_bounds: {x: 420, y: 180, w: 640, h: 640}
grid:
  rows: 9
  cols: 9
  cell_w: 71.0
  cell_h: 71.0
  offset_x: 0.0
  offset_y: 0.0

playable_mask:           # row-major, true = playable
  - [true, true, true, true, true, true, true, true, true]
  # ... 9 rows

color_clusters:          # LAB centroids for each candy color
  RED:    [48.0, 45.0, 32.0]
  ORANGE: [62.0, 22.0, 42.0]
  YELLOW: [75.0, -5.0, 55.0]
  GREEN:  [55.0, -28.0, 22.0]
  BLUE:   [45.0, -5.0, -38.0]
  PURPLE: [38.0, 22.0, -28.0]
cluster_radius: 22.0     # max LAB distance for confident match

template_paths:          # relative to profiles/
  STRIPED_H: "myprofile/striped_h.png"
  STRIPED_V: "myprofile/striped_v.png"
  WRAPPED:   "myprofile/wrapped.png"
special_match_threshold: 0.65

ocr_regions:
  turns: {x: 862, y: 98, w: 80, h: 40}
  score: {x: 700, y: 50, w: 300, h: 45}

eval_weights:
  w_clear: 10.0
  w_cascade: 6.0
  w_special: 1.0
  w_combo: 1.0
  w_lower: 4.0
  w_blocker: 8.0
  w_obj: 12.0
  w_entropy: 2.0
  w_dead: 15.0

objective: "score"       # "score" | "jelly" | "blocker" | "ingredient"
default_turns_fallback: 15
animation_threshold: 8.0
animation_timeout_ms: 1500
time_budget_ms: 400.0
```

---

## 14. Testing Plan

### 14.1 Unit Tests

```python
# tests/unit/test_match_detector.py
def test_horizontal_match_3():
    board = make_board("""
    R R R B G
    """)
    matches = MatchDetector().find(board)
    assert len(matches) == 1
    assert matches[0].cells == [(0,0), (0,1), (0,2)]

def test_no_match():
    board = make_board("R G B R G")
    assert MatchDetector().find(board) == []

def test_t_shape_creates_wrapped():
    board = make_board("""
    . R .
    R R R
    . R .
    """)
    matches = MatchDetector().find(board)
    assert any(m.special_created == SpecialType.WRAPPED for m in matches)
```

```python
# tests/unit/test_gravity.py
def test_gravity_fills_gap():
    board = make_board("""
    R B G
    . . .   <- empty (cleared)
    B G R
    """)
    result = GravityEngine().apply(board)
    assert result.cells[2][0].color == CandyColor.RED   # fell down
    assert result.cells[0][0].color == CandyColor.UNKNOWN  # new unknown fill
```

### 14.2 Property Tests (hypothesis)

```python
# tests/property/test_move_legality.py
from hypothesis import given, strategies as st

@given(st.integers(3, 12), st.integers(3, 12), st.integers(0, 100))
def test_all_generated_moves_are_adjacent(rows, cols, seed):
    board = SyntheticBoard(rows=rows, cols=cols, seed=seed).generate()
    for move in MoveGenerator().generate(board):
        assert move.is_adjacent()
        assert board.cell(move.r1, move.c1).playable
        assert board.cell(move.r2, move.c2).playable

@given(st.integers(3, 12), st.integers(3, 12), st.integers(0, 100))
def test_generated_moves_all_produce_match(rows, cols, seed):
    board = SyntheticBoard(rows=rows, cols=cols, seed=seed).generate()
    for move in MoveGenerator().generate(board):
        after = apply_swap(board, move)
        assert len(MatchDetector().find(after)) > 0
```

### 14.3 Vision Replay Tests

```python
# tests/vision/test_classifier_replay.py
@pytest.mark.parametrize("fixture", list_vision_fixtures())
def test_classifier_matches_expected(fixture):
    frame = cv2.imread(fixture.screenshot_path)
    profile = load_profile(fixture.profile_name)
    state = build_state(frame, profile)
    for (r, c, expected_color) in fixture.expected_cells:
        assert state.cell(r, c).color == expected_color, \
            f"Mismatch at ({r},{c}): got {state.cell(r,c).color}"
```

Fixtures are stored as `tests/vision/fixtures/<name>/`:
```
screenshot.png
expected_state.json    # {cells: [{r, c, color, special}, ...]}
profile.yaml           # which profile to use
```

### 14.4 Simulator Regression Tests

```python
# tests/simulator/benchmark_policies.py
def test_beam_beats_greedy_mean_score():
    scores_greedy = run_games(GreedyPolicy(), n=200, seed=42)
    scores_beam   = run_games(BeamSearchPolicy(depth=3, beam=6), n=200, seed=42)
    assert np.mean(scores_beam) > np.mean(scores_greedy) * 1.05  # >5% improvement
```

### 14.5 Calibration Snapshot Tests

```python
def test_profile_detects_correct_grid():
    frame = cv2.imread("tests/calibration/fixtures/hd_1080p.png")
    profile = ProfileManager().load("hd_1080p")
    geom = GridCalibrator().infer(crop_board(frame, profile.board_bounds), profile.grid)
    assert geom.rows == profile.grid.rows
    assert geom.cols == profile.grid.cols
    assert abs(geom.cell_w - profile.grid.cell_w) < 2.0
```

### 14.6 End-to-End Dry Run

```
$ python -m ccrush play --dry-run --profile myprofile --turns 5

[DRY RUN] Captured frame 1
[DRY RUN] Board detected at (420, 180, 640, 640), confidence=0.91
[DRY RUN] State built: 9×9, 81 cells, 0 unknown
[DRY RUN] Generated 39 legal moves
[DRY RUN] BeamSearch selected: Move(r1=4,c1=3,r2=4,c2=4), score=72.3
[DRY RUN] Would execute drag (760, 464) → (831, 464) [NOT EXECUTED]
Iteration 1 complete, 0 real moves executed.
```

`--dry-run` skips `ActionExecutor.execute()` and logs what would be clicked.

---

## 15. Main Loop Pseudocode

```python
async def main_loop(config: AppConfig, profile: CalibrationProfile) -> None:
    session     = SessionManager(profile)
    capture     = CaptureEngine(session.window_rect)
    vision      = VisionPipeline(profile)
    rules       = RulesEngine()
    strategy    = StrategyDispatcher(config)
    executor    = ActionExecutor(session, profile)
    recovery    = RecoveryManager(session, capture, vision)
    metrics     = MetricsLogger(config.log_path)
    frame_queue = asyncio.Queue(maxsize=1)

    await session.focus_window()

    async def capture_loop():
        while not abort_event.is_set():
            frame = capture.capture()
            await frame_queue.put(frame)   # drops old frame if full
            await asyncio.sleep(0)

    asyncio.create_task(capture_loop())

    while not abort_event.is_set():
        t0 = perf_ns()

        # 1. Wait for stable frame
        frame = await frame_queue.get()
        if AnimationDetector.is_animating(frame, capture.last_frame):
            await asyncio.sleep(0.05)
            continue

        # 2. Build game state
        with metrics.timer("vision"):
            state = vision.build_state(frame)

        if state.confidence < config.min_state_confidence:
            await recovery.attempt()
            continue

        # 3. Check terminal conditions
        if state.turn is not None and state.turn == 0:
            metrics.log_game_end(state.score)
            break

        # 4. Generate moves
        with metrics.timer("rules"):
            moves = rules.generate_moves(state)

        if not moves:
            await recovery.handle_no_moves(state)
            continue

        # 5. Select best move
        ctx = build_policy_context(state, config)
        with metrics.timer("strategy"):
            ranked = strategy.rank_moves(state, moves, ctx)
        best = ranked[0]

        # 6. Execute
        if not config.dry_run:
            with metrics.timer("execute"):
                await executor.execute(best.move, state)

        metrics.record_move(best, elapsed_ns=perf_ns() - t0)
```

---

## 16. Move Evaluation Pseudocode

```python
def evaluate_move(state: GameState, move: Move, ctx: PolicyContext,
                  weights: EvalWeights) -> float:
    # 1. Simulate swap
    board_copy = clone_board(state)
    swap_cells(board_copy, move)

    # 2. Detect initial matches
    match_set = MatchDetector.find(board_copy)
    if not match_set:
        return -math.inf  # invalid move

    for match in match_set:
        clear_cells(board_copy, match.cells)
        place_special(board_copy, match.special_created, match.trigger_cell)

    # 3. Cascade
    cascade = CascadeSimulator.run(board_copy)

    # 4. Build SimResult
    sim = SimResult(
        move=move,
        cleared_count=len(initial_cleared) + cascade.total_cleared,
        specials_created=[m.special_created for m in match_set
                          if m.special_created != SpecialType.NONE],
        cascade_depth=cascade.depth,
        score_estimate=cleared_count * 60 + cascade_bonus(cascade.depth),
        blocker_progress=cascade.blocker_progress,
    )

    # 5. Compute weighted score
    score = 0.0
    score += weights.w_clear   * sim.cleared_count
    score += weights.w_cascade * cascade_potential(board_copy, sim)
    score += weights.w_special * sum(SPECIAL_VALUE[s] for s in sim.specials_created)
    score += weights.w_combo   * detect_adjacent_specials_bonus(board_copy)
    score += weights.w_lower   * lower_board_bonus(board_copy, sim)
    score += weights.w_blocker * sim.blocker_progress
    score += weights.w_obj     * objective_progress(board_copy, ctx)
    score += weights.w_entropy * entropy_delta(state, board_copy)
    score -= weights.w_dead    * dead_board_risk(board_copy)

    return score
```

---

## 17. Risks, Unknowns, and Fallback Strategies

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Game updates change candy skin / UI layout | High | Medium | Profile system: re-run calibration after update |
| DPI scaling errors on HiDPI displays | High | Medium | Always read `GetDpiForWindow`; test at 125%, 150% |
| Animation detection wrong threshold | Medium | Medium | Per-profile tunable; log false positives |
| Exact special candy interaction rules differ from model | Medium | High | Log predicted vs observed outcomes; update `SpecialCandyRules` table |
| OCR fails on stylized turn/score fonts | Low–Medium | Medium | Fallback: count moves manually; disable OCR, use move counter |
| Game detects bot input and bans account | High | Low | Use human-like drag interpolation and timing jitter |
| Cascade simulation diverges from real game | Medium | Medium | Replay tests; instrument divergence rate from live play |
| Board geometry not detected (unusual level) | High | Low | Manual override via `--board-bounds` CLI arg |
| Python latency prevents timely moves | Low | Low | Strategy time budget enforced; hard fallback to greedy |
| Windows API focus stealing blocked | Medium | Low | Use `AttachThreadInput` alternative path |

---

## 18. Minimal Viable Version vs Advanced Version

### MVP (Phase 0–2, ~4 weeks)

- `dxcam` region capture.
- OpenCV board detection and grid calibration (no template matching — hardcoded
  profile for one resolution).
- Color-cluster candy classifier (6 colors).
- Move generator + cascade simulator (no specials).
- Greedy policy only.
- `SendInput` drag executor.
- Manual profile YAML (no calibration wizard).
- `pytest` unit tests for rules engine.
- CLI: `python -m ccrush play --profile default`.

**Expected capability**: Plays score-only levels on a fixed 9×9 layout at a
fixed resolution. Makes reasonable moves but no planning depth.

### Advanced Version (Phase 3–6, ~8 additional weeks)

All of the above plus:
- Automatic board detection (any layout, any position).
- `GridCalibrator` with Sobel peak detection.
- Special candy detection (templates).
- `SpecialCandyRules` interaction table.
- `BeamSearchPolicy` (default) + `MCTSPolicy`.
- Full calibration wizard (`rich` TUI).
- OCR for turn counter and score.
- `AnimationDetector` with reliable wait logic.
- `RecoveryManager` with popup handling.
- Metric logging + replay tests.
- Simulator-based policy benchmarking.
- Objective-specific weight presets.

**Expected capability**: Plays all standard level types on any calibrated
layout. Achieves strong scores by planning special candy combos and selecting
moves that maximize cascade potential.

### Future / Optional

- CNN candy classifier (better robustness under skin changes).
- DQN/AlphaZero-style trained policy (requires simulator data generation).
- Web-based calibration UI (replace `rich` TUI with a local HTTP server + browser overlay).
- Multi-level session automation with level selection.

---

## 19. Step-by-Step Implementation Roadmap

### Phase 0 — Foundation (Week 1)

1. `pyproject.toml`: add `opencv-python`, `dxcam`, `pywin32`, `pytesseract`,
   `loguru`, `rich`, `mss`, `hypothesis` as dependencies.
2. Create folder structure as defined in Section 5.
3. Write `state/models.py` — all Pydantic models.
4. Write `simulator/board.py` — `SyntheticBoard` with deterministic RNG.
5. Write `rules/match.py`, `rules/gravity.py`, `rules/cascade.py`.
6. Write `rules/moves.py` — `MoveGenerator`.
7. Write full unit test suite for rules (>80% function coverage).
8. Write property tests (hypothesis) for move legality.

### Phase 1 — Vision Layer (Weeks 2–3)

9. Write `capture/window.py` — `WindowManager` with `pywin32`.
10. Write `capture/engine.py` — `CaptureEngine` (dxcam + mss fallback).
11. Write `vision/board.py` — `BoardDetector` (contour + fallback template).
12. Write `vision/grid.py` — `GridCalibrator` (Sobel peaks).
13. Write `vision/classify.py` — `CellClassifier` (color cluster nearest-centroid).
14. Write `vision/motion.py` — `AnimationDetector`.
15. Write `state/builder.py` — `StateBuilder`.
16. Add vision replay test fixture for one sample screenshot.

### Phase 2 — Greedy Bot (Week 4)

17. Write `strategy/eval.py` — `EvalFunction`.
18. Write `strategy/greedy.py` — `GreedyPolicy`.
19. Write `strategy/dispatcher.py` — `StrategyDispatcher` (greedy only for now).
20. Write `executor/transform.py` — `CoordTransformer`.
21. Write `executor/input.py` — `SendInputDriver` (ctypes SendInput).
22. Write `executor/verify.py` — `MoveVerifier`.
23. Write `__main__.py` — `play` subcommand.
24. Manual end-to-end test: run bot on a test level, observe moves.

### Phase 3 — Strategy Upgrade (Weeks 5–6)

25. Write `strategy/beam.py` — `BeamSearchPolicy`.
26. Write `strategy/mcts.py` — `MCTSPolicy`.
27. Write `strategy/learned.py` — `LearnedPolicy` stub.
28. Update `StrategyDispatcher` with full policy-switching logic.
29. Run simulator benchmarks: greedy vs beam vs mcts.
30. Tune `EvalWeights` via benchmark A/B tests.

### Phase 4 — Calibration UX (Week 7)

31. Write `calibration/profile.py` — `CalibrationProfile` Pydantic model.
32. Write `calibration/manager.py` — `ProfileManager`.
33. Write `calibration/wizard.py` — `CalibrationWizard` (rich TUI).
34. Add `calibrate` subcommand to `__main__.py`.
35. Add OCR support: `vision/ocr.py` using pytesseract.
36. Add `vision/special.py` — `SpecialCandyDetector`.

### Phase 5 — Robustness (Week 8)

37. Write `recovery/manager.py` — `RecoveryManager`.
38. Improve `AnimationDetector` with tunable threshold.
39. Write `telemetry/logger.py` — `MetricsLogger`.
40. Add `--dry-run` mode to `play` subcommand.
41. Add integration test: full pipeline dry run with fixture frame.
42. Run full test suite; address any regressions.

### Phase 6 — Optional ML (Future)

43. Collect 5000+ labeled cell crops via the calibration wizard.
44. Train MobileNetV3-small on cell crops (PyTorch, ~1 hour GPU).
45. Integrate `LearnedPolicy` with a real DQN trained on `SyntheticBoard` data.
