# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
- What classes did you include, and what responsibilities did you assign to each?

My initial UML design includes 4 main classes: Owner, Pet, Task, and Scheduler. The Owner class stores the owner's name, available time for the day, and care preferences, and holds a list of their pets. The Pet class represents each pet with attributes like name, species, and age, and holds a list of care tasks assigned to it. The Task class represents a single care activity (e.g. walking, feeding, medication) with a title, duration in minutes, priority level, and category. Finally, the Scheduler class is responsible for taking the owner's data, such as including all pets and their tasks, and producing a daily plan. It sorts and filters tasks by priority and fits them within the owner's available time, then explains the reasoning behind the generated schedule.

**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

Yes, the design changed after reviewing the skeleton. First, I added a `pet_name` field to the Task class because once all tasks are collected into a flat list for scheduling, there was no way to tell which pet a task belonged to — this is needed for displaying the plan clearly (e.g. "Walk — for Mochi"). Second, I added a `required` boolean to Task to distinguish mandatory tasks like medication from optional ones like enrichment, since priority alone does not capture whether a task can be skipped. Third, I added a `priority_value` property and a `PRIORITY_MAP` constant so the scheduler can sort tasks numerically instead of repeatedly converting priority strings. Finally, I added `skipped_tasks` and `reasoning` lists to the Scheduler class so it can track which tasks were dropped due to time constraints and log its decisions, which `explain_plan()` can then use directly instead of re-deriving the logic.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

The scheduler considers three main constraints: the owner's total available time (the hard budget), task priority (high/medium/low mapped to numeric values for sorting), and whether a task is marked as required (mandatory tasks like medication that cannot be skipped). It also considers start_time to detect conflicts and to sort the final plan chronologically. I decided that required tasks should always come first because missing medication or feeding has real consequences for the pet, whereas skipping a grooming session is just inconvenient. Time budget is the hard ceiling — once it's exhausted, remaining tasks are skipped regardless of priority.

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

The conflict detection algorithm only checks whether two consecutive timed tasks overlap (i.e. whether one task's end time exceeds the next task's start time). It does not check every possible pair of tasks against each other, and it cannot detect partial overlaps between non-adjacent tasks. This is a reasonable tradeoff because, in a typical pet care day, the number of tasks is small (under 20) and most conflicts occur between back-to-back activities. A full pairwise check would add complexity without meaningful benefit at this scale. The lightweight approach keeps the code simple and the output easy to read, while still catching the most common scheduling mistake — double-booking the same time slot.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

I used AI (Claude Code) throughout every phase of the project: brainstorming class attributes during initial UML design, reviewing the skeleton for missing relationships and bottlenecks, implementing the full scheduling logic, writing the test suite, and polishing the Streamlit UI. The most effective prompts were ones that asked the AI to review existing code and identify problems — for example, "review the skeleton and find missing relationships or logic bottlenecks" surfaced four concrete issues (no pet_name on Task, no required flag, string-based priority sorting, no reasoning log) that significantly improved the design. Using separate chat sessions for different phases (design, implementation, testing, UI) helped keep each conversation focused and prevented context from earlier phases from biasing later decisions.

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

When the AI initially suggested the skeleton with 4 classes, it included a `Constraints` class as a separate entity. I chose to reject that and instead fold constraints (required flag, time budget, priority) into the existing Task and Scheduler classes, because a separate Constraints class would have added indirection without clear benefit — the scheduler already needs to know about priorities and time, so those belong where the decisions are made. I evaluated this by thinking through what the Constraints class would actually hold versus what the Scheduler already handles, and concluded it would just be a pass-through with no logic of its own.

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

I tested 26 behaviors across 7 test groups: task completion toggling, task addition/removal on pets, required-first scheduling with time-budget enforcement, chronological sorting by start_time, filtering by pet name and completion status, daily and weekly recurrence logic (including attribute preservation on the next occurrence), conflict detection for overlapping and same-start-time tasks, and a full set of edge cases — pet with no tasks, owner with no pets, zero available time, task that exactly fills the budget, already-completed tasks excluded from the plan, safe removal of nonexistent tasks, un-timed tasks sorted to the end, and multi-pet task interleaving. These tests were important because they verify both the "happy path" (normal usage) and the boundary conditions where bugs are most likely to hide.

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

I am fairly confident (4 out of 5) in the scheduler's correctness. The 26-test suite covers all core behaviors, recurrence logic, and conflict detection, and every test passes consistently. If I had more time, I would add tests for invalid inputs (e.g. malformed start_time strings like "25:99"), extremely large task counts to check performance, and edge cases around weekly recurrence spanning month or year boundaries.

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

I am most satisfied with the iterative design process — starting with a simple 4-class skeleton, then systematically reviewing it for gaps (pet_name, required, reasoning log), adding algorithmic features (sorting, filtering, recurrence, conflict detection), and verifying each addition with targeted tests. The final scheduler is more capable than what I initially planned, but every addition was driven by a concrete need rather than speculation.

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

I would redesign the conflict detection to handle full duration overlaps rather than only checking consecutive tasks. I would also add input validation (e.g. rejecting malformed start_time strings), a way to edit or reorder tasks in the UI, and persistent storage so the owner's data survives across browser sessions.

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?

The most important lesson was that AI is most useful when you treat it as a reviewer and collaborator rather than a code generator. The highest-value moments were when I asked the AI to critique my existing design and identify what was missing — that produced better results than asking it to generate code from scratch, because the review was grounded in concrete code rather than abstract requirements. Being the "lead architect" means making the final call on what to keep, what to reject, and why — the AI proposes, but the human decides.
