import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pawpal_system import Owner, Pet, Task, Scheduler


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

        assert plan[0].title == "Medication"

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
