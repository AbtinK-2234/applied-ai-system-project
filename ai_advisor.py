"""
AI Pet Care Advisor for PawPal+

Combines RAG-retrieved pet care knowledge with the user's live pet/schedule
data and calls the HuggingFace Inference API to generate personalized advice.

Includes guardrails for input validation, topic relevance, and output safety.
"""

import logging
import os
import re
from dataclasses import dataclass, field

from huggingface_hub import InferenceClient

from pawpal_system import Owner, Scheduler
from rag_engine import RAGEngine

logger = logging.getLogger(__name__)

MODEL = "meta-llama/Llama-3.1-8B-Instruct"
MAX_TOKENS = 1024
MAX_QUESTION_LENGTH = 500
MIN_QUESTION_LENGTH = 3

# Topics the advisor is allowed to answer about
ALLOWED_TOPICS = [
    "pet", "dog", "cat", "puppy", "kitten", "animal",
    "food", "feed", "nutrition", "diet", "eat", "meal", "treat", "water",
    "health", "vet", "vaccine", "sick", "symptom", "disease", "medicine",
    "medication", "pill", "supplement", "flea", "tick", "heartworm",
    "groom", "brush", "bath", "nail", "fur", "coat", "shed",
    "exercise", "walk", "play", "run", "swim", "agility", "enrichment",
    "train", "behavior", "bark", "bite", "scratch", "litter",
    "schedule", "task", "time", "plan", "routine", "conflict",
    "care", "breed", "age", "weight", "senior", "puppy",
]

SYSTEM_PROMPT = """\
You are PawPal+ AI Advisor, an expert pet care assistant embedded in a pet care \
scheduling app. You give helpful, accurate, and personalized advice about pet \
nutrition, health, grooming, exercise, training, and medication.

Rules:
- Base your answers on the retrieved knowledge provided below. If the knowledge \
does not cover the question, say so honestly rather than guessing.
- Personalize your advice using the owner's pet profiles and schedule context.
- Be concise but thorough. Use bullet points when listing recommendations.
- If a question involves a medical emergency or serious health concern, always \
recommend consulting a veterinarian.
- Never recommend specific medication dosages — defer to the owner's veterinarian.
- Stay strictly on-topic: only answer questions related to pet care, pet health, \
pet scheduling, and related topics. If the question is unrelated, politely decline.
- Do NOT provide advice on human medical issues, financial advice, or any topic \
outside pet care.

Specialized response style — follow this format every time:
1. Open by addressing the specific pet by name when a profile is available, \
and acknowledge a relevant detail (age, species, scheduled task).
2. Use a short bullet list (3–6 bullets) for the actual recommendations.
3. When relevant, tie at least one bullet back to the owner's actual schedule.
4. End with a closing line — for medical or dosage questions, the closing line \
must explicitly recommend consulting a veterinarian.

Few-shot examples of the expected style:

[Example A — nutrition for a young adult dog]
Question: "What should I feed Mochi?"
Pet profile: Mochi, dog, age 3. Morning walk scheduled at 08:00.
Answer:
"For Mochi (a 3-year-old adult dog), here is what I'd recommend:
- Two meals per day works well for adult dogs at this stage
- Aim for 18–25% protein and 10–15% fat in the daily diet
- Adjust portion size to body weight — most medium dogs need 1–2 cups of dry food daily
- Use small high-value treats during your 08:00 walk for training reinforcement
- Keep fresh water available at all times
For weight-specific portions, your veterinarian can give the most accurate target."

[Example B — senior cat health]
Question: "Whiskers is 10. What should I watch for?"
Pet profile: Whiskers, cat, age 10. Evening feeding at 18:00.
Answer:
"For Whiskers, who is now in the senior cat range, the things to watch for are:
- Changes in water intake or litter-box habits — early sign of kidney issues
- Weight loss or appetite drop, especially around the 18:00 feeding
- Stiffness when jumping or climbing — a marker for arthritis
- Dental discomfort, which can show up as eating slowly or dropping food
- Any new lumps or behavioral shifts
A senior wellness check at your vet (typically every 6–12 months) is the best way to catch these early."

[Example C — off-topic redirect]
Question: "What stocks should I buy?"
Answer:
"I'm the PawPal+ Pet Care Advisor — I can only help with pet-related topics like nutrition, health, grooming, exercise, training, and scheduling. Could you rephrase your question to be about your pet?"
"""


# ── Guardrails ────────────────────────────────────────────────────


def validate_input(question: str) -> str | None:
    """Validate user input. Returns an error message or None if valid."""
    if not question or not question.strip():
        return "Please enter a question."

    question = question.strip()
    if len(question) < MIN_QUESTION_LENGTH:
        return "Your question is too short. Please provide more detail."

    if len(question) > MAX_QUESTION_LENGTH:
        return (
            f"Your question is too long ({len(question)} characters). "
            f"Please keep it under {MAX_QUESTION_LENGTH} characters."
        )

    return None


def check_topic_relevance(question: str) -> bool:
    """Check whether the question is related to pet care topics.

    Returns True if the question appears relevant, False otherwise.
    """
    question_lower = question.lower()
    return any(topic in question_lower for topic in ALLOWED_TOPICS)


OFF_TOPIC_RESPONSE = (
    "I'm the PawPal+ Pet Care Advisor, and I can only help with pet-related "
    "questions — things like nutrition, health, grooming, exercise, training, "
    "medication, and scheduling. Could you rephrase your question to be about "
    "your pet's care?"
)


def validate_output(response: str) -> str:
    """Post-process the AI response to enforce output safety guardrails.

    - Strips any excessively long responses
    - Redacts patterns that look like dosage recommendations
    """
    # Truncate overly long responses
    if len(response) > 3000:
        response = response[:3000].rsplit(".", 1)[0] + "."
        response += (
            "\n\n*[Response truncated for brevity. "
            "Please ask a more specific follow-up question.]*"
        )
        logger.warning("Response truncated from >3000 chars")

    # Flag specific dosage patterns (e.g., "give 10mg", "administer 5ml")
    dosage_pattern = r"\b(give|administer|dose|take)\b.{0,20}\b\d+\s*(mg|ml|cc|tablet|pill|capsule)\b"
    if re.search(dosage_pattern, response, re.IGNORECASE):
        response += (
            "\n\n**Important:** The dosage information above is for general "
            "reference only. Always consult your veterinarian for the correct "
            "dosage for your specific pet."
        )
        logger.info("Dosage guardrail triggered — disclaimer appended")

    return response


# ── Context builders ──────────────────────────────────────────────


def _build_pet_context(owner: Owner) -> str:
    """Summarize the owner's pets and current tasks for the LLM."""
    if not owner.pets:
        return "The owner has not added any pets yet."

    lines = [f"Owner: {owner.name} (available time: {owner.available_time} min/day)"]
    for pet in owner.pets:
        lines.append(f"\nPet: {pet.name} ({pet.species}, age {pet.age})")
        if pet.tasks:
            for t in pet.tasks:
                status = "done" if t.completed else "pending"
                time_str = t.start_time if t.start_time else "unscheduled"
                lines.append(
                    f"  - {t.title} | {t.duration_minutes}min | "
                    f"{t.priority} priority | {t.category} | "
                    f"{t.frequency} | {time_str} | {status}"
                )
        else:
            lines.append("  (no tasks yet)")
    return "\n".join(lines)


def _build_schedule_context(owner: Owner) -> str:
    """Run the scheduler and summarize the generated plan."""
    scheduler = Scheduler(owner)
    plan = scheduler.generate_schedule()
    if not plan:
        return "No schedule has been generated yet (no pending tasks)."

    lines = ["Current schedule:"]
    for t in plan:
        time_str = t.start_time if t.start_time else "flex"
        req = "REQUIRED" if t.required else "optional"
        lines.append(
            f"  {time_str} - {t.title} ({t.pet_name}) "
            f"[{t.duration_minutes}min, {req}]"
        )
    if scheduler.conflicts:
        lines.append("\nConflicts detected:")
        for c in scheduler.conflicts:
            lines.append(f"  ⚠ {c}")
    if scheduler.skipped_tasks:
        lines.append("\nSkipped (not enough time):")
        for t in scheduler.skipped_tasks:
            lines.append(f"  - {t.title} ({t.pet_name})")
    return "\n".join(lines)


# ── AI Advisor ────────────────────────────────────────────────────


@dataclass
class AIAdvisor:
    """RAG-powered pet care advisor using HuggingFace Inference API with guardrails."""

    rag: RAGEngine = field(default_factory=RAGEngine)
    _client: InferenceClient | None = field(default=None, repr=False)
    _initialised: bool = field(default=False, repr=False)

    def initialise(self) -> bool:
        """Load the knowledge base and set up the HuggingFace client.

        Returns True if initialisation succeeded.
        """
        api_key = os.environ.get("HF_TOKEN", "")
        if not api_key:
            logger.error(
                "HF_TOKEN environment variable is not set. "
                "AI Advisor requires a valid HuggingFace token."
            )
            return False

        n_chunks = self.rag.load_knowledge_base()
        if n_chunks == 0:
            logger.error("Knowledge base is empty — AI Advisor cannot start.")
            return False

        self._client = InferenceClient(api_key=api_key)
        self._initialised = True
        logger.info("AI Advisor initialised (%d knowledge chunks)", n_chunks)
        return True

    @property
    def is_ready(self) -> bool:
        return self._initialised

    def ask(self, question: str, owner: Owner) -> str:
        """Answer a pet care question using RAG + live app context.

        Pipeline:
        1. Validate input (guardrail)
        2. Check topic relevance (guardrail)
        3. Retrieve relevant knowledge chunks
        4. Build context from the owner's pets and schedule
        5. Call HuggingFace Inference API with the combined prompt
        6. Validate output (guardrail)
        """
        if not self._initialised:
            return (
                "AI Advisor is not initialised. Please set the HF_TOKEN "
                "environment variable and restart the app."
            )

        # --- Guardrail: input validation ---
        input_error = validate_input(question)
        if input_error:
            logger.warning("Input validation failed: %s", input_error)
            return input_error

        # --- Guardrail: topic relevance ---
        if not check_topic_relevance(question):
            logger.info("Off-topic question blocked: %s", question[:80])
            return OFF_TOPIC_RESPONSE

        # --- Retrieve ---
        logger.info("Processing question: %s", question[:100])
        retrieved_chunks = self.rag.retrieve(question)
        knowledge_context = self.rag.format_context(retrieved_chunks)
        sources = list({c.source for c in retrieved_chunks})
        logger.info("Retrieved %d chunks from: %s", len(retrieved_chunks), sources)

        # --- Augment: combine knowledge + live app data ---
        pet_context = _build_pet_context(owner)
        schedule_context = _build_schedule_context(owner)

        user_message = self._build_user_message(
            question, knowledge_context, pet_context, schedule_context
        )

        # --- Generate ---
        try:
            response = self._client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=MAX_TOKENS,
            )
            answer = response.choices[0].message.content
            logger.info(
                "Generated response (%d chars, %d input tokens, %d output tokens)",
                len(answer),
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )

            # --- Guardrail: output validation ---
            answer = validate_output(answer)

            return answer

        except Exception as e:
            error_str = str(e).lower()
            if "auth" in error_str or "token" in error_str or "401" in error_str:
                logger.error("Invalid HF_TOKEN")
                return "Error: Invalid token. Please check your HF_TOKEN."
            elif "429" in error_str or "rate" in error_str:
                logger.warning("Rate limited by HuggingFace API")
                return "The AI service is temporarily busy. Please try again in a moment."
            else:
                logger.exception("HuggingFace API error")
                return "An error occurred while contacting the AI service. Please try again."

    @staticmethod
    def _build_user_message(
        question: str,
        knowledge_context: str,
        pet_context: str,
        schedule_context: str,
    ) -> str:
        """Assemble the full user message sent to the LLM."""
        parts = [f"## Question\n{question}"]

        if knowledge_context:
            parts.append(
                f"## Retrieved Pet Care Knowledge\n{knowledge_context}"
            )
        else:
            parts.append(
                "## Retrieved Pet Care Knowledge\n"
                "No directly relevant knowledge was found in the database for this "
                "question. Answer based on general pet care principles and clearly "
                "note when you are not drawing from the knowledge base."
            )

        parts.append(f"## Owner's Pets and Tasks\n{pet_context}")
        parts.append(f"## Current Schedule\n{schedule_context}")

        return "\n\n".join(parts)

    # ── Agentic mode ──────────────────────────────────────────────

    def ask_with_agent(self, question: str, owner: Owner):
        """Run the question through the agentic workflow.

        Returns an AgentResult with `.answer`, `.trace`, `.tools_called`, and
        `.revised`. The same input/topic guardrails as `ask()` apply before
        the agent runs, and `validate_output` runs on the final answer.
        """
        from agent import PetCareAgent, AgentResult

        if not self._initialised:
            return AgentResult(
                answer=(
                    "AI Advisor is not initialised. Please set the HF_TOKEN "
                    "environment variable and restart the app."
                )
            )

        input_error = validate_input(question)
        if input_error:
            logger.warning("Input validation failed: %s", input_error)
            return AgentResult(answer=input_error)

        if not check_topic_relevance(question):
            logger.info("Off-topic question blocked: %s", question[:80])
            return AgentResult(answer=OFF_TOPIC_RESPONSE)

        try:
            agent = PetCareAgent(rag=self.rag, client=self._client, model=MODEL)
            result = agent.run(question, owner)
            result.answer = validate_output(result.answer)
            return result
        except Exception as e:
            error_str = str(e).lower()
            if "auth" in error_str or "token" in error_str or "401" in error_str:
                logger.error("Invalid HF_TOKEN")
                return AgentResult(answer="Error: Invalid token. Please check your HF_TOKEN.")
            elif "429" in error_str or "rate" in error_str:
                logger.warning("Rate limited by HuggingFace API")
                return AgentResult(
                    answer="The AI service is temporarily busy. Please try again in a moment."
                )
            else:
                logger.exception("Agent run failed")
                return AgentResult(
                    answer="An error occurred while running the agent. Please try again."
                )
