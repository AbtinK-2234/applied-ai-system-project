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

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
