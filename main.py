from pawpal_system import Owner, Pet, Task, Scheduler

# --- Create Owner ---
owner = Owner(name="Jordan", available_time=60, preferences=["outdoor", "enrichment"])

# --- Create Pets ---
mochi = Pet(name="Mochi", species="dog", breed="Shiba Inu", age=3)
whiskers = Pet(name="Whiskers", species="cat", age=5)

owner.add_pet(mochi)
owner.add_pet(whiskers)

# --- Add Tasks to Mochi (dog) ---
mochi.add_task(Task(
    title="Morning walk",
    duration_minutes=25,
    priority="high",
    category="walk",
))
mochi.add_task(Task(
    title="Give heartworm medication",
    duration_minutes=5,
    priority="high",
    category="medication",
    required=True,
))
mochi.add_task(Task(
    title="Puzzle toy session",
    duration_minutes=15,
    priority="medium",
    category="enrichment",
))

# --- Add Tasks to Whiskers (cat) ---
whiskers.add_task(Task(
    title="Feed breakfast",
    duration_minutes=10,
    priority="high",
    category="feeding",
    required=True,
))
whiskers.add_task(Task(
    title="Brush fur",
    duration_minutes=15,
    priority="low",
    category="grooming",
))
whiskers.add_task(Task(
    title="Play with feather toy",
    duration_minutes=20,
    priority="medium",
    category="enrichment",
))

# --- Generate and display schedule ---
scheduler = Scheduler(owner)
scheduler.generate_schedule()

print(scheduler.explain_plan())
