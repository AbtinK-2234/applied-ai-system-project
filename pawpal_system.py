from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


PRIORITY_MAP = {"high": 3, "medium": 2, "low": 1}


@dataclass
class Task:
    """Represents a single pet care activity with duration, priority, and completion status."""

    title: str
    duration_minutes: int
    priority: str  # "low", "medium", "high"
    category: str  # "walk", "feeding", "medication", "grooming", "enrichment"
    pet_name: str = ""
    required: bool = False
    completed: bool = False
    start_time: str = ""  # "HH:MM" format, e.g. "08:30"
    frequency: str = "once"  # "once", "daily", "weekly"
    due_date: date | None = None

    @property
    def priority_value(self) -> int:
        """Return a numeric priority value for sorting."""
        return PRIORITY_MAP.get(self.priority, 0)

    @property
    def start_time_minutes(self) -> int:
        """Convert 'HH:MM' start_time to total minutes since midnight for sorting."""
        if not self.start_time:
            return 9999  # tasks without a time go to the end
        hours, minutes = self.start_time.split(":")
        return int(hours) * 60 + int(minutes)

    def mark_complete(self) -> Task | None:
        """Mark this task as completed. Returns a new Task for the next occurrence if recurring."""
        self.completed = True
        if self.frequency == "once":
            return None
        delta = timedelta(days=1) if self.frequency == "daily" else timedelta(weeks=1)
        next_due = (self.due_date or date.today()) + delta
        return Task(
            title=self.title,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            category=self.category,
            pet_name=self.pet_name,
            required=self.required,
            start_time=self.start_time,
            frequency=self.frequency,
            due_date=next_due,
        )


@dataclass
class Pet:
    """Stores pet details and manages a list of care tasks."""

    name: str
    species: str  # "dog", "cat", "other"
    breed: str = ""
    age: int = 0
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a task to this pet and stamp it with the pet's name."""
        task.pet_name = self.name
        self.tasks.append(task)

    def remove_task(self, title: str) -> None:
        """Remove a task by title."""
        self.tasks = [t for t in self.tasks if t.title != title]

    def complete_task(self, title: str) -> None:
        """Mark a task complete and auto-schedule its next occurrence if recurring."""
        for task in self.tasks:
            if task.title == title and not task.completed:
                next_task = task.mark_complete()
                if next_task is not None:
                    self.tasks.append(next_task)
                return


@dataclass
class Owner:
    """Manages multiple pets and provides access to all their tasks."""

    name: str
    available_time: int  # minutes available for pet care today
    preferences: list[str] = field(default_factory=list)
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner's household."""
        self.pets.append(pet)

    def remove_pet(self, name: str) -> None:
        """Remove a pet by name."""
        self.pets = [p for p in self.pets if p.name != name]

    def get_all_tasks(self) -> list[Task]:
        """Collect and return all tasks across all pets."""
        all_tasks = []
        for pet in self.pets:
            all_tasks.extend(pet.tasks)
        return all_tasks


class Scheduler:
    """Generates a priority-based daily care schedule within the owner's time budget."""

    def __init__(self, owner: Owner) -> None:
        """Initialize the scheduler with an owner's data."""
        self.owner = owner
        self.daily_plan: list[Task] = []
        self.skipped_tasks: list[Task] = []
        self.reasoning: list[str] = []
        self.conflicts: list[str] = []

    def sort_by_time(self, tasks: list[Task]) -> list[Task]:
        """Sort tasks by their start_time in 'HH:MM' format (earliest first)."""
        return sorted(tasks, key=lambda t: t.start_time_minutes)

    def filter_by_pet(self, pet_name: str) -> list[Task]:
        """Return only tasks belonging to a specific pet."""
        return [t for t in self.owner.get_all_tasks() if t.pet_name == pet_name]

    def filter_by_status(self, completed: bool) -> list[Task]:
        """Return tasks filtered by completion status."""
        return [t for t in self.owner.get_all_tasks() if t.completed == completed]

    def detect_conflicts(self, tasks: list[Task]) -> list[str]:
        """Detect tasks that overlap in time and return warning messages."""
        warnings = []
        timed = [t for t in tasks if t.start_time]
        timed_sorted = self.sort_by_time(timed)

        for i in range(len(timed_sorted) - 1):
            current = timed_sorted[i]
            nxt = timed_sorted[i + 1]
            current_end = current.start_time_minutes + current.duration_minutes
            if current_end > nxt.start_time_minutes:
                end_h, end_m = divmod(current_end, 60)
                warnings.append(
                    f"CONFLICT: '{current.title}' ({current.pet_name}, "
                    f"{current.start_time}–{end_h:02d}:{end_m:02d}) "
                    f"overlaps with '{nxt.title}' ({nxt.pet_name}, starts at {nxt.start_time})"
                )
        return warnings

    def generate_schedule(self) -> list[Task]:
        """Build a daily plan by scheduling required tasks first, then by priority."""
        self.daily_plan = []
        self.skipped_tasks = []
        self.reasoning = []
        self.conflicts = []

        all_tasks = [t for t in self.owner.get_all_tasks() if not t.completed]
        time_remaining = self.owner.available_time

        # Detect conflicts before scheduling
        self.conflicts = self.detect_conflicts(all_tasks)
        for warning in self.conflicts:
            self.reasoning.append(warning)

        # Split into required and optional tasks
        required_tasks = [t for t in all_tasks if t.required]
        optional_tasks = [t for t in all_tasks if not t.required]

        # Schedule required tasks first (sorted by priority, highest first)
        required_tasks.sort(key=lambda t: t.priority_value, reverse=True)
        for task in required_tasks:
            if task.duration_minutes <= time_remaining:
                self.daily_plan.append(task)
                time_remaining -= task.duration_minutes
                self.reasoning.append(
                    f"Scheduled '{task.title}' for {task.pet_name} "
                    f"({task.duration_minutes} min) — required task"
                )
            else:
                self.skipped_tasks.append(task)
                self.reasoning.append(
                    f"WARNING: Required task '{task.title}' for {task.pet_name} "
                    f"skipped — not enough time ({task.duration_minutes} min needed, "
                    f"{time_remaining} min left)"
                )

        # Schedule optional tasks by priority (highest first)
        optional_tasks.sort(key=lambda t: t.priority_value, reverse=True)
        for task in optional_tasks:
            if task.duration_minutes <= time_remaining:
                self.daily_plan.append(task)
                time_remaining -= task.duration_minutes
                self.reasoning.append(
                    f"Scheduled '{task.title}' for {task.pet_name} "
                    f"({task.duration_minutes} min) — {task.priority} priority"
                )
            else:
                self.skipped_tasks.append(task)
                self.reasoning.append(
                    f"Skipped '{task.title}' for {task.pet_name} "
                    f"— not enough time ({task.duration_minutes} min needed, "
                    f"{time_remaining} min left)"
                )

        # Sort the final plan by start_time for display
        self.daily_plan = self.sort_by_time(self.daily_plan)

        return self.daily_plan

    def explain_plan(self) -> str:
        """Return a formatted string explaining the schedule and reasoning."""
        lines = []
        lines.append(f"Schedule for {self.owner.name} "
                      f"({self.owner.available_time} min available):")
        lines.append("-" * 50)

        if not self.daily_plan:
            lines.append("No tasks scheduled.")
            return "\n".join(lines)

        total_time = 0
        for i, task in enumerate(self.daily_plan, start=1):
            status = "DONE" if task.completed else "TODO"
            tag = "REQUIRED" if task.required else task.priority
            time_str = task.start_time if task.start_time else "—:—"
            freq = f" [{task.frequency}]" if task.frequency != "once" else ""
            lines.append(
                f"  {i}. [{status}] {time_str}  {task.title} ({task.pet_name}) "
                f"— {task.duration_minutes} min [{tag}]{freq}"
            )
            total_time += task.duration_minutes

        lines.append("-" * 50)
        lines.append(f"Total: {total_time} min scheduled, "
                      f"{self.owner.available_time - total_time} min free")

        if self.conflicts:
            lines.append(f"\n⚠ Conflicts ({len(self.conflicts)}):")
            for c in self.conflicts:
                lines.append(f"  - {c}")

        if self.skipped_tasks:
            lines.append(f"\nSkipped ({len(self.skipped_tasks)} tasks):")
            for task in self.skipped_tasks:
                lines.append(f"  - {task.title} ({task.pet_name}) "
                              f"— {task.duration_minutes} min")

        lines.append("\nReasoning:")
        for reason in self.reasoning:
            lines.append(f"  • {reason}")

        return "\n".join(lines)
