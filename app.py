import logging
from datetime import date

from dotenv import load_dotenv
import streamlit as st
from pawpal_system import Owner, Pet, Task, Scheduler
from ai_advisor import AIAdvisor

# --- Load .env file ---
load_dotenv()

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")
st.caption("A smart pet care scheduling assistant with AI-powered advice")

# --- Session State ---
if "owner" not in st.session_state:
    st.session_state.owner = None
if "advisor" not in st.session_state:
    advisor = AIAdvisor()
    if advisor.initialise():
        st.session_state.advisor = advisor
        logger.info("AI Advisor loaded successfully")
    else:
        st.session_state.advisor = None
        logger.warning("AI Advisor unavailable (check HF_TOKEN)")
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- Owner Setup ---
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

    # --- Header bar ---
    col_info, col_reset = st.columns([4, 1])
    with col_info:
        st.markdown(
            f"**Owner:** {owner.name} · **Time budget:** {owner.available_time} min"
        )
    with col_reset:
        if st.button("Start Over"):
            st.session_state.owner = None
            st.session_state.pop("scheduler", None)
            st.session_state.chat_history = []
            st.rerun()

    # ── Tabs ──────────────────────────────────────────────────────
    tab_schedule, tab_advisor = st.tabs(["📅 Schedule", "🤖 AI Advisor"])

    # ==============================================================
    # TAB 1: Schedule (existing functionality)
    # ==============================================================
    with tab_schedule:

        # ── Add a Pet ─────────────────────────────────────────────
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
            pet_data = [
                {
                    "Name": p.name,
                    "Species": p.species,
                    "Age": p.age,
                    "Tasks": len(p.tasks),
                }
                for p in owner.pets
            ]
            st.table(pet_data)

        # ── Add Tasks ─────────────────────────────────────────────
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
                        "Duration (minutes)",
                        min_value=1,
                        max_value=240,
                        value=20,
                    )
                    start_time = st.text_input(
                        "Start time (HH:MM, optional)",
                        value="",
                        placeholder="e.g. 08:30",
                    )
                with col2:
                    priority = st.selectbox("Priority", ["high", "medium", "low"])
                    category = st.selectbox(
                        "Category",
                        ["walk", "feeding", "medication", "grooming", "enrichment"],
                    )
                    frequency = st.selectbox(
                        "Frequency", ["once", "daily", "weekly"]
                    )
                required = st.checkbox("Required (cannot be skipped)")
                add_task = st.form_submit_button("Add Task")
                if add_task and task_title:
                    pet = next(p for p in owner.pets if p.name == target_pet)
                    pet.add_task(
                        Task(
                            title=task_title,
                            duration_minutes=int(duration),
                            priority=priority,
                            category=category,
                            required=required,
                            start_time=start_time.strip(),
                            frequency=frequency,
                            due_date=(
                                date.today() if frequency != "once" else None
                            ),
                        )
                    )
                    st.rerun()

            # ── Task table (sorted by time) ───────────────────────
            all_tasks = owner.get_all_tasks()
            if all_tasks:
                scheduler_preview = Scheduler(owner)
                sorted_tasks = scheduler_preview.sort_by_time(all_tasks)
                task_rows = []
                for t in sorted_tasks:
                    tag = "REQUIRED" if t.required else t.priority
                    status = "Done" if t.completed else "Pending"
                    task_rows.append(
                        {
                            "Time": t.start_time or "—",
                            "Task": t.title,
                            "Pet": t.pet_name,
                            "Duration": f"{t.duration_minutes} min",
                            "Priority": tag,
                            "Frequency": t.frequency,
                            "Status": status,
                        }
                    )
                st.table(task_rows)
            else:
                st.info("No tasks yet. Add one above.")

            # ── Filter view ───────────────────────────────────────
            with st.expander("Filter tasks"):
                filter_col1, filter_col2 = st.columns(2)
                with filter_col1:
                    filter_pet = st.selectbox(
                        "By pet",
                        ["All"] + [p.name for p in owner.pets],
                        key="filter_pet",
                    )
                with filter_col2:
                    filter_status = st.selectbox(
                        "By status",
                        ["All", "Pending", "Completed"],
                        key="filter_status",
                    )

                filtered = all_tasks
                if filter_pet != "All":
                    filtered = [t for t in filtered if t.pet_name == filter_pet]
                if filter_status == "Pending":
                    filtered = [t for t in filtered if not t.completed]
                elif filter_status == "Completed":
                    filtered = [t for t in filtered if t.completed]

                if filtered:
                    for t in filtered:
                        tag = "REQUIRED" if t.required else t.priority
                        st.markdown(
                            f"- **{t.title}** ({t.pet_name}) — "
                            f"{t.duration_minutes} min · {tag}"
                        )
                else:
                    st.info("No tasks match the selected filters.")

        # ── Generate Schedule ─────────────────────────────────────
        st.divider()
        st.subheader("📅 Daily Schedule")

        if st.button("Generate Schedule"):
            if not owner.get_all_tasks():
                st.warning("Add at least one task before generating a schedule.")
            else:
                scheduler = Scheduler(owner)
                scheduler.generate_schedule()
                st.session_state.scheduler = scheduler

        if "scheduler" in st.session_state:
            scheduler = st.session_state.scheduler

            # Conflict warnings
            if scheduler.conflicts:
                for conflict in scheduler.conflicts:
                    st.warning(conflict)

            # Schedule table
            if scheduler.daily_plan:
                plan_rows = []
                for i, task in enumerate(scheduler.daily_plan, start=1):
                    tag = "REQUIRED" if task.required else task.priority
                    freq = task.frequency if task.frequency != "once" else ""
                    plan_rows.append(
                        {
                            "#": i,
                            "Time": task.start_time or "—",
                            "Task": task.title,
                            "Pet": task.pet_name,
                            "Duration": f"{task.duration_minutes} min",
                            "Type": tag,
                            "Repeat": freq,
                        }
                    )
                st.table(plan_rows)

                # Summary metrics
                total = sum(t.duration_minutes for t in scheduler.daily_plan)
                free = owner.available_time - total
                m1, m2, m3 = st.columns(3)
                m1.metric("Scheduled", f"{len(scheduler.daily_plan)} tasks")
                m2.metric("Time used", f"{total} min")
                m3.metric("Time free", f"{free} min")

                if free == 0:
                    st.info("Your day is fully booked!")
                elif free > 0:
                    st.success(
                        f"You have {free} minutes of free time remaining."
                    )
            else:
                st.info("No tasks could be scheduled.")

            # Skipped tasks
            if scheduler.skipped_tasks:
                with st.expander(
                    f"Skipped tasks ({len(scheduler.skipped_tasks)})"
                ):
                    for t in scheduler.skipped_tasks:
                        st.markdown(
                            f"- **{t.title}** ({t.pet_name}) — "
                            f"{t.duration_minutes} min — not enough time"
                        )

            # Reasoning
            with st.expander("Scheduling reasoning"):
                for reason in scheduler.reasoning:
                    st.markdown(f"- {reason}")

    # ==============================================================
    # TAB 2: AI Advisor (RAG-powered chat)
    # ==============================================================
    with tab_advisor:
        st.subheader("🤖 AI Pet Care Advisor")
        st.markdown(
            "Ask me anything about pet care — nutrition, health, grooming, "
            "exercise, training, or medication. I'll combine expert knowledge "
            "with your pets' profiles and schedule to give personalised advice."
        )

        advisor = st.session_state.advisor

        if advisor is None:
            st.warning(
                "**AI Advisor is unavailable.** Add your HuggingFace token "
                "to a `.env` file in the project root and restart the app.\n\n"
                "```\n"
                "HF_TOKEN=your-token-here\n"
                "```"
            )
        else:
            # Example questions
            with st.expander("Example questions to try"):
                st.markdown(
                    "- What should I feed my dog based on their age?\n"
                    "- Is my pet's exercise schedule sufficient?\n"
                    "- How often should I groom my cat?\n"
                    "- Are there any schedule conflicts I should worry about?\n"
                    "- What vaccinations does my puppy need?\n"
                    "- How do I give medication to a difficult cat?"
                )

            # Chat history display
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            # Chat input
            if question := st.chat_input("Ask about pet care..."):
                # Display user message
                with st.chat_message("user"):
                    st.markdown(question)
                st.session_state.chat_history.append(
                    {"role": "user", "content": question}
                )

                # Generate AI response
                with st.chat_message("assistant"):
                    with st.spinner("Searching knowledge base & generating advice..."):
                        logger.info("User question: %s", question[:100])
                        answer = advisor.ask(question, owner)
                    st.markdown(answer)
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": answer}
                )
