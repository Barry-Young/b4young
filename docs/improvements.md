# Implementation-Focused Improvement Backlog

The Blueprint Builder framework provides a robust conceptual foundation for an
autonomous enterprise. While high-level clarity and documentation are covered
well, the following improvements deepen the framework by focusing on the
**operational bridge** between the architecture and the implementation logic
(e.g., the `MarketIntelligenceCrew` code). Each item below is a candidate work
item to formalize as the system is built.

## Backlog

- [ ] **Automated Feedback Loops for the "Brand Constitution."** The current
  framework describes the Brand Constitution as a static or manually updated
  policy. Specify an automated feedback loop where KPIs from the *Performance
  Analytics & Insights Dashboard* directly inform prompt adjustments. For example,
  if the *Engagement Bot* consistently sees high bounce rates on specific phrase
  types, the system should automatically flag those phrases for blacklisting in
  the Constitution, creating a self-healing governance model.

- [x] **Formalize "Agent Health" & Dead Letter Queues (DLQ).** While the
  architecture discusses resilience, it lacks a defined protocol for "dead"
  agents. Add a section on implementing Dead Letter Queues (DLQs) for the
  event-driven bus. If an agent fails to process an event after *N* retries, the
  event should be moved to a DLQ for human review, and the agent should be
  automatically "rebooted" or quarantined to prevent resource exhaustion.
  → Drafted in [dlq-policy.md](./dlq-policy.md).

- [ ] **Version Control for "Prompt-as-Code."** To elevate the Brand
  Constitution, treat it as a software repository rather than a document. Adopt a
  Git-based workflow where updates to the Brand Constitution (prompt engineering
  templates, forbidden lists) undergo pull requests and automated testing against
  a "golden dataset" before deployment. This ensures changes to the brand voice
  are versioned and auditable.

- [x] **Blackboard Schema Standardization.** To avoid integration friction
  between different agent crews, define a strict schema for the *Blackboard*.
  Mandate that all agents read/write using a versioned JSON schema. This ensures
  the *Market Intelligence* crew produces output that the *Content Factory* can
  immediately ingest without custom parsing, significantly reducing operational
  fragility. → Drafted in
  [schemas/blackboard.schema.json](./schemas/blackboard.schema.json).

- [ ] **Operationalizing "Human-in-the-Loop" (HITL) Logic.** Move HITL from a
  conceptual checkpoint to a formal API state. Define an `AWAITING_APPROVAL`
  status in the system architecture. When the *Executive Producer* generates a
  content plan, the Data Plane places the assets in a holding state, and the
  Control Plane exposes a specific endpoint for human verification — providing a
  programmatic guarantee that no content is published without a green-light.

- [ ] **Resource Allocation Logic for Orchestrators.** The framework mentions
  that Orchestrators modulate resource allocation but doesn't define the trigger.
  Specify a *Task Complexity Score* — calculated based on sub-task depth and
  required API calls — that the Orchestrator uses to decide whether to run a task
  as a light serverless function or a sustained containerized service.

## Summary of Source-Based Suggestions

- **For Strategy:** The existing document covers core readability and glossary
  gaps well.
- **For Technical Execution:** Focus on the implementation specifics found in the
  current `MarketIntelligenceCrew` Python scripts, ensuring that the documentation
  reflects the actual asynchronous communication patterns being coded.

## Next Artifacts

Two concrete artifacts that advance this backlog and standardize communication
between agent crews have been drafted:

1. ✅ A sample **Dead Letter Queue (DLQ) policy** for the event-driven bus —
   [dlq-policy.md](./dlq-policy.md).
2. ✅ A **JSON schema template for the Blackboard** to standardize inter-crew
   communication — [schemas/blackboard.schema.json](./schemas/blackboard.schema.json).
