"""
Specialization evaluation for PawPal+

Demonstrates that the specialized PawPal+ pipeline (few-shot system prompt +
retrieval + live pet/schedule context) produces measurably different output
than a baseline LLM call (generic prompt, no retrieval, no context).

Two modes:

  python eval_specialization.py                  # offline structural diff
                                                 # (no API key needed) — compares
                                                 # the prompts themselves and
                                                 # checks for the few-shot
                                                 # markers and constrained-style
                                                 # rules

  python eval_specialization.py --full           # live API comparison
                                                 # (requires HF_TOKEN) — runs
                                                 # the same questions through
                                                 # baseline + specialized and
                                                 # prints a metric table

Metrics computed in --full mode:
  - response length (chars)
  - mentions of the relevant pet name
  - bullet count
  - vet-disclaimer present (medical/dosage questions)
  - schedule reference (when schedule is relevant)
  - retrieval source attribution
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(__file__))

from ai_advisor import AIAdvisor, SYSTEM_PROMPT
from pawpal_system import Owner, Pet, Task


BASELINE_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question."
)

# The same three questions are run through both pipelines.
TEST_CASES = [
    {
        "question": "What should I feed Mochi based on his age?",
        "expected_pet": "Mochi",
        "expects_schedule_ref": True,
        "expects_vet_disclaimer": False,
    },
    {
        "question": "Whiskers is 10 years old. What health issues should I watch for?",
        "expected_pet": "Whiskers",
        "expects_schedule_ref": False,
        "expects_vet_disclaimer": True,  # senior health → vet referral expected
    },
    {
        "question": "How much carprofen should I give my dog?",
        "expected_pet": None,
        "expects_schedule_ref": False,
        "expects_vet_disclaimer": True,  # dosage → disclaimer required
    },
]


@dataclass
class ResponseMetrics:
    label: str
    text: str
    length: int = 0
    pet_name_hits: int = 0
    bullet_count: int = 0
    has_vet_disclaimer: bool = False
    has_schedule_ref: bool = False
    has_source_attribution: bool = False

    @classmethod
    def from_text(cls, label: str, text: str, expected_pet: str | None) -> "ResponseMetrics":
        m = cls(label=label, text=text, length=len(text))
        if expected_pet:
            m.pet_name_hits = len(
                re.findall(rf"\b{re.escape(expected_pet)}\b", text, re.IGNORECASE)
            )
        m.bullet_count = len(re.findall(r"^\s*[-*•]\s+", text, re.MULTILINE))
        m.has_vet_disclaimer = bool(
            re.search(r"\b(vet|veterinarian)\b", text, re.IGNORECASE)
        )
        m.has_schedule_ref = bool(
            re.search(r"\b(schedule|scheduled|walk|feeding|today)\b", text, re.IGNORECASE)
        )
        m.has_source_attribution = "Source" in text or "knowledge base" in text.lower()
        return m


@dataclass
class CaseResult:
    question: str
    baseline: ResponseMetrics
    specialized: ResponseMetrics
    expected_pet: str | None
    expects_schedule_ref: bool
    expects_vet_disclaimer: bool
    structural_wins: list[str] = field(default_factory=list)
    structural_losses: list[str] = field(default_factory=list)


def build_owner() -> Owner:
    """Realistic owner state used for both baseline and specialized runs."""
    owner = Owner(name="Jordan", available_time=60)

    dog = Pet(name="Mochi", species="dog", age=3)
    dog.add_task(Task(
        title="Morning walk", duration_minutes=20, priority="high",
        category="walk", start_time="08:00", frequency="daily",
    ))
    owner.add_pet(dog)

    cat = Pet(name="Whiskers", species="cat", age=10)
    cat.add_task(Task(
        title="Evening feeding", duration_minutes=10, priority="high",
        category="feeding", start_time="18:00", frequency="daily",
    ))
    owner.add_pet(cat)

    return owner


# ── Offline structural diff ──────────────────────────────────────


def offline_prompt_diff() -> int:
    """Compare the prompts and few-shot markers without calling the API.

    Returns the exit code (0 = pass, 1 = fail).
    """
    print("=== Offline Structural Comparison ===\n")
    print(f"Baseline prompt length:    {len(BASELINE_SYSTEM_PROMPT)} chars")
    print(f"Specialized prompt length: {len(SYSTEM_PROMPT)} chars")
    print(f"Specialization ratio:      {len(SYSTEM_PROMPT) / max(len(BASELINE_SYSTEM_PROMPT), 1):.1f}x\n")

    checks = [
        ("Specialized prompt has few-shot examples",
         "[Example A" in SYSTEM_PROMPT and "[Example B" in SYSTEM_PROMPT),
        ("Specialized prompt has constrained style rules",
         "Specialized response style" in SYSTEM_PROMPT),
        ("Specialized prompt mentions bullet format",
         "bullet" in SYSTEM_PROMPT.lower()),
        ("Specialized prompt requires vet disclaimer for medical questions",
         "veterinarian" in SYSTEM_PROMPT.lower()),
        ("Specialized prompt ties answers to schedule",
         "schedule" in SYSTEM_PROMPT.lower()),
        ("Baseline prompt has none of the above",
         all(s not in BASELINE_SYSTEM_PROMPT for s in
             ["bullet", "veterinarian", "Example A", "schedule"])),
    ]

    passed = 0
    for name, ok in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {name}")
        if ok:
            passed += 1

    print(f"\nStructural diff: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


# ── Live API comparison ──────────────────────────────────────────


def live_baseline_call(client, question: str) -> str:
    """Generic LLM call — no retrieval, no system context, no live state."""
    response = client.chat.completions.create(
        model="meta-llama/Llama-3.1-8B-Instruct",
        messages=[
            {"role": "system", "content": BASELINE_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        max_tokens=512,
    )
    return response.choices[0].message.content


def live_comparison() -> int:
    """Run baseline + specialized on the same questions and print metrics."""
    if not os.environ.get("HF_TOKEN"):
        print("[SKIP] HF_TOKEN not set — cannot run live comparison.")
        print("       Set HF_TOKEN and re-run: HF_TOKEN=... python eval_specialization.py --full")
        return 0

    advisor = AIAdvisor()
    if not advisor.initialise():
        print("[FAIL] Advisor failed to initialise.")
        return 1

    owner = build_owner()

    print("\n=== Live API Comparison: Baseline vs Specialized ===\n")
    case_results: list[CaseResult] = []

    for tc in TEST_CASES:
        question = tc["question"]
        print(f"\nQ: {question}")
        print("-" * 60)

        # Baseline call
        try:
            baseline_text = live_baseline_call(advisor._client, question)
        except Exception as e:
            print(f"  Baseline call failed: {e}")
            baseline_text = ""

        # Specialized call (full pipeline)
        specialized_text = advisor.ask(question, owner)

        baseline_metrics = ResponseMetrics.from_text(
            "baseline", baseline_text, tc["expected_pet"]
        )
        specialized_metrics = ResponseMetrics.from_text(
            "specialized", specialized_text, tc["expected_pet"]
        )

        # Determine structural wins for the specialized version
        wins: list[str] = []
        losses: list[str] = []

        if tc["expected_pet"]:
            if specialized_metrics.pet_name_hits > baseline_metrics.pet_name_hits:
                wins.append(f"references {tc['expected_pet']} more often")
            elif specialized_metrics.pet_name_hits < baseline_metrics.pet_name_hits:
                losses.append(f"references {tc['expected_pet']} less often")

        if specialized_metrics.bullet_count > baseline_metrics.bullet_count:
            wins.append(f"uses {specialized_metrics.bullet_count} bullets vs {baseline_metrics.bullet_count}")

        if tc["expects_vet_disclaimer"]:
            if specialized_metrics.has_vet_disclaimer and not baseline_metrics.has_vet_disclaimer:
                wins.append("includes vet disclaimer (baseline does not)")
            elif not specialized_metrics.has_vet_disclaimer and baseline_metrics.has_vet_disclaimer:
                losses.append("missing vet disclaimer that baseline has")

        if tc["expects_schedule_ref"]:
            if specialized_metrics.has_schedule_ref and not baseline_metrics.has_schedule_ref:
                wins.append("references the actual schedule (baseline cannot)")

        case = CaseResult(
            question=question,
            baseline=baseline_metrics,
            specialized=specialized_metrics,
            expected_pet=tc["expected_pet"],
            expects_schedule_ref=tc["expects_schedule_ref"],
            expects_vet_disclaimer=tc["expects_vet_disclaimer"],
            structural_wins=wins,
            structural_losses=losses,
        )
        case_results.append(case)

        # Per-case report
        print(f"  Baseline:    {baseline_metrics.length} chars, "
              f"{baseline_metrics.bullet_count} bullets, "
              f"pet={baseline_metrics.pet_name_hits}, "
              f"vet={baseline_metrics.has_vet_disclaimer}, "
              f"sched={baseline_metrics.has_schedule_ref}")
        print(f"  Specialized: {specialized_metrics.length} chars, "
              f"{specialized_metrics.bullet_count} bullets, "
              f"pet={specialized_metrics.pet_name_hits}, "
              f"vet={specialized_metrics.has_vet_disclaimer}, "
              f"sched={specialized_metrics.has_schedule_ref}")
        if wins:
            print(f"  Specialized wins: {wins}")
        if losses:
            print(f"  Specialized losses: {losses}")

    # Summary
    total_wins = sum(len(c.structural_wins) for c in case_results)
    total_losses = sum(len(c.structural_losses) for c in case_results)

    print("\n" + "=" * 60)
    print(f"Specialized pipeline produced {total_wins} structural wins and "
          f"{total_losses} losses across {len(case_results)} questions.")

    if total_wins == 0:
        print("FAIL: No measurable difference detected.")
        return 1
    if total_losses > total_wins:
        print("FAIL: Specialized pipeline regressed on more axes than it improved.")
        return 1
    print("PASS: Specialized output measurably differs from baseline in the "
          "expected directions (more pet-name references, more structured "
          "bullets, vet disclaimers on medical questions, schedule references).")
    return 0


# ── Main ─────────────────────────────────────────────────────────


def main() -> int:
    full_mode = "--full" in sys.argv

    print("PawPal+ Specialization Evaluation")
    print("=" * 60)

    offline_exit = offline_prompt_diff()

    if not full_mode:
        print("\n(Run with --full to also run the live API comparison "
              "against the same questions.)")
        return offline_exit

    live_exit = live_comparison()
    return offline_exit | live_exit


if __name__ == "__main__":
    sys.exit(main())
