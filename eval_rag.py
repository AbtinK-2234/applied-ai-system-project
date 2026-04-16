"""
Evaluation script for PawPal+ RAG system.

Tests the RAG pipeline on predefined inputs and prints a pass/fail summary.
Evaluates both retrieval quality (correct sources found) and guardrail behavior.

Usage:
    python eval_rag.py              # retrieval + guardrail tests (no API key needed)
    python eval_rag.py --full       # also run end-to-end tests (requires HF_TOKEN)
"""

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(__file__))

from rag_engine import RAGEngine
from ai_advisor import (
    AIAdvisor,
    validate_input,
    check_topic_relevance,
    validate_output,
)
from pawpal_system import Owner, Pet, Task


@dataclass
class EvalResult:
    name: str
    passed: bool
    detail: str


results: list[EvalResult] = []


def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append(EvalResult(name, passed, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


# ── Retrieval quality tests ──────────────────────────────────────

def eval_retrieval():
    print("\n=== Retrieval Quality ===")
    engine = RAGEngine()
    n = engine.load_knowledge_base()
    record("Knowledge base loads", n > 0, f"{n} chunks")

    test_cases = [
        {
            "query": "What should I feed my dog?",
            "expected_source": "nutrition.md",
            "description": "Dog nutrition query retrieves nutrition.md",
        },
        {
            "query": "How often should I brush my cat?",
            "expected_source": "grooming.md",
            "description": "Cat grooming query retrieves grooming.md",
        },
        {
            "query": "vaccination schedule for puppies distemper rabies health",
            "expected_source": "health.md",
            "description": "Vaccination query retrieves health.md",
        },
        {
            "query": "How much exercise does a senior dog need?",
            "expected_source": "exercise.md",
            "description": "Exercise query retrieves exercise.md",
        },
        {
            "query": "How do I give pills to my cat?",
            "expected_source": "medication.md",
            "description": "Medication query retrieves medication.md",
        },
        {
            "query": "How do I stop my dog from barking?",
            "expected_source": "training.md",
            "description": "Training query retrieves training.md",
        },
    ]

    for tc in test_cases:
        chunks = engine.retrieve(tc["query"])
        sources = [c.source for c in chunks]
        passed = tc["expected_source"] in sources
        record(
            tc["description"],
            passed,
            f"got {sources}" if not passed else f"top source: {sources[0]}",
        )

    # Verify retrieval returns content, not empty
    chunks = engine.retrieve("flea tick prevention monthly")
    context = engine.format_context(chunks)
    record(
        "Format context produces non-empty string",
        len(context) > 50,
        f"{len(context)} chars",
    )


# ── Guardrail tests ─────────────────────────────────────────────

def eval_guardrails():
    print("\n=== Guardrails ===")

    # Input validation
    record("Empty input rejected", validate_input("") is not None)
    record("Too-short input rejected", validate_input("hi") is not None)
    record("Oversized input rejected", validate_input("x" * 501) is not None)
    record("Valid input accepted", validate_input("How do I feed my dog?") is None)

    # Topic relevance
    on_topic = [
        "What should I feed my puppy?",
        "How often to groom a cat?",
        "Is my dog's exercise schedule enough?",
        "When should I give heartworm medication?",
    ]
    off_topic = [
        "What is the capital of France?",
        "How do I fix a segmentation fault?",
        "Write me a poem about the moon",
        "What stocks should I buy?",
    ]

    for q in on_topic:
        record(f"On-topic: '{q[:40]}...'", check_topic_relevance(q))
    for q in off_topic:
        record(f"Off-topic blocked: '{q[:40]}...'", not check_topic_relevance(q))

    # Output validation
    safe = "Brush your dog weekly for a healthy coat."
    record("Safe output unchanged", validate_output(safe) == safe)

    dosage = "You should give 10mg of carprofen twice daily."
    validated = validate_output(dosage)
    record(
        "Dosage triggers vet disclaimer",
        "consult your veterinarian" in validated.lower(),
    )

    long_text = "A" * 3500
    truncated = validate_output(long_text)
    record("Long output truncated", len(truncated) < 3500)


# ── End-to-end tests (requires API key) ─────────────────────────

def eval_end_to_end():
    print("\n=== End-to-End (API) ===")

    api_key = os.environ.get("HF_TOKEN", "")
    if not api_key:
        print("  [SKIP] HF_TOKEN not set — skipping end-to-end tests")
        print("         Run with: HF_TOKEN=your-key python eval_rag.py --full")
        return

    advisor = AIAdvisor()
    ok = advisor.initialise()
    record("Advisor initialises", ok)
    if not ok:
        return

    # Set up a realistic owner
    owner = Owner(name="Jordan", available_time=60)
    dog = Pet(name="Mochi", species="dog", age=3)
    dog.add_task(Task(
        title="Morning walk", duration_minutes=20, priority="high",
        category="walk", start_time="08:00", frequency="daily",
    ))
    dog.add_task(Task(
        title="Flea medication", duration_minutes=5, priority="high",
        category="medication", required=True, frequency="once",
    ))
    owner.add_pet(dog)

    cat = Pet(name="Whiskers", species="cat", age=10)
    cat.add_task(Task(
        title="Evening feeding", duration_minutes=10, priority="high",
        category="feeding", start_time="18:00", frequency="daily",
    ))
    owner.add_pet(cat)

    # Test 1: Nutrition question (should reference pet context)
    answer1 = advisor.ask("What should I feed Mochi based on his age?", owner)
    record(
        "Nutrition Q references the dog",
        "mochi" in answer1.lower() or "dog" in answer1.lower(),
        f"response length: {len(answer1)} chars",
    )

    # Test 2: Schedule question (should reference schedule data)
    answer2 = advisor.ask(
        "Is my exercise schedule enough for Mochi?", owner
    )
    record(
        "Schedule Q provides exercise advice",
        len(answer2) > 50,
        f"response length: {len(answer2)} chars",
    )

    # Test 3: Off-topic question (should be blocked by guardrail)
    answer3 = advisor.ask("What is the meaning of life?", owner)
    record(
        "Off-topic blocked at advisor level",
        "pet" in answer3.lower() and "care" in answer3.lower(),
    )

    # Test 4: Senior cat health (should pull from health.md)
    answer4 = advisor.ask(
        "Whiskers is 10 years old. What health issues should I watch for?",
        owner,
    )
    record(
        "Senior cat health Q is substantive",
        len(answer4) > 100 and ("kidney" in answer4.lower() or "senior" in answer4.lower() or "vet" in answer4.lower()),
        f"response length: {len(answer4)} chars",
    )


# ── Main ─────────────────────────────────────────────────────────

def main():
    full_mode = "--full" in sys.argv

    print("PawPal+ RAG Evaluation")
    print("=" * 50)

    eval_retrieval()
    eval_guardrails()

    if full_mode:
        eval_end_to_end()

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    print("\n" + "=" * 50)
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")

    if failed:
        print("\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  - {r.name}: {r.detail}")
        print(f"\nScore: {passed}/{total}")
        sys.exit(1)
    else:
        print("All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
