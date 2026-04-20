# ccrush-ai

A Windows Python application that autonomously plays Candy Crush-style match-3
games. It captures the screen in real time, classifies the board, plans moves
with a beam search strategy, and executes drags — all without game SDK access.

---

## Quick Start

```bash
# Install dependencies (requires Python 3.12+)
pip install -e ".[dev]"

# Calibrate for your game layout
python -m ccrush calibrate --profile myprofile

# Play
python -m ccrush play --profile myprofile

# Dry run (no clicks)
python -m ccrush play --profile myprofile --dry-run
```

---

## Key Features

- **Geometry-agnostic** — any board shape, any cell count, any resolution or DPI scale.
- **Profile-driven** — all board-specific constants live in a YAML profile, not code.
- **Pluggable strategy** — Greedy, Beam Search, MCTS, and a Learned Policy stub.
- **Guided calibration** — `rich`-TUI wizard onboards a new layout in < 30 minutes.
- **Resilient** — `RecoveryManager` handles popups, failed swaps, and stuck animations.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full technical design: modules, data models, vision pipeline, strategy engine, pseudocode, testing plan, implementation roadmap |
| [docs/PROJECT.md](docs/PROJECT.md) | Product roadmap: epics, acceptance criteria, release plan |

---

## Tech Stack

| Purpose | Package |
|---|---|
| Screen capture | `dxcam` (DXGI) / `mss` fallback |
| Image processing | `opencv-python`, `numpy` |
| Data models | `pydantic` v2 |
| Windows input | `pywin32`, `ctypes` SendInput |
| OCR | `pytesseract` + Tesseract 5 |
| Calibration TUI | `rich` |
| Logging | `loguru` |
| Testing | `pytest`, `hypothesis` |

---

## Project Status

**v0.1.0** — In design. See [docs/PROJECT.md](docs/PROJECT.md) for the roadmap.
