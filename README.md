# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

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

## Smarter Scheduling

Beyond basic priority-based planning, PawPal+ includes several algorithmic enhancements:

- **Time-based sorting** — Tasks can have a `start_time` in `"HH:MM"` format. The scheduler sorts the final plan chronologically so the daily schedule reads in natural order.
- **Filtering** — The scheduler can filter tasks by pet name or by completion status, making it easy to view only what's relevant.
- **Recurring tasks** — Tasks can be set to `"daily"` or `"weekly"` frequency. When a recurring task is marked complete, a new instance is automatically created with the next due date (using `timedelta`).
- **Conflict detection** — Before building the schedule, the scheduler scans for overlapping time slots and surfaces warning messages rather than crashing, so the owner can adjust.
