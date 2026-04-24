# PawPal+ Model Card

This model card documents the AI components of **PawPal+**, the applied AI system extension of the PawPal pet care scheduler from Modules 1–3. It covers what the system does, how it was built with AI assistance, where its limits and biases are, and what testing showed.

---

## 1. System Overview

| Field | Value |
|---|---|
| **Project name** | PawPal+ |
| **Base project (Modules 1–3)** | PawPal — a Python/Streamlit pet care scheduler with `Owner`, `Pet`, `Task`, and `Scheduler` classes that produces a daily plan from priority + time-budget constraints. |
| **New AI feature (Module 4)** | RAG-powered Pet Care Advisor with an **agentic reasoning chain** (planner → tools → synthesizer → critic), **few-shot specialization** of the system prompt, and a **baseline-vs-specialized evaluation harness**. TF-IDF retrieval over a 6-document pet-care knowledge base is combined with live app state (pets, tasks, schedule) and sent to an LLM for personalized advice. |
| **Underlying model** | `meta-llama/Llama-3.1-8B-Instruct` via the HuggingFace Inference API |
| **Retrieval model** | scikit-learn `TfidfVectorizer` (1–2 grams, English stop-words, max 5000 features) + cosine similarity |
| **Intended use** | Educational / hobby pet-care planning. Helps a single household owner plan daily pet care and ask grounded follow-up questions about routine care. |
| **Out of scope** | Veterinary diagnosis, emergency triage, dosing decisions, exotic species, anything outside routine domestic dog/cat care. |

---

## 2. AI Collaboration

### a. How I used AI during development

I used GitHub Copilot and Claude Code throughout the project, but in different modes for different phases:

- **Design (Modules 1–3):** Brainstorming class attributes for the original UML, then asking the model to *review* the skeleton and surface missing relationships. That review pass produced four concrete improvements I would have otherwise missed (`pet_name` on `Task`, a `required` flag, a numeric priority map, a `reasoning` log on `Scheduler`).
- **Implementation:** Copilot Agent Mode for multi-file edits (wiring `pawpal_system.py` ↔ `app.py`), Inline Chat for targeted method work (the lambda key for sorting `"HH:MM"` strings).
- **Testing:** "Generate Tests" for scaffolding, then I expanded each group with edge cases by hand.
- **Module 4 RAG extension:** Claude Code helped me lay out the pipeline (validate → retrieve → augment → generate → validate output) before I wrote any code, and helped debug the chunking heuristic when small fragments were polluting retrieval.

I deliberately used **separate chat sessions** for design / implementation / testing so the model couldn't carry biased assumptions from one phase into the next.

### b. One helpful AI suggestion

When designing the knowledge base, the model suggested organizing documents by **topic** (`nutrition.md`, `health.md`, `grooming.md`, …) rather than by **species** (`dog_guide.md`, `cat_guide.md`). This was the right call: a query like "dog grooming" now retrieves `grooming.md` and gets both species-specific and general grooming content, rather than dragging in unrelated dog material. Retrieval evals (see §4) confirm the topic split lets queries hit the correct source consistently.

### c. One flawed AI suggestion

The model initially recommended a vector database (ChromaDB) with sentence-transformer embeddings for retrieval. I rejected it. Sentence-transformers pulls in `torch` and `transformers` (~2 GB of dependencies), which would have made the project meaningfully harder to install and run reproducibly, especially on a CPU-only laptop. For keyword-rich pet care queries, TF-IDF is accurate enough — the eval suite shows 6/6 source-routing tests pass — and installs in seconds. The tradeoff is that purely *semantic* queries ("my pet seems sad") may retrieve weakly; that's acceptable for the project's scope.

### d. Where I exercised judgment over the AI

The model's first skeleton included a separate `Constraints` class. I removed it: it would have been a pass-through with no logic, since the `Scheduler` already knows about priorities, required flags, and time budgets. I evaluated this by asking what code the `Constraints` class would actually contain, and the answer was "nothing the scheduler doesn't already do." Indirection without behavior is just noise.

---

## 3. Biases, Limitations, and Risks

### a. Data biases

The knowledge base is six markdown documents I wrote myself, drawing on general pet-care references. Known biases:

- **Species coverage skews toward dogs and cats.** "Other" species (rabbits, reptiles, birds) are barely covered. A user asking about a parrot will get TF-IDF matches that are technically related but semantically off.
- **Adult-pet bias.** Most guidance assumes a healthy adult dog or cat. Senior, puppy/kitten, and special-needs cases are present but thinner.
- **Western pet-care norms.** Recommendations (vaccination schedules, feeding portions, veterinary visit frequency) reflect mainstream US/EU practices.

### b. Model-level biases and risks

- The Llama-3.1-8B model can hallucinate plausible-sounding pet care facts. The system prompt asks it to refuse when retrieval doesn't cover the question, but this is a soft constraint, not a hard one.
- **Dosage hallucination is the highest-impact risk.** A wrong medication dose is materially harmful. The output guardrail uses a regex (`\b(give|administer|dose|take)\b ... \b\d+\s*(mg|ml|cc|tablet|pill|capsule)\b`) to detect dosage-shaped strings and append a vet-consult disclaimer. The guardrail is intentionally additive (it adds a warning, never edits the response) so the user always sees the original text plus the warning.
- **Topic-drift risk.** The keyword-based topic filter can be tricked by a pet-shaped wrapper around an off-topic question ("My dog asked me what stocks to buy"). It's a basic guardrail, not adversarial-robust.

### c. Operational limitations

- TF-IDF retrieval is keyword-dependent. Vague semantic queries ("my pet is acting weird") retrieve weakly compared to keyword-rich ones ("dog vomiting symptoms").
- No conversation memory — each question is independent. A follow-up like "and for cats?" loses context.
- The knowledge base is static. Updating it requires editing markdown files and restarting the app.
- Single-user, single-process. There is no auth, persistence, or multi-tenant isolation.

### d. What this system should **not** be used for

- Veterinary diagnosis or emergencies — the system tells the user to consult a vet, but it should not be relied on as a substitute.
- Calculating medication doses for a specific pet.
- Care decisions for exotic species not represented in the knowledge base.

---

## 4. Testing and Evaluation Results

The system has two layers of automated testing.

### a. `pytest` unit/integration suite — 48 tests, all passing

Organized into 12 groups covering both the original scheduler (Modules 1–3) and the new RAG layer (Module 4):

| Group | Coverage |
|---|---|
| `TestTaskCompletion`, `TestTaskAddition`, `TestScheduler`, `TestSortingAndFiltering`, `TestRecurringTasks`, `TestConflictDetection`, `TestEdgeCases` | Original scheduler — completion toggles, add/remove, required-first scheduling, time-budget enforcement, chronological sort, filters, daily/weekly recurrence, overlap detection, edge cases (zero time, exact-fit, completed exclusion, multi-pet interleaving). |
| `TestKnowledgeBaseLoading` | Loads all six markdown files; handles missing/empty directories gracefully. |
| `TestChunking` | Splits on headings, drops chunks under 30 chars, preserves source metadata. |
| `TestRetrieval` | Returns relevant chunks, respects `top_k`, handles empty index and irrelevant queries. |
| `TestContextBuilding` | Builds pet/schedule context strings from live `Owner` state. |
| `TestAdvisorInit` | Initializes with/without API key; verifies API call structure. |

### b. `eval_rag.py` evaluation harness — 23/23 passing (no API key required)

A standalone script that prints a pass/fail summary for retrieval quality and guardrail behavior, plus optional end-to-end tests that hit the live API.

```
PawPal+ RAG Evaluation
==================================================
=== Retrieval Quality ===
  [PASS] Knowledge base loads — 104 chunks
  [PASS] Dog nutrition query retrieves nutrition.md
  [PASS] Cat grooming query retrieves grooming.md
  [PASS] Vaccination query retrieves health.md
  [PASS] Exercise query retrieves exercise.md
  [PASS] Medication query retrieves medication.md
  [PASS] Training query retrieves training.md
  [PASS] Format context produces non-empty string — 2814 chars
=== Guardrails ===
  [PASS] Empty input rejected
  [PASS] Too-short input rejected
  [PASS] Oversized input rejected
  [PASS] Valid input accepted
  [PASS] On-topic: 'What should I feed my puppy?...'
  [PASS] On-topic: 'How often to groom a cat?...'
  [PASS] On-topic: 'Is my dog's exercise schedule enough?...'
  [PASS] On-topic: 'When should I give heartworm medic...'
  [PASS] Off-topic blocked: 'What is the capital of France?...'
  [PASS] Off-topic blocked: 'How do I fix a segmentation fault...'
  [PASS] Off-topic blocked: 'Write me a poem about the moon...'
  [PASS] Off-topic blocked: 'What stocks should I buy?...'
  [PASS] Safe output unchanged
  [PASS] Dosage triggers vet disclaimer
  [PASS] Long output truncated
==================================================
RESULTS: 23/23 passed, 0 failed
```

### c. What worked

- **Source-routing accuracy is reliable.** All six topic-routing queries hit the correct source on the first try. The topic-organized knowledge base structure is the main reason — TF-IDF latches onto the topic-specific vocabulary (`vaccination`, `grooming`, `heartworm`) directly.
- **Guardrails compose cleanly.** Stacking input validation → topic filter → retrieval → output validation means each layer can be tested independently.
- **Live app context substantially improves answers.** Asking "What should I feed Mochi?" pulls Mochi's age and species from `Owner` state into the prompt, and the response references both — confirmed in end-to-end tests.

### d. What didn't work / what surprised me

- **My first chunking heuristic produced too many tiny chunks** (single bullets, broken lists). Dropping chunks under 30 chars and adding 100-char overlap fixed it; chunk count dropped from ~180 noisy chunks to 104 useful ones with no loss in retrieval coverage.
- **The keyword topic filter occasionally false-rejects legitimate questions** that don't include any of the allowed-topic words but are clearly pet-related (e.g., "Can he eat grapes?"). This is a known limitation; an embedding-based classifier would be more robust.
- **Dosage regex is conservative.** It triggers on phrasings like "give 2 tablets" even when the model is just citing a label, appending the disclaimer. I prefer this false-positive direction — the warning is harmless when unnecessary, dangerous when missing.

### e. What I learned

The single biggest lesson: **AI is most useful as a reviewer, not a generator**. The highest-leverage moments in this project came from asking the model to critique my existing code and design (the skeleton review, the chunking debug session). Code generated from a blank prompt was usually serviceable but generic; code produced by reviewing what I'd already written was specific and pointed at real problems. Being the "lead architect" means deciding what advice to take and why — the model proposes, I dispose.

The second lesson is about guardrails: **layered, additive guardrails are easier to reason about than a single smart one.** Each layer in `ai_advisor.py` (`validate_input`, `check_topic_relevance`, `validate_output`) is dumb on its own and easy to test, but together they cover a meaningful surface area without anyone layer being load-bearing.

---

## 4b. Agentic Workflow (observable multi-step reasoning)

The `PetCareAgent` in [agent.py](agent.py) implements a real agentic chain — not just a pipeline. Every step is recorded as a `TraceStep` and exposed both programmatically (`AgentResult.trace`) and in the Streamlit UI (expandable panel under each response).

**Pipeline:**
1. **Plan** — the LLM is shown the four available tools (`retrieve_knowledge`, `get_pet_profiles`, `get_schedule`, `get_conflicts`) and asked to emit a JSON plan. A tolerant parser extracts the first `{…}` block and a heuristic fallback kicks in if the JSON is malformed or names an unknown tool, so the chain never crashes on a bad plan.
2. **Execute** — each selected tool is called deterministically (no LLM). Tool outputs become observations.
3. **Synthesize** — the LLM is given the question + observations and produces a draft answer, constrained by the specialized system prompt.
4. **Critique** — a heuristic groundedness check flags empty/too-short answers, answers that ignore a retrieved pet profile, and answers with weak token overlap against retrieved knowledge. This is deliberately structural (not another LLM call) so happy-path questions cost one planner call + one synthesizer call.
5. **Revise** — only when the critic flags issues, a single-shot revision call is made with the critic's feedback. The trace records whether a revision happened (`AgentResult.revised`).

**Observability:** each step has a `name`, `summary`, and `detail`, so the full reasoning chain can be replayed after the fact. The UI expander label shows something like `Agent trace — 6 steps, tools: ['retrieve_knowledge', 'get_schedule'] (revised)` — you know what the agent decided, what tools it ran, and whether the critic forced a second pass.

## 4c. Specialization (few-shot + baseline comparison)

The system prompt in [ai_advisor.py](ai_advisor.py) contains:
- **Explicit style rules** — named pet opening, 3–6 bullets, schedule tie-in, vet-consult closing for medical questions.
- **Three in-context few-shot examples** — adult dog nutrition, senior cat health, off-topic redirect — so the model sees the exact format rather than inferring it from rules alone.

[eval_specialization.py](eval_specialization.py) demonstrates the difference in two modes:

- **Offline structural diff** (no API key): confirms the specialized prompt is ~55× the baseline length, contains few-shot examples, enforces the bullet and vet-disclaimer rules, and references the schedule — all absent from the baseline prompt. 6/6 checks pass.
- **Live API comparison** (`--full`, needs HF_TOKEN): runs the same three questions through the generic-prompt baseline and the full specialized pipeline. Computes per-question metrics — length, bullet count, pet-name references, vet-disclaimer presence, schedule references, retrieved-source attribution — and counts structural wins/losses. The specialized pipeline wins on named references and bullet structure (the baseline can't see the pet), and on vet disclaimers for dosage questions (the specialized prompt requires them).

## 5. Future Improvements

- Replace TF-IDF with sentence-transformer embeddings if the knowledge base grows beyond ~20 documents — the dependency cost becomes worth it at that scale.
- Add conversation memory so follow-up questions retain context.
- Allow users to upload their own vet documents into the knowledge base.
- Add a per-response confidence score derived from top-k retrieval similarity, so users see when the AI is on shaky ground.
- Replace the keyword topic filter with a small embedding classifier to handle on-topic-but-keyword-poor questions.
- Persist owner/pet/task state across sessions (currently lost on browser refresh).
