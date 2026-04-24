## Class Diagram

```mermaid
classDiagram
    class Task {
        +String title
        +int duration_minutes
        +String priority
        +String category
        +String pet_name
        +bool required
        +bool completed
        +String start_time
        +String frequency
        +date due_date
        +priority_value() int
        +start_time_minutes() int
        +mark_complete() Task | None
    }

    class Pet {
        +String name
        +String species
        +String breed
        +int age
        +List~Task~ tasks
        +add_task(task: Task)
        +remove_task(title: str)
        +complete_task(title: str)
    }

    class Owner {
        +String name
        +int available_time
        +List~String~ preferences
        +List~Pet~ pets
        +add_pet(pet: Pet)
        +remove_pet(name: str)
        +get_all_tasks() List~Task~
    }

    class Scheduler {
        +Owner owner
        +List~Task~ daily_plan
        +List~Task~ skipped_tasks
        +List~String~ reasoning
        +List~String~ conflicts
        +sort_by_time(tasks) List~Task~
        +filter_by_pet(pet_name) List~Task~
        +filter_by_status(completed) List~Task~
        +detect_conflicts(tasks) List~String~
        +generate_schedule() List~Task~
        +explain_plan() String
    }

    class RAGEngine {
        +List~Chunk~ chunks
        +load_knowledge_base(directory) int
        +retrieve(query, top_k) List~Chunk~
        +format_context(chunks) String
        -_chunk_markdown(text, source) List~Chunk~
        -_build_index()
    }

    class Chunk {
        +String text
        +String source
        +String heading
    }

    class AIAdvisor {
        +RAGEngine rag
        +initialise() bool
        +is_ready bool
        +ask(question, owner) String
        +ask_with_agent(question, owner) AgentResult
        -_build_user_message() String
    }

    class PetCareAgent {
        +RAGEngine rag
        +InferenceClient client
        +String model
        +bool enable_critic
        +run(question, owner) AgentResult
        -_plan() List
        -_execute() Dict
        -_synthesize() String
        -_critique() tuple
        -_revise() String
    }

    class AgentResult {
        +String answer
        +List~TraceStep~ trace
        +List~String~ tools_called
        +bool revised
    }

    class TraceStep {
        +String name
        +String summary
        +String detail
        +render() String
    }

    Owner "1" --> "1..*" Pet : owns
    Pet "1" --> "0..*" Task : has
    Scheduler "1" --> "1" Owner : plans for
    Scheduler "1" --> "0..*" Task : schedules
    Task ..> Task : mark_complete() creates next
    AIAdvisor "1" --> "1" RAGEngine : uses
    AIAdvisor "1" --> "1" Owner : reads context from
    AIAdvisor "1" --> "1" PetCareAgent : delegates to
    PetCareAgent "1" --> "1" RAGEngine : queries
    PetCareAgent "1" --> "1" Owner : tools inspect
    PetCareAgent "1" --> "1" Scheduler : tools invoke
    PetCareAgent ..> AgentResult : produces
    AgentResult "1" --> "0..*" TraceStep : records
    RAGEngine "1" --> "0..*" Chunk : indexes
```

## System Architecture & Data Flow

```mermaid
flowchart TD
    subgraph UI["Streamlit App (app.py)"]
        ST["Schedule Tab"]
        AT["AI Advisor Tab (agent toggle)"]
    end

    subgraph Core["Core System (pawpal_system.py)"]
        OW[Owner]
        PE[Pet]
        TA[Task]
        SC[Scheduler]
    end

    subgraph RAG["Retrieval Layer"]
        KB["Knowledge Base<br/>(6 markdown docs)"]
        RE["RAG Engine<br/>(TF-IDF + cosine similarity)"]
    end

    subgraph GR["Guardrails"]
        GIN["Input validation<br/>(length, topic)"]
        GOUT["Output validation<br/>(length, dosage disclaimer)"]
    end

    subgraph AG["PetCareAgent (agent.py)"]
        P["1. Planner<br/>LLM picks tools (JSON)"]
        T["2. Tool Executor<br/>retrieve_knowledge<br/>get_pet_profiles<br/>get_schedule<br/>get_conflicts"]
        S["3. Synthesizer<br/>LLM drafts answer<br/>(few-shot specialized prompt)"]
        C["4. Critic<br/>heuristic groundedness"]
        RV["5. Revise (if flagged)<br/>single-shot rewrite"]
        TR["TraceStep log<br/>(observable steps)"]
    end

    API["HuggingFace API<br/>(Llama-3.1-8B-Instruct)"]

    ST --> OW
    OW --> PE
    PE --> TA
    OW --> SC
    SC --> TA

    AT -- "1. Question" --> GIN
    GIN -- "valid+on-topic" --> P
    GIN -- "rejected" --> AT

    P -- "tool list" --> T
    KB -- "load & chunk" --> RE
    T -- "retrieve_knowledge" --> RE
    T -- "get_pet_profiles" --> OW
    T -- "get_schedule / get_conflicts" --> SC
    T -- "observations" --> S
    S -- "draft" --> C
    C -- "OK" --> GOUT
    C -- "REVISE" --> RV
    RV --> GOUT
    S -- "LLM call" --> API
    P -- "LLM call" --> API
    RV -- "LLM call" --> API

    P -. logs .-> TR
    T -. logs .-> TR
    S -. logs .-> TR
    C -. logs .-> TR
    RV -. logs .-> TR

    GOUT -- "final answer + trace" --> AT
```

## Evaluation Harness

Two evaluation scripts validate the system on predefined inputs and print pass/fail summaries. They are run by CI on every push.

| Script | Scope | Tests |
|---|---|---|
| `eval_rag.py` | Retrieval quality, guardrail behavior, optional end-to-end | 23 offline, +4 end-to-end with `--full` |
| `eval_specialization.py` | Baseline-vs-specialized prompt + output comparison | 6 offline structural checks, +per-question metrics with `--full` |
| `pytest tests/` | Scheduler (Modules 1–3), RAG, advisor, agent | 84 unit/integration tests |
