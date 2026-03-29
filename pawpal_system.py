from dataclasses import dataclass, field


PRIORITY_MAP = {"high": 3, "medium": 2, "low": 1}


@dataclass
class Task:
    """Represents a single pet care activity with duration, priority, and completion status."""

    title: str
    duration_minutes: int
    priority: str  # "low", "medium", "high"
    category: str  # "walk", "feeding", "medication", "grooming", "enrichment"
    pet_name: str = ""
    required: bool = False  # True for tasks that must not be skipped (e.g. medication)
    completed: bool = False

    @property
    def priority_value(self) -> int:
        """Return a numeric priority value for sorting."""
        return PRIORITY_MAP.get(self.priority, 0)

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.completed = True


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

    def generate_schedule(self) -> list[Task]:
        """Build a daily plan by scheduling required tasks first, then by priority."""
        self.daily_plan = []
        self.skipped_tasks = []
        self.reasoning = []

        all_tasks = self.owner.get_all_tasks()
        time_remaining = self.owner.available_time

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

        return self.daily_plan

    def explain_plan(self) -> str:
        """Return a formatted string explaining the schedule and reasoning."""
        lines = []
        lines.append(f"Schedule for {self.owner.name} "
                      f"({self.owner.available_time} min available):")
        lines.append("-" * 40)

        if not self.daily_plan:
            lines.append("No tasks scheduled.")
            return "\n".join(lines)

        total_time = 0
        for i, task in enumerate(self.daily_plan, start=1):
            status = "DONE" if task.completed else "TODO"
            tag = "REQUIRED" if task.required else task.priority
            lines.append(
                f"  {i}. [{status}] {task.title} ({task.pet_name}) "
                f"— {task.duration_minutes} min [{tag}]"
            )
            total_time += task.duration_minutes

        lines.append("-" * 40)
        lines.append(f"Total: {total_time} min scheduled, "
                      f"{self.owner.available_time - total_time} min free")

        if self.skipped_tasks:
            lines.append(f"\nSkipped ({len(self.skipped_tasks)} tasks):")
            for task in self.skipped_tasks:
                lines.append(f"  - {task.title} ({task.pet_name}) "
                              f"— {task.duration_minutes} min")

        lines.append("\nReasoning:")
        for reason in self.reasoning:
            lines.append(f"  • {reason}")

        return "\n".join(lines)
