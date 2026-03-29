from datetime import date
from pawpal_system import Owner, Pet, Task, Scheduler

# --- Create Owner ---
owner = Owner(name="Jordan", available_time=90, preferences=["outdoor", "enrichment"])

# --- Create Pets ---
mochi = Pet(name="Mochi", species="dog", breed="Shiba Inu", age=3)
whiskers = Pet(name="Whiskers", species="cat", age=5)

owner.add_pet(mochi)
owner.add_pet(whiskers)

# --- Add Tasks OUT OF ORDER to test sorting ---
mochi.add_task(Task(
    title="Puzzle toy session",
    duration_minutes=15,
    priority="medium",
    category="enrichment",
    start_time="10:00",
))
mochi.add_task(Task(
    title="Morning walk",
    duration_minutes=25,
    priority="high",
    category="walk",
    start_time="07:30",
))
mochi.add_task(Task(
    title="Give heartworm medication",
    duration_minutes=5,
    priority="high",
    category="medication",
    required=True,
    start_time="08:00",
    frequency="daily",
    due_date=date.today(),
))

# --- Add overlapping tasks to test conflict detection ---
whiskers.add_task(Task(
    title="Feed breakfast",
    duration_minutes=10,
    priority="high",
    category="feeding",
    required=True,
    start_time="08:00",  # same time as Mochi's medication — conflict!
    frequency="daily",
    due_date=date.today(),
))
whiskers.add_task(Task(
    title="Brush fur",
    duration_minutes=15,
    priority="low",
    category="grooming",
    start_time="11:00",
))
whiskers.add_task(Task(
    title="Play with feather toy",
    duration_minutes=20,
    priority="medium",
    category="enrichment",
    start_time="09:00",
))

# --- Generate and display schedule ---
scheduler = Scheduler(owner)
scheduler.generate_schedule()
print(scheduler.explain_plan())

# --- Demonstrate sorting by time ---
print("\n\n=== All tasks sorted by time ===")
for t in scheduler.sort_by_time(owner.get_all_tasks()):
    time_str = t.start_time if t.start_time else "—:—"
    print(f"  {time_str}  {t.title} ({t.pet_name}) — {t.duration_minutes} min")

# --- Demonstrate filtering ---
print("\n=== Mochi's tasks only ===")
for t in scheduler.filter_by_pet("Mochi"):
    print(f"  {t.title} — {t.priority} priority")

print("\n=== Incomplete tasks only ===")
for t in scheduler.filter_by_status(completed=False):
    print(f"  {t.title} ({t.pet_name}) — {'done' if t.completed else 'pending'}")

# --- Demonstrate recurring task ---
print("\n\n=== Recurring task demo ===")
print(f"Mochi's tasks before completing medication: {len(mochi.tasks)}")
mochi.complete_task("Give heartworm medication")
print(f"Mochi's tasks after completing medication:  {len(mochi.tasks)}")
for t in mochi.tasks:
    status = "DONE" if t.completed else "TODO"
    due = f" (due {t.due_date})" if t.due_date else ""
    print(f"  [{status}] {t.title}{due}")
