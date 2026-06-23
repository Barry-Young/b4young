"""
Blueprint Builder System (BYI Edition)
======================================

This module implements a simplified version of the Blueprint Builder system as
described in the "Blueprint Builder for byoungimprovements" document.  It is
designed to run locally using Python and the CrewAI framework.  The goal of
this code is to provide a reference implementation for the core concepts
outlined in the document: a control/data plane separation, multi‑agent crews,
an event‑driven message bus, and a shared blackboard.  This implementation
does **not** attempt to fully replicate the production system described in the
document, but it should serve as a starting point for experimentation and
future development.

Key Features
------------
* **Blackboard pattern**: Agents store and retrieve data via a shared
  key‑value store.  This allows agent outputs to exceed individual LLM context
  limits and enables asynchronous coordination between tasks.
* **Event bus**: Agents and crews communicate using a simple publish/subscribe
  mechanism built on top of Python's `queue` module.  This decouples
  components and provides the basis for an event‑driven architecture.
* **Agent classes**: Each agent is defined with a role, goal, backstory and a
  `perform_task` method.  In a production environment these methods would
  integrate with external tools (e.g. OpenAI API, Serper), but here they
  simulate behaviour with deterministic text.
* **Crew orchestration**: A `Crew` instance coordinates a set of agents and
  tasks.  The orchestrator delegates work to workers, monitors completion via
  events, aggregates results, and writes the final report to disk.

Usage
-----
This module can be executed as a script.  Running it will initialise a
single `Market Intelligence` crew and execute its tasks.  The resulting
markdown report will be saved to the `outputs` directory.  To customise the
behaviour you can modify the agent definitions or extend the stubbed task
logic with calls to real APIs.  See the `Agent.perform_task` method for
details.

Environment
-----------
The code expects certain environment variables to be present for API
configuration.  You can create a `.env` file in the same directory and
populate it with keys like `OPENAI_API_KEY` or `SERPER_API_KEY`.  The
`dotenv` library is used to load these values at runtime.  If the keys are
missing, the system will still run using stubbed responses, but you will not
get real data.
"""

import os
import json
import uuid
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


class Blackboard:
    """A simple in‑memory key‑value store for agent communication.

    In a production system this might be backed by Redis, DynamoDB or another
    database.  Here we use a Python dictionary protected by a lock to ensure
    thread safety.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def write(self, key: str, value: Any) -> None:
        """Write a value to the blackboard under the given key."""
        with self._lock:
            self._store[key] = value
            print(f"[Blackboard] Wrote key={key}")

    def read(self, key: str) -> Any:
        """Read a value from the blackboard.  Returns None if missing."""
        with self._lock:
            value = self._store.get(key)
            print(f"[Blackboard] Read key={key} found={value is not None}")
            return value


class EventBus:
    """A simple publish/subscribe event bus.

    Each subscriber registers a callback that will be invoked whenever an
    event of the subscribed type is published.  Events are processed in
    separate threads so that publishers are not blocked by slow consumers.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._worker_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._worker_thread.start()

    def subscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to events of a given type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        print(f"[EventBus] Subscriber registered for event_type={event_type}")

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish an event with a type and payload."""
        event = {"type": event_type, "payload": payload}
        self._queue.put(event)
        print(f"[EventBus] Published event_type={event_type}")

    def _dispatch_loop(self) -> None:
        """Background thread that dispatches events to subscribers."""
        while True:
            event = self._queue.get()
            event_type = event["type"]
            payload = event["payload"]
            for callback in self._subscribers.get(event_type, []):
                # Call each subscriber in its own thread to avoid blocking others
                threading.Thread(target=callback, args=(payload,), daemon=True).start()


@dataclass
class Agent:
    """Represents an individual agent within a crew.

    Attributes:
        role: A human‑readable description of the agent's function.
        goal: A concise statement describing what the agent aims to accomplish.
        backstory: Additional context used for prompt engineering and agent memory.
        tool_functions: A dictionary of tool names to callables available to the agent.
        verbose: Whether to print debugging output during execution.
    """

    role: str
    goal: str
    backstory: str
    tool_functions: Dict[str, Callable[[str], str]] = field(default_factory=dict)
    verbose: bool = False

    def perform_task(self, description: str, expected_output: str, blackboard: Blackboard, event_bus: EventBus, task_id: str) -> str:
        """Execute a task and return its output.

        The default implementation simply returns a templated string.  Subclasses
        can override this method to integrate with real APIs (e.g. OpenAI or
        Serper) or other tools.  Results are written to the blackboard and an
        event is published upon completion.

        Args:
            description: A human‑readable task description.
            expected_output: A short description of the expected output format.
            blackboard: The shared blackboard instance.
            event_bus: The event bus for publishing completion events.
            task_id: A unique identifier for this task.
        """
        # Compose a simple output based on the agent's role and goal.  In
        # practice, this would be replaced by a call to an LLM or external API.
        output = (
            f"Agent: {self.role}\n"
            f"Goal: {self.goal}\n"
            f"Task: {description}\n"
            f"Generated on: {datetime.utcnow().isoformat()}\n\n"
            f"This is a placeholder output for {self.role}.  The expected output was: {expected_output}."
        )

        # Write the output to the blackboard
        blackboard.write(task_id, output)

        # Publish a completion event
        event_bus.publish(f"{self.role}_complete", {"task_id": task_id})

        if self.verbose:
            print(f"[Agent] {self.role} completed task_id={task_id}")

        return output


@dataclass
class Task:
    """Represents a single unit of work to be executed by an agent."""

    description: str
    expected_output: str
    agent: Agent
    async_execution: bool = False

    def run(self, blackboard: Blackboard, event_bus: EventBus, task_id: str) -> str:
        """Run the task via its agent and return the produced output."""
        if self.agent.verbose:
            print(f"[Task] Starting task_id={task_id} description='{self.description}'")
        return self.agent.perform_task(
            description=self.description,
            expected_output=self.expected_output,
            blackboard=blackboard,
            event_bus=event_bus,
            task_id=task_id,
        )


class Crew:
    """Coordinates a set of tasks executed by multiple agents."""

    def __init__(self, name: str, orchestrator: Agent, tasks: List[Task], blackboard: Blackboard, event_bus: EventBus) -> None:
        self.name = name
        self.orchestrator = orchestrator
        self.tasks = tasks
        self.blackboard = blackboard
        self.event_bus = event_bus
        # Register orchestrator completion handlers
        self._register_event_handlers()

    def _register_event_handlers(self) -> None:
        """Subscribe orchestrator to worker completion events."""
        for task in self.tasks:
            event_type = f"{task.agent.role}_complete"
            self.event_bus.subscribe(event_type, self._on_task_complete)

    def _on_task_complete(self, payload: Dict[str, Any]) -> None:
        """Callback invoked when a task completes.  Logs progress."""
        task_id = payload.get("task_id")
        if self.orchestrator.verbose:
            print(f"[Crew] {self.name} received completion for task_id={task_id}")

    def run(self) -> str:
        """Execute all tasks in sequence and return aggregated report."""
        report_sections: List[str] = []
        for idx, task in enumerate(self.tasks, start=1):
            task_id = str(uuid.uuid4())
            if self.orchestrator.verbose:
                print(f"[Crew] Running task {idx}/{len(self.tasks)} (ID={task_id})")
            output = task.run(self.blackboard, self.event_bus, task_id)
            report_sections.append(output)

        # Aggregate outputs into a single report
        report = "\n\n".join(report_sections)
        return report


def save_report(report: str, blueprint_id: str, out_dir: str = "outputs") -> str:
    """Save a report to disk and return the file path."""
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{blueprint_id}_{timestamp}.md"
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[save_report] Report saved to {filepath}")
    return filepath


def build_market_intelligence_crew(verbose: bool = False) -> Crew:
    """Create a Market Intelligence crew with sample agents and tasks."""
    blackboard = Blackboard()
    event_bus = EventBus()

    # Define agents
    orchestrator = Agent(
        role="Chief Strategist",
        goal="Orchestrate market analysis and synthesize an intelligence report",
        backstory=(
            "A seasoned business strategist who understands the byoungimprovements brand and "
            "knows how to delegate tasks to specialised agents."
        ),
        verbose=verbose,
    )

    trend_spotter = Agent(
        role="Trend Spotter",
        goal="Identify emerging trends in the personal and business development space",
        backstory="Skilled at analysing social media, news feeds and forums to detect shifts and patterns.",
        verbose=verbose,
    )

    competitor_analyst = Agent(
        role="Competitor Analyst",
        goal="Analyse competitor strategies and extract actionable insights",
        backstory="Expert in benchmarking competitor content and uncovering market gaps.",
        verbose=verbose,
    )

    audience_profiler = Agent(
        role="Audience Profiler",
        goal="Describe audience demographics, interests and pain points",
        backstory="Deep knowledge of psychographics and community sentiment.",
        verbose=verbose,
    )

    # Define tasks
    tasks = [
        Task(
            description="Research top five emerging trends relevant to early‑stage entrepreneurs.",
            expected_output="A list of five trends with supporting data and sources.",
            agent=trend_spotter,
            async_execution=False,
        ),
        Task(
            description="Analyse three major competitors and summarise their recent marketing strategies.",
            expected_output="A comparative overview highlighting key tactics and performance metrics.",
            agent=competitor_analyst,
            async_execution=False,
        ),
        Task(
            description="Create an audience profile for the target niche, including demographic and psychographic insights.",
            expected_output="A description of the target audience's age range, interests, pain points and aspirations.",
            agent=audience_profiler,
            async_execution=False,
        ),
    ]

    crew = Crew(
        name="Market Intelligence", 
        orchestrator=orchestrator, 
        tasks=tasks, 
        blackboard=blackboard, 
        event_bus=event_bus,
    )
    return crew


def main() -> None:
    """Entry point for running the Market Intelligence crew."""
    verbose = os.getenv("VERBOSE", "false").lower() == "true"
    blueprint_id = os.getenv("BLUEPRINT_ID", "market_intelligence_v1")

    crew = build_market_intelligence_crew(verbose=verbose)
    report = crew.run()
    save_report(report, blueprint_id=blueprint_id)


if __name__ == "__main__":
    main()