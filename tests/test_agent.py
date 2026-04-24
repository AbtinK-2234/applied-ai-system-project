"""Tests for the PetCareAgent agentic workflow."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import (
    PetCareAgent, AgentResult, TraceStep, VALID_TOOLS, TOOL_DESCRIPTIONS,
)
from rag_engine import RAGEngine, Chunk
from pawpal_system import Owner, Pet, Task


def make_chat_response(content: str):
    """Build a mock response object shaped like the real client returns."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 50
    return resp


def make_loaded_rag() -> RAGEngine:
    """A RAG engine with deterministic test chunks (no disk I/O)."""
    engine = RAGEngine()
    engine.chunks = [
        Chunk(text="Adult dogs do well with two meals per day.",
              source="nutrition.md", heading="Adult Dogs"),
        Chunk(text="Brushing reduces shedding and is recommended weekly.",
              source="grooming.md", heading="Brushing"),
        Chunk(text="Senior cats benefit from kidney function checks.",
              source="health.md", heading="Senior Cats"),
    ]
    engine._build_index()
    return engine


def make_owner() -> Owner:
    owner = Owner(name="Jordan", available_time=60)
    dog = Pet(name="Mochi", species="dog", age=3)
    dog.add_task(Task(
        title="Morning walk", duration_minutes=20, priority="high",
        category="walk", start_time="08:00", frequency="daily",
    ))
    owner.add_pet(dog)
    return owner


# ── Tool registry ────────────────────────────────────────────────


class TestToolRegistry:
    def test_all_tools_have_descriptions(self):
        assert VALID_TOOLS == set(TOOL_DESCRIPTIONS.keys())

    def test_expected_tools_present(self):
        assert {"retrieve_knowledge", "get_pet_profiles",
                "get_schedule", "get_conflicts"} <= VALID_TOOLS


# ── Tool implementations ────────────────────────────────────────


class TestTools:
    def test_retrieve_knowledge_returns_chunks(self):
        agent = PetCareAgent(rag=make_loaded_rag(), client=MagicMock())
        result = agent._tool_retrieve_knowledge("dog meals", make_owner())
        assert "Retrieved" in result
        assert "nutrition.md" in result

    def test_retrieve_knowledge_handles_empty(self):
        agent = PetCareAgent(rag=RAGEngine(), client=MagicMock())
        result = agent._tool_retrieve_knowledge("anything", make_owner())
        assert "No relevant knowledge" in result

    def test_get_pet_profiles_lists_pets(self):
        agent = PetCareAgent(rag=make_loaded_rag(), client=MagicMock())
        result = agent._tool_get_pet_profiles("", make_owner())
        assert "Mochi" in result
        assert "dog" in result

    def test_get_pet_profiles_no_pets(self):
        owner = Owner(name="Solo", available_time=30)
        agent = PetCareAgent(rag=make_loaded_rag(), client=MagicMock())
        result = agent._tool_get_pet_profiles("", owner)
        assert "No pets" in result

    def test_get_schedule_returns_plan(self):
        agent = PetCareAgent(rag=make_loaded_rag(), client=MagicMock())
        result = agent._tool_get_schedule("", make_owner())
        assert "Morning walk" in result
        assert "Mochi" in result

    def test_get_conflicts_no_conflicts(self):
        agent = PetCareAgent(rag=make_loaded_rag(), client=MagicMock())
        result = agent._tool_get_conflicts("", make_owner())
        assert "No conflicts" in result


# ── Planner ──────────────────────────────────────────────────────


class TestPlanner:
    def test_parse_plan_strict_json(self):
        raw = '{"tools": [{"name": "retrieve_knowledge", "argument": "x"}], "reasoning": "r"}'
        parsed = PetCareAgent._parse_plan(raw)
        assert parsed["tools"][0]["name"] == "retrieve_knowledge"

    def test_parse_plan_with_preamble(self):
        raw = (
            'Sure, here is the plan: '
            '{"tools": [{"name": "get_schedule", "argument": ""}], "reasoning": "r"}'
        )
        parsed = PetCareAgent._parse_plan(raw)
        assert parsed["tools"][0]["name"] == "get_schedule"

    def test_parse_plan_invalid_returns_empty(self):
        assert PetCareAgent._parse_plan("not json at all") == {}

    def test_fallback_plan_always_retrieves(self):
        plan = PetCareAgent._fallback_plan("anything")
        names = [p["name"] for p in plan]
        assert "retrieve_knowledge" in names

    def test_fallback_plan_picks_pet_tool(self):
        plan = PetCareAgent._fallback_plan("How old is Mochi?")
        names = [p["name"] for p in plan]
        assert "get_pet_profiles" in names

    def test_fallback_plan_picks_schedule_tool(self):
        plan = PetCareAgent._fallback_plan("Is my schedule full today?")
        names = [p["name"] for p in plan]
        assert "get_schedule" in names

    def test_planner_uses_llm_output(self):
        client = MagicMock()
        client.chat.completions.create.return_value = make_chat_response(
            '{"tools": [{"name": "retrieve_knowledge", "argument": "dog food"}, '
            '{"name": "get_pet_profiles", "argument": ""}], "reasoning": "test"}'
        )
        agent = PetCareAgent(rag=make_loaded_rag(), client=client)
        result = AgentResult(answer="")
        plan = agent._plan("What should I feed Mochi?", make_owner(), result)
        names = [p["name"] for p in plan]
        assert "retrieve_knowledge" in names
        assert "get_pet_profiles" in names
        assert any(s.name == "plan" for s in result.trace)

    def test_planner_dedupes(self):
        client = MagicMock()
        client.chat.completions.create.return_value = make_chat_response(
            '{"tools": [{"name": "retrieve_knowledge", "argument": "a"}, '
            '{"name": "retrieve_knowledge", "argument": "b"}], "reasoning": "x"}'
        )
        agent = PetCareAgent(rag=make_loaded_rag(), client=client)
        result = AgentResult(answer="")
        plan = agent._plan("q", make_owner(), result)
        assert len(plan) == 1

    def test_planner_falls_back_on_invalid_tools(self):
        client = MagicMock()
        client.chat.completions.create.return_value = make_chat_response(
            '{"tools": [{"name": "delete_database", "argument": ""}], "reasoning": "x"}'
        )
        agent = PetCareAgent(rag=make_loaded_rag(), client=client)
        result = AgentResult(answer="")
        plan = agent._plan("How is Mochi?", make_owner(), result)
        names = [p["name"] for p in plan]
        # Fallback heuristic kicks in — always includes retrieve_knowledge
        assert "retrieve_knowledge" in names


# ── Critic ───────────────────────────────────────────────────────


class TestCritic:
    def test_critic_passes_grounded_answer(self):
        agent = PetCareAgent(rag=make_loaded_rag(), client=MagicMock())
        observations = {
            "retrieve_knowledge": "Adult dogs benefit from twice-daily meals "
                                  "containing balanced protein, fats, and "
                                  "carbohydrates for healthy nutrition."
        }
        draft = (
            "For your dog, give twice-daily meals with balanced protein, "
            "fats, and carbohydrates for healthy nutrition."
        )
        result = AgentResult(answer="")
        verdict, _ = agent._critique("How feed?", observations, draft, result)
        assert verdict == "OK"

    def test_critic_flags_short_answer(self):
        agent = PetCareAgent(rag=make_loaded_rag(), client=MagicMock())
        result = AgentResult(answer="")
        verdict, issues = agent._critique("Q", {}, "ok.", result)
        assert verdict == "REVISE"
        assert "too short" in issues

    def test_critic_flags_missing_pet(self):
        agent = PetCareAgent(rag=make_loaded_rag(), client=MagicMock())
        observations = {
            "get_pet_profiles":
                "Owner: Jordan\n- Mochi: dog, age 3, 1 task(s)"
        }
        draft = (
            "Dogs benefit from regular walks and balanced nutrition. "
            "Always provide fresh water and appropriate exercise daily."
        )
        result = AgentResult(answer="")
        verdict, issues = agent._critique("How is my pet?", observations, draft, result)
        assert verdict == "REVISE"
        assert "Mochi" in issues


# ── Full agent run ───────────────────────────────────────────────


class TestAgentRun:
    def test_run_produces_trace_and_answer(self):
        """End-to-end test with all LLM calls mocked."""
        client = MagicMock()
        # Sequence: 1) plan, 2) synthesize. Critic is heuristic, no LLM call.
        client.chat.completions.create.side_effect = [
            make_chat_response(
                '{"tools": [{"name": "retrieve_knowledge", "argument": "mochi food"}, '
                '{"name": "get_pet_profiles", "argument": ""}], "reasoning": "user asks about Mochi"}'
            ),
            make_chat_response(
                "For Mochi, who is a 3-year-old adult dog:\n"
                "- Two meals per day\n"
                "- Balanced protein and fat\n"
                "- Adjust portion to body weight\n"
                "- Use treats during walks for training\n"
                "Consult your veterinarian for exact portions."
            ),
        ]
        agent = PetCareAgent(rag=make_loaded_rag(), client=client)
        result = agent.run("What should I feed Mochi?", make_owner())

        # The answer is the synthesizer output
        assert "Mochi" in result.answer
        # Trace contains plan + tool steps + synthesize + critique (at least)
        step_names = [s.name for s in result.trace]
        assert "plan" in step_names
        assert "synthesize" in step_names
        assert "critique" in step_names
        assert any(n.startswith("tool:") for n in step_names)
        # Tools were recorded
        assert "retrieve_knowledge" in result.tools_called

    def test_run_revises_when_critic_fails(self):
        """When the critic flags issues, a revise call happens."""
        client = MagicMock()
        # Plan → synthesize (bad answer) → revise (good answer)
        client.chat.completions.create.side_effect = [
            make_chat_response(
                '{"tools": [{"name": "get_pet_profiles", "argument": ""}], "reasoning": "x"}'
            ),
            make_chat_response("ok."),  # too short → critic flags
            make_chat_response(
                "For Mochi (a 3-year-old adult dog), here is the plan:\n"
                "- Daily walks support cardiovascular health\n"
                "- Two meals per day works well at this age\n"
                "- Brush weekly to control shedding\n"
                "Your morning 08:00 walk is already a good start."
            ),
        ]
        agent = PetCareAgent(rag=make_loaded_rag(), client=client)
        result = agent.run("Tell me about Mochi.", make_owner())

        assert result.revised is True
        assert "Mochi" in result.answer
        step_names = [s.name for s in result.trace]
        assert "revise" in step_names


# ── Advisor.ask_with_agent integration ──────────────────────────


class TestAdvisorAskWithAgent:
    @patch.dict(os.environ, {"HF_TOKEN": "test-key-123"})
    def test_off_topic_blocked_before_agent_runs(self):
        from ai_advisor import AIAdvisor
        advisor = AIAdvisor()
        advisor.initialise()
        result = advisor.ask_with_agent("What is the capital of France?", make_owner())
        assert isinstance(result, AgentResult)
        # Off-topic returns the canned message; no trace from the agent
        assert "PawPal+" in result.answer
        assert result.trace == []

    @patch.dict(os.environ, {"HF_TOKEN": "test-key-123"})
    def test_invalid_input_blocked(self):
        from ai_advisor import AIAdvisor
        advisor = AIAdvisor()
        advisor.initialise()
        result = advisor.ask_with_agent("hi", make_owner())
        assert isinstance(result, AgentResult)
        assert "too short" in result.answer.lower()
        assert result.trace == []

    def test_uninitialised_returns_friendly_error(self):
        from ai_advisor import AIAdvisor
        advisor = AIAdvisor()
        result = advisor.ask_with_agent("How is Mochi?", make_owner())
        assert isinstance(result, AgentResult)
        assert "not initialised" in result.answer.lower()
