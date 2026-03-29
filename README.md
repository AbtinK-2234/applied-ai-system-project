# PawPal+ (Module 2 Project)

**PawPal+** is a Streamlit app that helps a pet owner plan daily care tasks for their pets using priority-based scheduling, conflict detection, and recurring task management.

## Features

- **Owner & Pet profiles** — Set up your name, daily time budget, and add multiple pets with species and age
- **Task management** — Add tasks with title, duration, priority, category, start time, frequency, and required flag
- **Priority-based scheduling** — Required tasks (e.g. medication) are scheduled first, then optional tasks fill remaining time by priority
- **Time-based sorting** — Tasks with a `start_time` in `"HH:MM"` format are displayed in chronological order
- **Filtering** — View tasks filtered by pet name or completion status
- **Recurring tasks** — Daily and weekly tasks auto-generate the next occurrence when marked complete (using `timedelta`)
- **Conflict detection** — Overlapping time slots are flagged with warnings before the schedule is built
- **Schedule explanation** — Every scheduling decision (included, skipped, conflict) is logged and displayed as reasoning

## Demo

To run the app locally:

```bash
streamlit run app.py
```

![PawPal+ App Demo](demo_screenshot.png)

## System Architecture

The final UML class diagram reflecting all four classes and their relationships:

![UML Class Diagram](uml_final.png)

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## Testing PawPal+

Run the full test suite with:

```bash
python -m pytest
```

The suite contains **26 tests** organized into 7 groups:

| Group | What it covers |
|---|---|
| `TestTaskCompletion` | `mark_complete()` changes status correctly |
| `TestTaskAddition` | Adding/removing tasks, pet name stamping |
| `TestScheduler` | Required-first scheduling, time-budget overflow |
| `TestSortingAndFiltering` | Chronological sort, filter by pet, filter by status |
| `TestRecurringTasks` | Daily/weekly recurrence, one-time tasks return None |
| `TestConflictDetection` | Overlapping times flagged, non-overlapping times clean |
| `TestEdgeCases` | No tasks, no pets, zero time, exact-fit, same start time, completed exclusion, safe removal, un-timed tasks sorted last, attribute preservation, multi-pet interleaving |

**Confidence level: 4/5** — Core scheduling, sorting, recurrence, and conflict logic are well-covered. Edge cases like invalid time formats or extremely large task sets are not yet tested.
