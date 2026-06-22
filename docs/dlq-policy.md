# Dead Letter Queue (DLQ) & Agent Health Policy

This policy formalizes how the Blueprint Builder handles "dead" agents and events
that cannot be processed. It implements the *Formalize "Agent Health" & Dead
Letter Queues* item from the [improvement backlog](./improvements.md) and applies
to every event-driven message bus topic in the Data Plane (see
[02-multi-agent-ecosystem.md](./02-multi-agent-ecosystem.md#241-event-driven-communication-bus)).

## Goals

- Prevent a single failing agent or poison-pill event from exhausting resources
  or stalling a crew.
- Guarantee that no event is silently lost — every unprocessable event lands
  somewhere a human can review it.
- Make agent failure observable and recoverable through automated reboot or
  quarantine.

## Retry policy

Each consumer processes an event inside a bounded retry loop before the event is
considered undeliverable.

| Parameter | Default | Notes |
|-----------|---------|-------|
| `max_retries` (N) | `5` | Maximum processing attempts before routing to the DLQ. |
| Backoff | Exponential with jitter | e.g. `2s, 4s, 8s, 16s, 32s`. |
| Visibility timeout | `> p99` task duration | Prevents duplicate concurrent processing. |
| Idempotency | Required | Consumers key on `task_id` so retries do not double-produce. |

Transient failures (timeouts, 5xx from third-party APIs, rate limits) are
retried. Deterministic failures (schema validation errors, 4xx, unparseable
payloads) are sent to the DLQ immediately — retrying them only wastes resources.

## Routing to the DLQ

When an event exhausts `max_retries` (or fails deterministically), it is moved to
a per-topic DLQ (e.g. `<topic>.dlq`) as a **DLQ entry**:

```json
{
  "schema_version": "1.0.0",
  "original_topic": "research.complete",
  "task_id": "1f1b9c2e-...",
  "crew": "market_intelligence",
  "consumer_agent": "scriptwriter",
  "failure_reason": "SchemaValidationError: payload missing 'outline'",
  "failure_class": "deterministic",
  "attempts": 5,
  "first_failed_at": "2026-06-22T16:00:00Z",
  "last_failed_at": "2026-06-22T16:01:02Z",
  "original_event": { "...": "verbatim copy of the failed event" }
}
```

The DLQ entry preserves the original event verbatim so it can be replayed after
the root cause is fixed.

## Agent health: reboot and quarantine

Failures are tracked per agent instance over a sliding window:

- **Reboot** — if an agent's failures are likely environmental (e.g. a crashed
  worker, stuck connection), the runtime restarts the agent instance and resumes
  consumption.
- **Quarantine** — if an agent exceeds a failure-rate threshold within the window
  (e.g. `> 50%` failures over the last `20` events, or `≥ 3` consecutive
  reboots), it is removed from the active pool and stops consuming. This prevents
  a misbehaving agent from draining a topic into the DLQ and exhausting API
  budgets.
- Quarantine and DLQ routing both raise an **alert for human review** via the
  Control Plane (see
  [05-governance-security.md](./05-governance-security.md#53-monitoring-evaluation-and-human-in-the-loop-oversight)).

| Health parameter | Default |
|------------------|---------|
| Failure window | last `20` events / `15` min |
| Quarantine threshold | `> 50%` failure rate or `≥ 3` consecutive reboots |
| Reboot cap before quarantine | `3` |

## Human review & reprocessing

1. A DLQ alert surfaces in the Control Plane dashboard with the failure reason
   and a link to the DLQ entry.
2. A human (or an automated remediation rule) diagnoses the root cause.
3. Once fixed — code patch, schema update, or upstream data correction — the
   entry is **replayed** back onto its `original_topic`. Because consumers are
   idempotent on `task_id`, replay is safe.
4. Entries that are intentionally discarded are marked `resolved: dropped` with a
   reason, so the DLQ never accumulates silently.

## Observability

- DLQ depth per topic and quarantined-agent count are first-class metrics on the
  Performance Analytics dashboard; non-zero values trigger alerts.
- Every retry, reboot, quarantine, and replay is logged with the `task_id` and
  `trace_id` for end-to-end tracing.
