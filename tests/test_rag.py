"""Tests for the RAG engine and AI advisor components."""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rag_engine import RAGEngine, Chunk, KNOWLEDGE_BASE_DIR
from ai_advisor import (
    AIAdvisor, _build_pet_context, _build_schedule_context,
    validate_input, check_topic_relevance, validate_output, OFF_TOPIC_RESPONSE,
)
from pawpal_system import Owner, Pet, Task


# ── RAG Engine: Document Loading ──────────────────────────────────


class TestKnowledgeBaseLoading:
    def test_loads_from_default_directory(self):
        engine = RAGEngine()
        n = engine.load_knowledge_base()
        assert n > 0, "Should load chunks from the knowledge_base directory"
        assert len(engine.chunks) == n

    def test_all_chunks_have_source_and_heading(self):
        engine = RAGEngine()
        engine.load_knowledge_base()
        for chunk in engine.chunks:
            assert chunk.source, "Every chunk must have a source file"
            assert chunk.heading, "Every chunk must have a heading"
            assert len(chunk.text) > 30, "Chunks should not be trivially small"

    def test_loads_from_nonexistent_directory(self):
        engine = RAGEngine()
        n = engine.load_knowledge_base(Path("/tmp/nonexistent_kb_dir"))
        assert n == 0

    def test_loads_from_empty_directory(self, tmp_path):
        engine = RAGEngine()
        n = engine.load_knowledge_base(tmp_path)
        assert n == 0

    def test_covers_all_knowledge_files(self):
        engine = RAGEngine()
        engine.load_knowledge_base()
        sources = {c.source for c in engine.chunks}
        expected = {"nutrition.md", "health.md", "grooming.md", "exercise.md",
                    "medication.md", "training.md"}
        assert sources == expected, f"Missing sources: {expected - sources}"


# ── RAG Engine: Chunking ─────────────────────────────────────────


class TestChunking:
    def test_chunk_markdown_splits_on_headings(self):
        text = (
            "# Heading A\nSome text that is long enough to pass the minimum chunk size threshold easily.\n"
            "# Heading B\nMore text here that is also long enough to pass the minimum chunk size threshold."
        )
        chunks = RAGEngine._chunk_markdown(text, "test.md")
        headings = [c.heading for c in chunks]
        assert "Heading A" in headings
        assert "Heading B" in headings

    def test_chunk_markdown_drops_tiny_chunks(self):
        text = "# H\nOk"
        chunks = RAGEngine._chunk_markdown(text, "test.md")
        assert len(chunks) == 0, "Chunks shorter than 30 chars should be dropped"

    def test_chunk_source_preserved(self):
        text = "# Topic\n" + ("Content. " * 50)
        chunks = RAGEngine._chunk_markdown(text, "myfile.md")
        for c in chunks:
            assert c.source == "myfile.md"


# ── RAG Engine: Retrieval ────────────────────────────────────────


class TestRetrieval:
    def test_retrieve_returns_relevant_chunks(self):
        engine = RAGEngine()
        engine.load_knowledge_base()
        results = engine.retrieve("dog nutrition feeding schedule")
        assert len(results) > 0
        # At least one result should come from the nutrition file
        sources = [r.source for r in results]
        assert "nutrition.md" in sources

    def test_retrieve_respects_top_k(self):
        engine = RAGEngine()
        engine.load_knowledge_base()
        results = engine.retrieve("grooming brushing", top_k=2)
        assert len(results) <= 2

    def test_retrieve_before_loading_returns_empty(self):
        engine = RAGEngine()
        results = engine.retrieve("anything")
        assert results == []

    def test_retrieve_irrelevant_query(self):
        engine = RAGEngine()
        engine.load_knowledge_base()
        results = engine.retrieve("quantum physics black hole")
        # May return results with low scores, but shouldn't crash
        assert isinstance(results, list)

    def test_format_context(self):
        engine = RAGEngine()
        chunks = [
            Chunk(text="Dogs need protein.", source="nutrition.md", heading="Dog Food"),
            Chunk(text="Brush daily.", source="grooming.md", heading="Brushing"),
        ]
        ctx = engine.format_context(chunks)
        assert "Dogs need protein." in ctx
        assert "Brush daily." in ctx
        assert "[Source 1:" in ctx
        assert "[Source 2:" in ctx

    def test_format_context_empty(self):
        engine = RAGEngine()
        assert engine.format_context([]) == ""


# ── AI Advisor: Context Building ─────────────────────────────────


class TestContextBuilding:
    def test_pet_context_with_pets_and_tasks(self):
        owner = Owner(name="Alice", available_time=60)
        pet = Pet(name="Rex", species="dog", age=3)
        pet.add_task(Task(
            title="Walk", duration_minutes=20, priority="high",
            category="walk", start_time="08:00",
        ))
        owner.add_pet(pet)

        ctx = _build_pet_context(owner)
        assert "Alice" in ctx
        assert "Rex" in ctx
        assert "dog" in ctx
        assert "Walk" in ctx
        assert "08:00" in ctx

    def test_pet_context_no_pets(self):
        owner = Owner(name="Bob", available_time=30)
        ctx = _build_pet_context(owner)
        assert "not added any pets" in ctx

    def test_schedule_context_generates_plan(self):
        owner = Owner(name="Carol", available_time=60)
        pet = Pet(name="Kitty", species="cat", age=2)
        pet.add_task(Task(
            title="Feed", duration_minutes=10, priority="high",
            category="feeding", required=True,
        ))
        owner.add_pet(pet)

        ctx = _build_schedule_context(owner)
        assert "Feed" in ctx
        assert "Kitty" in ctx

    def test_schedule_context_no_tasks(self):
        owner = Owner(name="Dan", available_time=60)
        ctx = _build_schedule_context(owner)
        assert "No schedule" in ctx


# ── AI Advisor: Initialisation ───────────────────────────────────


class TestAdvisorInit:
    def test_init_fails_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HF_TOKEN", None)
            advisor = AIAdvisor()
            assert advisor.initialise() is False
            assert advisor.is_ready is False

    def test_ask_when_not_initialised(self):
        advisor = AIAdvisor()
        owner = Owner(name="Test", available_time=30)
        result = advisor.ask("hello", owner)
        assert "not initialised" in result.lower()

    @patch.dict(os.environ, {"HF_TOKEN": "test-key-123"})
    def test_init_succeeds_with_api_key(self):
        advisor = AIAdvisor()
        assert advisor.initialise() is True
        assert advisor.is_ready is True

    @patch.dict(os.environ, {"HF_TOKEN": "test-key-123"})
    def test_ask_calls_api_with_context(self):
        advisor = AIAdvisor()
        advisor.initialise()

        # Mock the Groq client
        mock_message = MagicMock()
        mock_message.content = "Feed your dog twice daily."
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 20
        advisor._client = MagicMock()
        advisor._client.chat.completions.create.return_value = mock_response

        owner = Owner(name="Alice", available_time=60)
        pet = Pet(name="Rex", species="dog", age=3)
        owner.add_pet(pet)

        answer = advisor.ask("How should I feed Rex?", owner)
        assert answer == "Feed your dog twice daily."

        # Verify the client was called with the right structure
        call_kwargs = advisor._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        user_msg = messages[1]["content"]
        assert "How should I feed Rex?" in user_msg
        assert "Rex" in user_msg  # pet context included


# ── Guardrails ───────────────────────────────────────────────────


class TestInputValidation:
    def test_empty_question_rejected(self):
        assert validate_input("") is not None
        assert validate_input("   ") is not None

    def test_too_short_rejected(self):
        assert validate_input("hi") is not None

    def test_too_long_rejected(self):
        long_q = "a" * 501
        result = validate_input(long_q)
        assert result is not None
        assert "too long" in result

    def test_valid_question_passes(self):
        assert validate_input("How often should I feed my dog?") is None


class TestTopicRelevance:
    def test_pet_question_is_relevant(self):
        assert check_topic_relevance("What should I feed my dog?") is True
        assert check_topic_relevance("How often to groom a cat?") is True
        assert check_topic_relevance("Is this exercise schedule enough?") is True

    def test_off_topic_blocked(self):
        assert check_topic_relevance("What is the capital of France?") is False
        assert check_topic_relevance("How do I fix my JavaScript code?") is False
        assert check_topic_relevance("Tell me a joke") is False

    @patch.dict(os.environ, {"HF_TOKEN": "test-key-123"})
    def test_off_topic_returns_guardrail_message(self):
        advisor = AIAdvisor()
        advisor.initialise()
        owner = Owner(name="Test", available_time=30)
        result = advisor.ask("What is the meaning of life?", owner)
        assert result == OFF_TOPIC_RESPONSE


class TestOutputValidation:
    def test_normal_response_unchanged(self):
        text = "Feed your dog twice daily with high-quality food."
        assert validate_output(text) == text

    def test_long_response_truncated(self):
        text = "A" * 3500
        result = validate_output(text)
        assert len(result) < 3500
        assert "truncated" in result.lower()

    def test_dosage_gets_disclaimer(self):
        text = "You should give 10mg of medication daily."
        result = validate_output(text)
        assert "consult your veterinarian" in result.lower()

    def test_no_dosage_no_disclaimer(self):
        text = "Regular walks are important for your dog's health."
        result = validate_output(text)
        assert "consult your veterinarian" not in result.lower()
