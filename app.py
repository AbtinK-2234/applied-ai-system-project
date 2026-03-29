import streamlit as st
from pawpal_system import Owner, Pet, Task, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

# --- Session State: persist the Owner across reruns ---
if "owner" not in st.session_state:
    st.session_state.owner = None

# --- Step 1: Owner Setup ---
if st.session_state.owner is None:
    st.subheader("Welcome! Let's set up your profile.")
    with st.form("owner_form"):
        owner_name = st.text_input("Your name", value="Jordan")
        available_time = st.number_input(
            "Minutes available for pet care today",
            min_value=5, max_value=480, value=60,
        )
        submitted = st.form_submit_button("Get Started")
        if submitted:
            st.session_state.owner = Owner(
                name=owner_name, available_time=available_time
            )
            st.rerun()
else:
    owner = st.session_state.owner

    st.markdown(f"**Owner:** {owner.name} · **Time budget:** {owner.available_time} min")

    # --- Step 2: Add a Pet ---
    st.subheader("🐶 Pets")

    with st.form("pet_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            pet_name = st.text_input("Pet name", value="Mochi")
        with col2:
            species = st.selectbox("Species", ["dog", "cat", "other"])
        with col3:
            age = st.number_input("Age", min_value=0, max_value=30, value=2)
        add_pet = st.form_submit_button("Add Pet")
        if add_pet and pet_name:
            owner.add_pet(Pet(name=pet_name, species=species, age=age))
            st.rerun()

    if not owner.pets:
        st.info("No pets yet. Add one above.")
    else:
        for pet in owner.pets:
            st.markdown(f"- **{pet.name}** ({pet.species}, age {pet.age}) — {len(pet.tasks)} tasks")

    # --- Step 3: Add Tasks to a Pet ---
    if owner.pets:
        st.subheader("📋 Tasks")

        with st.form("task_form"):
            target_pet = st.selectbox(
                "Add task for", [p.name for p in owner.pets]
            )
            col1, col2 = st.columns(2)
            with col1:
                task_title = st.text_input("Task title", value="Morning walk")
                duration = st.number_input(
                    "Duration (minutes)", min_value=1, max_value=240, value=20
                )
            with col2:
                priority = st.selectbox("Priority", ["high", "medium", "low"])
                category = st.selectbox(
                    "Category",
                    ["walk", "feeding", "medication", "grooming", "enrichment"],
                )
            required = st.checkbox("Required (cannot be skipped)")
            add_task = st.form_submit_button("Add Task")
            if add_task and task_title:
                pet = next(p for p in owner.pets if p.name == target_pet)
                pet.add_task(Task(
                    title=task_title,
                    duration_minutes=int(duration),
                    priority=priority,
                    category=category,
                    required=required,
                ))
                st.rerun()

        # Show current tasks per pet
        all_tasks = owner.get_all_tasks()
        if all_tasks:
            st.markdown("**Current tasks:**")
            for task in all_tasks:
                tag = "🔴 REQUIRED" if task.required else task.priority
                st.markdown(
                    f"- {task.title} ({task.pet_name}) — "
                    f"{task.duration_minutes} min · [{tag}]"
                )
        else:
            st.info("No tasks yet. Add one above.")

    # --- Step 4: Generate Schedule ---
    st.divider()
    st.subheader("📅 Daily Schedule")

    if st.button("Generate Schedule"):
        if not owner.get_all_tasks():
            st.warning("Add at least one task before generating a schedule.")
        else:
            scheduler = Scheduler(owner)
            scheduler.generate_schedule()
            st.session_state.last_plan = scheduler.explain_plan()

    if "last_plan" in st.session_state:
        st.code(st.session_state.last_plan, language=None)

    # --- Reset ---
    st.divider()
    if st.button("Start Over"):
        st.session_state.owner = None
        st.session_state.pop("last_plan", None)
        st.rerun()
