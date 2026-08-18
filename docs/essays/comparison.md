# Comparison — what category this is

The point is not that existing systems are wrong. They solve different
problems.

| System | Main purpose |
| --- | --- |
| Agent frameworks (LangGraph, CrewAI, …) | Coordinate model activity |
| Workflow engines (Temporal, Airflow, …) | Execute processes durably |
| CI systems (GitHub Actions, …) | Validate artifacts |
| netdust-flow | Control delivery authority |

**Agent frameworks** answer "how do I orchestrate models?" — routing,
memory, tool use, fan-out. Most let the model decide when it is done,
because for their general domains there is often no mechanical check
to require. netdust-flow's central mandate — a deterministic finish —
is the one property a horizontal framework structurally cannot impose.

**Workflow engines** answer "how does a process run reliably?" —
durability, retries, distributed execution. They are excellent at
executing a declared process and indifferent to who has the authority
to declare a step complete. netdust-flow is tiny precisely because it
outsources durability to git and session hooks and keeps only the
authority question.

**CI systems** answer "is this artifact valid?" — and netdust-flow
gates routinely *invoke* CI-shaped commands (suites, linters, diff
scans). But CI validates on push; it does not drive the loop, yield to
recorded human decisions, or derive delivery state from accumulated
evidence. Here the checks are the road, not a fence beside it.

**netdust-flow** answers one question the other three leave open: who
may advance and finish delivery? Its answer — verified evidence only;
agents route, gates and humans finish, and every human decision is a
recorded event — composes with all three categories rather than
replacing them. A gate can run your CI. An agent node can be driven by
any framework. The protocol only insists that none of them gets the
last word without evidence.

Use something else when: the work has no mechanical exit check
(open-ended research, ideation), when you need parallel orchestration
at scale (this is a solo-operation design), or when process durability
across infrastructure is the hard problem (that's Temporal's job, not
a Stop hook's).

---

## Addendum — the axis was never loops vs graphs

This comparison is framed around workflow shape (loops, graphs, CI,
orchestration). After the eval program that framing reads as too
shallow. The graph is not the fundamental point; it is a *mechanism*
for making one thing inspectable and enforceable: **who has authority
to advance and finish delivery.** The real axis is

    agent autonomy  ⟷  controlled delivery authority

and every system above sits somewhere on it. Agent frameworks maximise
autonomy; CI checks artifacts but holds no authority over the loop;
netdust-flow constrains autonomy *only* at the authority transitions
(intent, arming, evidence) and leaves the agent free to route
everywhere else. A loop with the same three recorded, enforced
transitions would make the same claim; a graph with none of them would
not. Compare systems by which authority transitions they make external
and checkable — not by whether they draw the work as a loop or a graph.
