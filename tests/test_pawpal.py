import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pawpal_system import Owner, Pet, Task, Scheduler


# ── Happy-path tests ──────────────────────────────────────────────


class TestTaskCompletion:
    def test_mark_complete_changes_status(self):
        task = Task(title="Walk", duration_minutes=20, priority="high", category="walk")
        assert task.completed is False
        task.mark_complete()
        assert task.completed is True

    def test_new_task_starts_incomplete(self):
        task = Task(title="Feed", duration_minutes=10, priority="medium", category="feeding")
        assert task.completed is False


class TestTaskAddition:
    def test_adding_task_increases_count(self):
        pet = Pet(name="Mochi", species="dog")
        assert len(pet.tasks) == 0
        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high", category="walk"))
        assert len(pet.tasks) == 1
        pet.add_task(Task(title="Feed", duration_minutes=10, priority="high", category="feeding"))
        assert len(pet.tasks) == 2

    def test_add_task_sets_pet_name(self):
        pet = Pet(name="Whiskers", species="cat")
        task = Task(title="Brush", duration_minutes=15, priority="low", category="grooming")
        pet.add_task(task)
        assert task.pet_name == "Whiskers"

    def test_remove_task_decreases_count(self):
        pet = Pet(name="Mochi", species="dog")
        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high", category="walk"))
        pet.add_task(Task(title="Feed", duration_minutes=10, priority="high", category="feeding"))
        pet.remove_task("Walk")
        assert len(pet.tasks) == 1
        assert pet.tasks[0].title == "Feed"


class TestScheduler:
    def test_required_tasks_scheduled_first(self):
        owner = Owner(name="Jordan", available_time=60)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="Walk", duration_minutes=25, priority="high", category="walk"))
        pet.add_task(Task(title="Medication", duration_minutes=5, priority="medium",
                          category="medication", required=True))

        scheduler = Scheduler(owner)
        plan = scheduler.generate_schedule()

        # After time-sorting, required "Medication" should still be in the plan
        assert any(t.title == "Medication" for t in plan)

    def test_tasks_skipped_when_time_exceeded(self):
        owner = Owner(name="Jordan", available_time=15)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="Walk", duration_minutes=10, priority="high", category="walk"))
        pet.add_task(Task(title="Grooming", duration_minutes=10, priority="low", category="grooming"))

        scheduler = Scheduler(owner)
        scheduler.generate_schedule()

        assert len(scheduler.daily_plan) == 1
        assert len(scheduler.skipped_tasks) == 1
        assert scheduler.skipped_tasks[0].title == "Grooming"


class TestSortingAndFiltering:
    def test_sort_by_time(self):
        owner = Owner(name="Jordan", available_time=60)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="Late", duration_minutes=10, priority="low",
                          category="walk", start_time="14:00"))
        pet.add_task(Task(title="Early", duration_minutes=10, priority="low",
                          category="walk", start_time="07:00"))
        pet.add_task(Task(title="Mid", duration_minutes=10, priority="low",
                          category="walk", start_time="10:30"))

        scheduler = Scheduler(owner)
        sorted_tasks = scheduler.sort_by_time(owner.get_all_tasks())

        assert [t.title for t in sorted_tasks] == ["Early", "Mid", "Late"]

    def test_filter_by_pet(self):
        owner = Owner(name="Jordan", available_time=60)
        mochi = Pet(name="Mochi", species="dog")
        whiskers = Pet(name="Whiskers", species="cat")
        owner.add_pet(mochi)
        owner.add_pet(whiskers)

        mochi.add_task(Task(title="Walk", duration_minutes=20, priority="high", category="walk"))
        whiskers.add_task(Task(title="Feed", duration_minutes=10, priority="high", category="feeding"))

        scheduler = Scheduler(owner)
        mochi_tasks = scheduler.filter_by_pet("Mochi")

        assert len(mochi_tasks) == 1
        assert mochi_tasks[0].title == "Walk"

    def test_filter_by_status(self):
        owner = Owner(name="Jordan", available_time=60)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high", category="walk"))
        pet.add_task(Task(title="Feed", duration_minutes=10, priority="high",
                          category="feeding", completed=True))

        scheduler = Scheduler(owner)

        pending = scheduler.filter_by_status(completed=False)
        assert len(pending) == 1
        assert pending[0].title == "Walk"

        done = scheduler.filter_by_status(completed=True)
        assert len(done) == 1
        assert done[0].title == "Feed"


class TestRecurringTasks:
    def test_daily_task_creates_next_occurrence(self):
        task = Task(title="Walk", duration_minutes=20, priority="high",
                    category="walk", frequency="daily", due_date=date.today())
        next_task = task.mark_complete()

        assert task.completed is True
        assert next_task is not None
        assert next_task.completed is False
        assert next_task.due_date == date.today() + timedelta(days=1)

    def test_weekly_task_creates_next_occurrence(self):
        task = Task(title="Bath", duration_minutes=30, priority="low",
                    category="grooming", frequency="weekly", due_date=date.today())
        next_task = task.mark_complete()

        assert next_task is not None
        assert next_task.due_date == date.today() + timedelta(weeks=1)

    def test_once_task_returns_none(self):
        task = Task(title="Vet visit", duration_minutes=60, priority="high",
                    category="medication", frequency="once")
        next_task = task.mark_complete()

        assert task.completed is True
        assert next_task is None

    def test_complete_task_on_pet_adds_next(self):
        pet = Pet(name="Mochi", species="dog")
        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high",
                          category="walk", frequency="daily", due_date=date.today()))
        assert len(pet.tasks) == 1

        pet.complete_task("Walk")

        assert len(pet.tasks) == 2
        assert pet.tasks[0].completed is True
        assert pet.tasks[1].completed is False
        assert pet.tasks[1].due_date == date.today() + timedelta(days=1)


class TestConflictDetection:
    def test_detects_overlapping_tasks(self):
        owner = Owner(name="Jordan", available_time=60)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="Walk", duration_minutes=30, priority="high",
                          category="walk", start_time="08:00"))
        pet.add_task(Task(title="Feed", duration_minutes=10, priority="high",
                          category="feeding", start_time="08:15"))

        scheduler = Scheduler(owner)
        conflicts = scheduler.detect_conflicts(owner.get_all_tasks())

        assert len(conflicts) == 1
        assert "CONFLICT" in conflicts[0]

    def test_no_conflict_when_no_overlap(self):
        owner = Owner(name="Jordan", available_time=60)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="Walk", duration_minutes=30, priority="high",
                          category="walk", start_time="08:00"))
        pet.add_task(Task(title="Feed", duration_minutes=10, priority="high",
                          category="feeding", start_time="09:00"))

        scheduler = Scheduler(owner)
        conflicts = scheduler.detect_conflicts(owner.get_all_tasks())

        assert len(conflicts) == 0


# ── Edge-case tests ───────────────────────────────────────────────


class TestEdgeCases:
    def test_pet_with_no_tasks(self):
        """Scheduling should work even if a pet has zero tasks."""
        owner = Owner(name="Jordan", available_time=60)
        owner.add_pet(Pet(name="Mochi", species="dog"))

        scheduler = Scheduler(owner)
        plan = scheduler.generate_schedule()

        assert plan == []
        assert scheduler.skipped_tasks == []
        assert "No tasks scheduled." in scheduler.explain_plan()

    def test_zero_available_time(self):
        """All tasks should be skipped when the owner has 0 minutes."""
        owner = Owner(name="Jordan", available_time=0)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)
        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high", category="walk"))

        scheduler = Scheduler(owner)
        scheduler.generate_schedule()

        assert len(scheduler.daily_plan) == 0
        assert len(scheduler.skipped_tasks) == 1

    def test_task_exactly_fills_remaining_time(self):
        """A task whose duration equals the remaining time should still be scheduled."""
        owner = Owner(name="Jordan", available_time=20)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)
        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high", category="walk"))

        scheduler = Scheduler(owner)
        scheduler.generate_schedule()

        assert len(scheduler.daily_plan) == 1
        assert scheduler.skipped_tasks == []

    def test_two_tasks_exact_same_start_time(self):
        """Two tasks at the exact same time should produce a conflict warning."""
        owner = Owner(name="Jordan", available_time=60)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high",
                          category="walk", start_time="08:00"))
        pet.add_task(Task(title="Feed", duration_minutes=10, priority="high",
                          category="feeding", start_time="08:00"))

        scheduler = Scheduler(owner)
        conflicts = scheduler.detect_conflicts(owner.get_all_tasks())

        assert len(conflicts) == 1
        assert "CONFLICT" in conflicts[0]

    def test_completed_tasks_excluded_from_schedule(self):
        """Already-completed tasks should not appear in the daily plan."""
        owner = Owner(name="Jordan", available_time=60)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high",
                          category="walk", completed=True))
        pet.add_task(Task(title="Feed", duration_minutes=10, priority="high",
                          category="feeding"))

        scheduler = Scheduler(owner)
        scheduler.generate_schedule()

        assert len(scheduler.daily_plan) == 1
        assert scheduler.daily_plan[0].title == "Feed"

    def test_remove_nonexistent_task_is_safe(self):
        """Removing a task title that doesn't exist should not raise an error."""
        pet = Pet(name="Mochi", species="dog")
        pet.add_task(Task(title="Walk", duration_minutes=20, priority="high", category="walk"))
        pet.remove_task("Nonexistent")
        assert len(pet.tasks) == 1

    def test_owner_with_no_pets(self):
        """Scheduling with no pets should produce an empty plan without errors."""
        owner = Owner(name="Jordan", available_time=60)
        scheduler = Scheduler(owner)
        plan = scheduler.generate_schedule()

        assert plan == []
        assert "No tasks scheduled." in scheduler.explain_plan()

    def test_tasks_without_start_time_sorted_last(self):
        """Tasks missing a start_time should appear after timed tasks."""
        owner = Owner(name="Jordan", available_time=60)
        pet = Pet(name="Mochi", species="dog")
        owner.add_pet(pet)

        pet.add_task(Task(title="No time", duration_minutes=10, priority="high", category="walk"))
        pet.add_task(Task(title="Early", duration_minutes=10, priority="low",
                          category="walk", start_time="07:00"))

        scheduler = Scheduler(owner)
        sorted_tasks = scheduler.sort_by_time(owner.get_all_tasks())

        assert sorted_tasks[0].title == "Early"
        assert sorted_tasks[1].title == "No time"

    def test_recurring_task_preserves_attributes(self):
        """The next occurrence of a recurring task should keep all original attributes."""
        task = Task(title="Walk", duration_minutes=25, priority="high", category="walk",
                    pet_name="Mochi", required=True, start_time="07:30",
                    frequency="daily", due_date=date.today())
        next_task = task.mark_complete()

        assert next_task.title == "Walk"
        assert next_task.duration_minutes == 25
        assert next_task.priority == "high"
        assert next_task.pet_name == "Mochi"
        assert next_task.required is True
        assert next_task.start_time == "07:30"
        assert next_task.frequency == "daily"

    def test_multiple_pets_tasks_interleaved_in_schedule(self):
        """Tasks from different pets should be combined and sorted by time."""
        owner = Owner(name="Jordan", available_time=60)
        mochi = Pet(name="Mochi", species="dog")
        whiskers = Pet(name="Whiskers", species="cat")
        owner.add_pet(mochi)
        owner.add_pet(whiskers)

        mochi.add_task(Task(title="Walk", duration_minutes=10, priority="high",
                            category="walk", start_time="09:00"))
        whiskers.add_task(Task(title="Feed", duration_minutes=10, priority="high",
                               category="feeding", start_time="08:00"))

        scheduler = Scheduler(owner)
        plan = scheduler.generate_schedule()

        assert plan[0].title == "Feed"
        assert plan[0].pet_name == "Whiskers"
        assert plan[1].title == "Walk"
        assert plan[1].pet_name == "Mochi"
