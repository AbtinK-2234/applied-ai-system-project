"""
PetCareAgent — agentic workflow for PawPal+

A multi-step reasoning chain with planning, tool calls, synthesis, and
self-critique. Every intermediate step is recorded in a trace so the user
can see what the agent decided to do and why.

Pipeline:
    1. PLAN     — LLM picks which tools to call (JSON output)
    2. EXECUTE  — deterministic tool dispatch, gathers observations
    3. SYNTHESIZE — LLM drafts answer from observations
    4. CRITIQUE — heuristic groundedness check + optional LLM critique
    5. REVISE   — one-shot revision if critique flags issues
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from huggingface_hub import InferenceClient

from pawpal_system import Owner, Scheduler
from rag_engine import RAGEngine

logger = logging.getLogger(__name__)


# ── Tool registry ─────────────────────────────────────────────────


TOOL_DESCRIPTIONS = {
    "retrieve_knowledge": (
        "Retrieve relevant pet care knowledge from the knowledge base. "
        "Argument: a sub-query string. Use for nutrition, health, grooming, "
        "exercise, training, or medication facts."
    ),
    "get_pet_profiles": (
        "Get the owner's pets and their tasks. No arguments. "
        "Use when the question references a specific pet, age, species, "
        "or 'my pet'."
    ),
    "get_schedule": (
        "Get the freshly-generated daily schedule. No arguments. "
        "Use when the question is about today's plan, time budget, "
        "or what's scheduled."
    ),
    "get_conflicts": (
        "Get scheduling conflicts and skipped tasks. No arguments. "
        "Use when the question is about overlaps, missed tasks, or "
        "schedule problems."
    ),
}

VALID_TOOLS = set(TOOL_DESCRIPTIONS.keys())


# ── Trace & result types ──────────────────────────────────────────


@dataclass
class TraceStep:
    """A single observable step in the agent's reasoning chain."""
    name: str          # "plan", "tool:retrieve_knowledge", "synthesize", ...
    summary: str       # one-line human-readable summary
    detail: str = ""   # full content for expanders / logs

    def render(self) -> str:
        out = f"**{self.name}** — {self.summary}"
        if self.detail:
            out += f"\n```\n{self.detail}\n```"
        return out


@dataclass
class AgentResult:
    """Everything the agent produced for one question."""
    answer: str
    trace: list[TraceStep] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    revised: bool = False


# ── Prompts ───────────────────────────────────────────────────────


PLANNER_PROMPT = """\
You are the planner for the PawPal+ pet care agent. Your job is to decide \
which tools the agent should call to answer the user's question.

Available tools:
{tool_list}

Rules:
- Always call `retrieve_knowledge` for pet-care factual questions.
- Call `get_pet_profiles` when the question mentions a pet by name, references \
"my dog", "my pet", or asks about age/species/breed.
- Call `get_schedule` when the question is about today's plan, walks, feeding \
times, or anything related to "the schedule".
- Call `get_conflicts` when the question mentions conflicts, overlaps, missed \
tasks, or "is my schedule okay".
- You may call between 1 and 4 tools. Do not duplicate tools.

Output strictly valid JSON in this exact shape:
{{"tools": [{{"name": "<tool_name>", "argument": "<string or empty>"}}], \
"reasoning": "<one-sentence why>"}}
"""

SYNTHESIZER_PROMPT = """\
You are PawPal+ AI Advisor. Use ONLY the observations below to answer the \
user's question. If an observation is missing, say so honestly — do not guess.

Style:
- Open by addressing the specific pet by name when the profile is provided.
- Use bullet points for recommendations.
- Reference the owner's actual schedule when relevant.
- For medical or dosage questions, defer to the veterinarian explicitly.
- Keep the answer focused — under 350 words.
"""

CRITIC_PROMPT = """\
You are the critic for the PawPal+ agent. Read the question, the observations, \
and the draft answer. Output strictly valid JSON:
{"verdict": "OK" | "REVISE", "issues": "<one-sentence reason if REVISE, else empty>"}

Flag REVISE only if:
- The answer contradicts the observations.
- The answer makes up facts not present in the observations.
- The answer ignores a pet that was clearly referenced in the question.
Otherwise output OK.
"""


# ── Agent ─────────────────────────────────────────────────────────


@dataclass
class PetCareAgent:
    """Multi-step pet-care agent with tool calls, planning, and self-critique."""

    rag: RAGEngine
    client: InferenceClient
    model: str = "meta-llama/Llama-3.1-8B-Instruct"
    max_tokens: int = 1024
    enable_critic: bool = True

    # ── Public entrypoint ─────────────────────────────────────────

    def run(self, question: str, owner: Owner) -> AgentResult:
        """Run the full agentic pipeline on one question."""
        result = AgentResult(answer="")

        # Step 1: PLAN
        plan = self._plan(question, owner, result)

        # Step 2: EXECUTE
        observations = self._execute(plan, owner, result)

        # Step 3: SYNTHESIZE
        draft = self._synthesize(question, observations, result)

        # Step 4: CRITIQUE
        verdict, issues = self._critique(question, observations, draft, result)

        # Step 5: REVISE (if needed)
        if verdict == "REVISE":
            draft = self._revise(question, observations, draft, issues, result)
            result.revised = True

        result.answer = draft
        return result

    # ── Step 1: planner ───────────────────────────────────────────

    def _plan(
        self, question: str, owner: Owner, result: AgentResult
    ) -> list[dict[str, str]]:
        """Ask the LLM to pick tools. Falls back to a heuristic if parsing fails."""
        tool_list = "\n".join(
            f"  - {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items()
        )
        prompt = PLANNER_PROMPT.format(tool_list=tool_list)

        owner_summary = self._owner_summary(owner)
        user_msg = (
            f"Question: {question}\n\n"
            f"Owner context: {owner_summary}\n\n"
            "Output the JSON plan now."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=300,
            )
            raw = response.choices[0].message.content.strip()
            plan = self._parse_plan(raw)
            reasoning = plan.get("reasoning", "(no reasoning)")
            tools = plan.get("tools", [])
            valid_tools = [
                t for t in tools
                if isinstance(t, dict) and t.get("name") in VALID_TOOLS
            ]
            if not valid_tools:
                logger.warning("Planner returned no valid tools — falling back")
                valid_tools = self._fallback_plan(question)
                reasoning = "fallback heuristic (planner output invalid)"
        except Exception:
            logger.exception("Planner LLM call failed — using heuristic fallback")
            valid_tools = self._fallback_plan(question)
            reasoning = "fallback heuristic (planner LLM failed)"

        # De-duplicate tools, cap at 4
        seen: set[str] = set()
        deduped: list[dict[str, str]] = []
        for t in valid_tools:
            name = t["name"]
            if name in seen:
                continue
            seen.add(name)
            deduped.append({"name": name, "argument": t.get("argument", "")})
            if len(deduped) >= 4:
                break

        names = [t["name"] for t in deduped]
        result.trace.append(TraceStep(
            name="plan",
            summary=f"Selected tools: {names}",
            detail=f"Reasoning: {reasoning}",
        ))
        return deduped

    @staticmethod
    def _parse_plan(raw: str) -> dict:
        """Extract JSON from the planner output, tolerating preamble/postamble."""
        # Try direct parse first
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Look for the first {...} block
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def _fallback_plan(question: str) -> list[dict[str, str]]:
        """Heuristic plan used when the LLM planner fails."""
        q = question.lower()
        plan: list[dict[str, str]] = [
            {"name": "retrieve_knowledge", "argument": question}
        ]
        if any(w in q for w in ["my pet", "my dog", "my cat", "mochi", "whiskers", "old", "age", "puppy", "kitten"]):
            plan.append({"name": "get_pet_profiles", "argument": ""})
        if any(w in q for w in ["schedule", "today", "plan", "walk", "feed"]):
            plan.append({"name": "get_schedule", "argument": ""})
        if any(w in q for w in ["conflict", "overlap", "missed", "skip"]):
            plan.append({"name": "get_conflicts", "argument": ""})
        return plan

    @staticmethod
    def _owner_summary(owner: Owner) -> str:
        """One-line summary of owner state for the planner."""
        if not owner.pets:
            return "no pets yet"
        names = ", ".join(f"{p.name}({p.species},{p.age}y)" for p in owner.pets)
        return f"{len(owner.pets)} pet(s): {names}; budget {owner.available_time}min"

    # ── Step 2: tool executor ─────────────────────────────────────

    def _execute(
        self,
        plan: list[dict[str, str]],
        owner: Owner,
        result: AgentResult,
    ) -> dict[str, str]:
        """Run each tool in the plan and return a name → observation mapping."""
        observations: dict[str, str] = {}

        tool_impls: dict[str, Callable[[str, Owner], str]] = {
            "retrieve_knowledge": self._tool_retrieve_knowledge,
            "get_pet_profiles": self._tool_get_pet_profiles,
            "get_schedule": self._tool_get_schedule,
            "get_conflicts": self._tool_get_conflicts,
        }

        for step in plan:
            name = step["name"]
            argument = step.get("argument", "")
            impl = tool_impls.get(name)
            if impl is None:
                continue
            try:
                obs = impl(argument, owner)
            except Exception as e:
                logger.exception("Tool %s failed", name)
                obs = f"[tool error: {e}]"
            observations[name] = obs
            result.tools_called.append(name)
            result.trace.append(TraceStep(
                name=f"tool:{name}",
                summary=f"{len(obs)} chars returned",
                detail=obs[:1500] + ("…" if len(obs) > 1500 else ""),
            ))
        return observations

    def _tool_retrieve_knowledge(self, argument: str, owner: Owner) -> str:
        query = argument or "pet care general advice"
        chunks = self.rag.retrieve(query)
        if not chunks:
            return "No relevant knowledge found."
        sources = sorted({c.source for c in chunks})
        body = self.rag.format_context(chunks)
        return f"Retrieved {len(chunks)} chunk(s) from {sources}.\n\n{body}"

    @staticmethod
    def _tool_get_pet_profiles(argument: str, owner: Owner) -> str:
        if not owner.pets:
            return "No pets registered."
        lines = [f"Owner: {owner.name} (budget {owner.available_time}min/day)"]
        for pet in owner.pets:
            lines.append(f"- {pet.name}: {pet.species}, age {pet.age}, {len(pet.tasks)} task(s)")
        return "\n".join(lines)

    @staticmethod
    def _tool_get_schedule(argument: str, owner: Owner) -> str:
        scheduler = Scheduler(owner)
        plan = scheduler.generate_schedule()
        if not plan:
            return "No schedule generated (no pending tasks)."
        lines = ["Today's schedule:"]
        for t in plan:
            time_str = t.start_time or "flex"
            tag = "REQUIRED" if t.required else t.priority
            lines.append(
                f"  {time_str} — {t.title} ({t.pet_name}) "
                f"[{t.duration_minutes}min, {tag}]"
            )
        return "\n".join(lines)

    @staticmethod
    def _tool_get_conflicts(argument: str, owner: Owner) -> str:
        scheduler = Scheduler(owner)
        scheduler.generate_schedule()
        parts: list[str] = []
        if scheduler.conflicts:
            parts.append("Conflicts:")
            parts.extend(f"  - {c}" for c in scheduler.conflicts)
        else:
            parts.append("No conflicts detected.")
        if scheduler.skipped_tasks:
            parts.append("\nSkipped tasks (not enough time):")
            for t in scheduler.skipped_tasks:
                parts.append(f"  - {t.title} ({t.pet_name}, {t.duration_minutes}min)")
        return "\n".join(parts)

    # ── Step 3: synthesizer ───────────────────────────────────────

    def _synthesize(
        self,
        question: str,
        observations: dict[str, str],
        result: AgentResult,
    ) -> str:
        """Generate the answer from the question + tool observations."""
        obs_block = self._format_observations(observations)
        user_msg = (
            f"## Question\n{question}\n\n"
            f"## Observations\n{obs_block}\n\n"
            "Now write the final answer following the style rules."
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYNTHESIZER_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=self.max_tokens,
        )
        draft = response.choices[0].message.content
        result.trace.append(TraceStep(
            name="synthesize",
            summary=f"draft: {len(draft)} chars",
            detail=draft[:500] + ("…" if len(draft) > 500 else ""),
        ))
        return draft

    @staticmethod
    def _format_observations(observations: dict[str, str]) -> str:
        if not observations:
            return "(no observations)"
        sections = []
        for name, body in observations.items():
            sections.append(f"### {name}\n{body}")
        return "\n\n".join(sections)

    # ── Step 4: critic ────────────────────────────────────────────

    def _critique(
        self,
        question: str,
        observations: dict[str, str],
        draft: str,
        result: AgentResult,
    ) -> tuple[str, str]:
        """Heuristic critic. Returns (verdict, issues)."""
        issues: list[str] = []

        # Check 1: response should not be empty or trivial
        if len(draft.strip()) < 50:
            issues.append("draft too short")

        # Check 2: if pets were retrieved, response should mention at least one
        if "get_pet_profiles" in observations:
            pet_obs = observations["get_pet_profiles"]
            named = re.findall(r"^- (\w+):", pet_obs, re.MULTILINE)
            if named and not any(name.lower() in draft.lower() for name in named):
                issues.append(
                    f"pet profile retrieved but draft doesn't mention any of {named}"
                )

        # Check 3: if knowledge was retrieved, draft should reference at least one
        # source-typical keyword from the retrieved chunks (loose grounding check)
        if "retrieve_knowledge" in observations:
            kb_obs = observations["retrieve_knowledge"]
            if "No relevant knowledge" not in kb_obs and len(draft) > 0:
                # Pick a few content words from the observations
                obs_tokens = set(re.findall(r"\b[a-z]{6,}\b", kb_obs.lower()))
                draft_tokens = set(re.findall(r"\b[a-z]{6,}\b", draft.lower()))
                overlap = obs_tokens & draft_tokens
                if len(overlap) < 3:
                    issues.append("draft has weak overlap with retrieved knowledge")

        verdict = "REVISE" if issues else "OK"
        issue_str = "; ".join(issues)
        result.trace.append(TraceStep(
            name="critique",
            summary=f"verdict: {verdict}",
            detail=issue_str if issue_str else "no issues",
        ))
        return verdict, issue_str

    # ── Step 5: revise ────────────────────────────────────────────

    def _revise(
        self,
        question: str,
        observations: dict[str, str],
        draft: str,
        issues: str,
        result: AgentResult,
    ) -> str:
        """Single-shot revision pass when the critic flags issues."""
        obs_block = self._format_observations(observations)
        user_msg = (
            f"## Question\n{question}\n\n"
            f"## Observations\n{obs_block}\n\n"
            f"## Previous draft\n{draft}\n\n"
            f"## Critic feedback\n{issues}\n\n"
            "Rewrite the answer addressing the critic's feedback. "
            "Stay grounded in the observations."
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYNTHESIZER_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=self.max_tokens,
        )
        revised = response.choices[0].message.content
        result.trace.append(TraceStep(
            name="revise",
            summary=f"revised: {len(revised)} chars",
            detail=revised[:500] + ("…" if len(revised) > 500 else ""),
        ))
        return revised
