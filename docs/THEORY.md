# Research Verdict: The Theoretical Basis of netdust-flow

*Deep-research protocol: 16+ sources, credibility-scored, triangulated,
stress-tested through a structured three-position debate. July 2026.*

netdust-flow's architecture: work declared as a versioned graph of
**agent**, **gate**, and **human** nodes; edges conditioned only on
machine-readable state; an LLM may route but never finish (`__end__`
reachable only via gate or human — invariant I2); a bounded, stateless
walker; craft (skills/agents) referenced by nodes, never embedded.

---

## TL;DR

netdust-flow is not a novel idea — it is the deliberate intersection of
four established results: LLMs cannot reliably verify their own work
(Kambhampati et al., ICML 2024); external mechanical verification is
where reliability actually comes from (LLM-Modulo; MAST); declared,
inspectable, terminating control structures are formally superior to
opaque LLM scheduling for well-specified engineering work (workflow-net
soundness 1997→2011; scheduler-theoretic analysis 2026); and simple
predefined workflows outperform autonomous agents on well-defined tasks
(Anthropic, and production practice). The one serious counter-position —
the Bitter Lesson, that model progress will obsolete the scaffold — is
real but priced in: the system's only durable asset is a declarative
file, its runtime is ~500 lines, and its gates would be required even
with perfect models, because they are the *evidence*, not the crutch.

---

## Research Vectors

| Vector | Status | Key Finding |
|---|---|---|
| Factual timeline | ✅ | ReAct loop (2022) → multi-agent wave (2023–24) → "loop engineering" named practice (June 2026, 8.5M-view catalyst) → "loops or graphs?" opened July 18, 2026, unresolved |
| Causal analysis | ✅ | Loops fail for structural reasons: opaque scheduling, implicit dependencies, unbounded recovery, unreliable self-verification |
| Structural changes | ✅ | Field converging on graphs + durable execution + validated outputs; formal machinery (soundness, termination proofs) arriving from academia |
| Contested claims | ✅ | Scaffolding-obsolescence (Bitter Lesson) vs. design-over-models (MAST); genuinely open |
| Data / metrics | ⚠️ | Strong failure-mode data (MAST: 1,600+ traces); graph-vs-loop *gain* numbers still mostly unvalidated predictions |
| Forward implication | ✅ | Verification layer appreciates as models improve; orchestration layer depreciates — invest accordingly |

---

## Core Findings

**1. LLM self-verification is empirically unreliable; external sound
verification is where gains come from.** `[HC]`
Kambhampati et al.'s ICML 2024 position paper argues autoregressive
LLMs cannot by themselves do planning or self-verification, proposing
LLM-Modulo: LLMs generate, external verifiers check. The supporting
experiments are stark — on graph coloring, GPT-4's accuracy *fell* in
self-critique mode because its verification produced hallucinated
violations; on planning, self-critique showed high false-positive
verification rates, while feedback from an external sound verifier
produced the real accuracy improvement (Stechly, Valmeekam,
Kambhampati 2023–24). This is the direct theoretical warrant for
invariant I2: *agents may route; only gates and humans finish.* An
LLM verdict is a low-reliability validator; an exit code is a
high-reliability one.

**2. The validation gap is formal: system correctness is bounded by
the product of validator reliabilities.** `[HC as theory]`
The Graph Harness position paper (arXiv 2604.11378, Apr 2026) proves a
conditional-soundness bound: Pr[all outputs correct] ≥ Π pᵥ, where pᵥ
is each node's validation reliability. Code-based validation has
pᵥ ≈ 1; LLM-based semantic validation has pᵥ significantly below 1.
Consequence for netdust-flow: every joint where a gate replaces a
verdict raises the product; every remaining agent-written signal
(e.g., task checkboxes feeding the ledger) is a below-1 factor the
theory itself flags. The known checkbox seam is not just an
engineering TODO — it is the system's dominant term in this bound.

**3. Failure data locates the problem where netdust-flow aims.** `[HC]`
MAST (NeurIPS 2025; 1,600+ annotated traces, 7 frameworks, κ = 0.88)
clusters 14 failure modes into specification/design (~42% — including
missing termination conditions), inter-agent misalignment (~37%), and
task verification (~21%). The authors' conclusion: failures stem from
system design, not just model limitations, and gains come from
refining system design rather than waiting for better models.
Declared specs with structural gates (gate-check), enforced
termination (walker budgets), and mechanical verification address the
first and third categories head-on; netdust-flow's single-session
node execution largely sidesteps the second.

**4. The agent loop is formally a non-deterministic single-ready-unit
scheduler; declared graphs make the policy inspectable.** `[HC as
framework; MC as performance claim]`
The scheduler-theoretic framework characterizes the dominant loop
paradigm as |U| ≤ 1 with the next step chosen by opaque LLM inference,
with three structural weaknesses: implicit dependencies, unbounded
recovery, mutable execution history. Notably for netdust-flow's
design point, the paper's 70-system survey observed failure-loop
behavior in 3 of 4 flexible graph/flow orchestration systems and 0 of
7 state-machine systems — constrained, declared control flow beat
expressive dynamic graphs on exactly the pathology that matters. Its
termination theorem (bounded time under per-node timeouts and retry
budgets) is the formal version of the walker's iteration budget and
dry-loop guard. Its performance predictions (G_graph > 0 etc.) remain
explicitly unvalidated — treat as hypotheses.

**5. Termination and reachability guarantees are 30-year-old settled
theory, not AI novelty.** `[HC]`
Van der Aalst's workflow nets (1997; classification and decidability
in *Formal Aspects of Computing* 2011) define soundness for a net
with a start and end place: from every reachable state proper
termination remains possible, completion is proper, and no transition
is dead — decidable, tool-checked (Woflan) since the nineties.
flow-lint's invariants are a vertical restatement: every node
reachable from `__start__`, `__end__` reachable, deterministic
routing, finish only through gate/human. netdust-flow inherits
Business Process Management's formal ancestry; the new element is
only what the nodes contain.

**6. For well-defined tasks, predefined workflows beat autonomous
agents — the industry position, stated by the vendor with the least
incentive to say it.** `[MC→HC by triangulation]`
Anthropic's *Building Effective Agents* draws the architectural line:
workflows orchestrate LLMs through predefined code paths, offering
predictability and consistency for well-defined tasks; agents are for
open-ended work where structure cannot be pre-articulated; start with
the simplest solution. Practitioner corroboration: the most reliable
production agentic systems today are workflows. Related empirical
signals point the same way — structured planning scripts raised
enterprise tool-calling accuracy from 41% to 96% (Routine), and
WorfBench measured a 15% capability gap between sequence and graph
planning even in frontier models, bounding what planner-authored
graphs can be trusted to invent — supporting human-authored flows.

**7. The discourse is days ahead of the tooling, and both are moving
toward this design point.** `[MC]`
"Loop engineering" became a named practice within weeks of the June 7
catalyst post (8.5M views); the "did we shift to graphs yet?" question
opened July 18 and is unresolved (2.7M views, 1,200 replies). Current
tools each hold one property netdust-flow composes — durable graphs
(LangGraph 1.0, Smithers), declarative versioned files (Callee),
deterministic action steps (acpx) — but none *mandates* deterministic
finish, because horizontal frameworks cannot: most of their users'
domains have no mechanical exit check to require. A vertical system
can afford the mandate. That is a structural explanation, not a
mystery.

---

## The Debate

### 🐂 Bull — the design is theoretically over-determined
- Four independent literatures (verification limits, failure
  taxonomy, scheduler theory, workflow soundness) each separately
  imply a piece of the architecture; their intersection *is* the
  architecture.
- The measured failure distribution (MAST) maps onto the design:
  spec gates for the 42%, mechanical verification for the 21%,
  bounded termination for the loop pathologies.
- The strongest empirical numbers available (Routine 41→96%,
  external-verifier gains in the Kambhampati experiments,
  state-machine 0/7 vs. flexible-graph 3/4 failure loops) all favor
  structure over judgment.
- The system's cost basis is minimal: ~500 new lines on tested gate
  scripts, one declarative file format. The theory is load-bearing;
  the implementation is not a bet.

### 🐻 Bear — the theory is thinner than it looks, and time is against it
- The flagship theoretical ally (Graph Harness) is a *position paper*:
  no implementation, no experiments, single author, its performance
  claims self-declared unvalidated. Citing proofs about termination
  is not evidence of better delivered websites.
- The Bitter Lesson cluster: architectural assumptions may be
  obsolete within months as models improve; "as base models improve,
  the marginal benefit of complex scaffolding will likely decrease"
  (arXiv 2602.21193). Better models internalize procedures; harnesses
  get stripped, not grown.
- Thm 6.3 cuts inward: netdust-flow's own FINISHED still multiplies
  in an agent-written factor (checkboxes). By its own theory the
  system is only as sound as its weakest validator — and that seam is
  open.
- n = 1: every reliability number cited comes from other people's
  benchmarks. Zero flow-driven production deliveries exist. A theory
  document without a delivery ledger is exactly the "green tests,
  zero deliveries" theater the project warned itself about.

### 🔩 Structural — what actually changed at the plumbing level
- Verification asymmetry is the deep mechanic: generation is
  stochastic and improving; *evidence* (exit codes, manifests,
  traces) is deterministic and auditable. Layers that produce
  evidence appreciate as agents do more; layers that produce
  judgment depreciate. Gates are evidence machinery, not capability
  scaffolding — the Bitter Lesson applies to the second, not the
  first.
- Horizontal frameworks structurally cannot mandate deterministic
  finish (their users' domains lack exit checks); vertical systems
  can. The absence of I2 in the field is market structure, not
  refuted design.
- The scaffold literature already names netdust-flow's trade:
  pipeline-based scaffolds "trade generality for stability and cost
  control" (SWE-RL related work). netdust-flow is the hybrid — 
  agentic *inside* nodes, pipeline *between* them — taking frontier
  capability where it helps and determinism where it counts.
- The file-outlives-runtime bet restructures the obsolescence risk:
  if models improve enough to collapse nodes, the graph shrinks by
  editing YAML; the invariants survive at any graph size, including
  trivial ones.

### Debate Rounds

**Round 1 — Core Disagreement**
🐂 *Thesis:* deterministic-finish graphs are the theoretically correct
architecture for solo AI-assisted code delivery, and the literature
now proves it. Falsifiable: flow-driven deliveries should show fewer
escaped defects and interventions than the prose-era harness.
🐻 *Rebuttal:* the literature proves loops fail and self-verification
fails; it does not prove *this* composition wins — no controlled
study of gated graphs vs. strong loop baselines exists (Graph Harness
G0 comparison: designed, never run).
🔩 *Mechanism:* both are downstream of validator reliability pᵥ. The
bull's case is that netdust-flow maximizes Π pᵥ; the bear's case is
that the product still contains agent-written factors and no field
measurement.

**Round 2 — Evidence Contest**
🐂 *Strongest data:* external sound verifiers produce the accuracy
gains that self-critique cannot (Kambhampati experiments) — the exact
substitution netdust-flow performs at every gate.
🐻 *Counter-data:* "the marginal benefit of complex scaffolding will
likely decrease" as models improve — stated in current ML literature,
and consistent with every prior capability wave.
🔩 *What the data measures:* the Kambhampati results measure
*verification*, the scaffolding claim measures *capability
assistance*. They are about different layers; both can be true.
netdust-flow survives both exactly insofar as its machinery is
verification, not assistance. Audit line: any gate that exists to
help the model rather than to check it is Bitter-Lesson-exposed.

**Round 3 — Forward Implication**
🐂 *If bulls are right:* within ~6 months of adoption, the delivery
ledger shows fewer escapes and less babysitting than the legacy
harness; the theory doc becomes a credibility asset; the vertical
pattern (declared graph + mechanical gates) is where the field lands,
and the studio got there a year early.
🐻 *If bears are right:* within 2–3 model generations, single-session
agents with internalized planning and near-reliable self-checking
make the graph overhead pure ceremony; maintenance of flows, lint,
and walker becomes drag; Smithers-class runtimes absorb the niche.
🔩 *Deciding conditions:* (1) does closing the checkbox seam
measurably reduce escapes (validation-gap theory says yes); (2) do
flow-run metrics beat the legacy baseline on the same evals; (3) does
any frontier model demonstrate *sound* self-verification on formal
tasks — the single result that would genuinely retire I2. Watch that
literature; nothing else in the bear case retires it.

---

## Synthesis

The honest structure of the theoretical basis is a two-layer
argument, and it is important not to blur the layers.

The first layer is close to settled. LLMs are unreliable verifiers of
their own and each other's work; this is peer-reviewed, replicated
across reasoning and planning domains, and mechanistically explained
(approximate retrieval does not implement sound checking). Systems
that route the verification function to external, mechanical checkers
gain accuracy; systems that let the generator grade itself do not,
and sometimes get worse. Meanwhile the largest failure study in the
field finds that agent systems break primarily on specification,
termination, and verification — design-layer properties — and the
formal machinery for guaranteeing exactly those properties
(reachability, proper completion, bounded termination) has existed in
workflow theory since 1997 and in scheduler theory forever. On this
layer, netdust-flow is orthodox: I1 and I2 are a Petri-net soundness
discipline applied to LLM nodes, the walker is a bounded scheduler
with an inspectable policy, and the gate/verdict distinction is
LLM-Modulo with exit codes. Nothing here depends on a fashionable
paper; most of it predates LLMs.

The second layer is a live bet, and should be named as one. Whether
this architecture *outperforms* a strong modern loop on real delivery
work is empirically open — the one paper that formalizes the
comparison explicitly declined to run it. And the Bitter Lesson
pressure is real: every month of model progress erodes some scaffold
somewhere. The structural analysis gives the bet its terms:
netdust-flow's machinery survives model progress precisely to the
degree that it is *evidence infrastructure* (gates, manifests,
traces, human seals) rather than *capability assistance* (routing the
model can learn, decomposition the model can do). The design already
leans the right way — gates are checks, not crutches; the graph is a
contract, not a prompt — and its cost basis (~500 lines on
pre-existing tested scripts, one file format) makes the downside a
day's write-off rather than a platform migration. The final word
belongs to the delivery ledger, not the literature: the theory earns
the word "basis" the day the evals pass on flow-driven work and keep
passing.

---

## Confidence Assessment

| Claim | Confidence | Key Evidence | Contested By |
|---|---|---|---|
| LLM self-verification unreliable; external verification is the gain | [HC] | ICML 2024 + experiments (self-critique hurts; sound verifier helps) | Future models with sound self-check (none demonstrated) |
| Verification/termination/spec gaps are the measured failure classes | [HC] | MAST, 1,600+ traces, NeurIPS 2025 | — |
| I2-style invariants formally guarantee termination/reachability | [HC] | WF-net soundness 1997/2011; termination theorem (2026) | — (as theory) |
| Declared workflows preferable for well-defined tasks | [HC/MC] | Anthropic; production practice; Routine 41→96; state-machine failure data | Definitional drift critiques; task-class boundary |
| Gated graphs *outperform* strong loops on delivery outcomes | [MC→open] | Convergent inference; no controlled study | Graph Harness's own unvalidated status; Bitter Lesson |
| Scaffolding obsolescence retires this design | [LC] | Bitter-lesson essays; one arXiv aside | Evidence-vs-assistance distinction; MAST design-over-models finding |

## Limitations & Unknowns

Honest gaps, not boilerplate. (1) The strongest framework ally is an
unimplemented position paper; treating its theorems as validation of
*outcomes* would be pattern-matching — they validate *structure*.
(2) All quantitative reliability numbers are from other domains and
benchmarks; nothing here measures WordPress delivery at n = 1. The
seven-group ablation that would attribute gains to graph structure has
been designed by others but run by no one. (3) The checkbox seam
means netdust-flow currently violates its own strongest theorem at
one joint; the theory basis is also a to-do list. (4) The survey
window for the discourse is one week old in a field moving weekly;
the repo landscape section will age fastest. (5) What would change
the conclusion: a demonstrated sound LLM self-verifier on formal
tasks (retires I2's necessity), or flow-run evals underperforming the
legacy harness (retires the composition, keeps the theory).

## Addendum (v0.2, July 2026) — The Machine, Named

The July 2026 FSM discourse (the "state machines in 2 minutes" thread
and the "From Loops to Graphs" explainer) restated a claim this
project had been circling: agent graphs are finite state machines
rediscovered, and any such system should survive being written as the
classical 5-tuple M = (S, Σ, δ, s₀, F). Auditing netdust-flow v0.1
against that definition was productive — it passed four-fifths of it
and failed one component in a way that produced two concrete,
reproducible defects. Both are fixed in v0.2; the audit and the fixes
are recorded here because the failure mode generalizes.

**The mapping.** S = declared nodes plus the pseudo-states; δ = the
edge list, deterministic by first-match with lint-enforced `when`
coverage; s₀ = `__start__`; F = `{__end__}`. In statechart terms
(Harel 1987) the walker implements run-to-completion microsteps:
gate nodes are *transient* states resolved within one walk, agent and
human nodes are *stable* states that await the next event. Gate
execution is deliberately Moore-flavored — the check runs because the
machine occupies the checkpoint, regardless of the arriving edge —
which is what makes the revisited-gate guard coherent. One deliberate
deviation from textbook FSM semantics stands: an event with no
matching edge BLOCKS rather than staying put. Stay-put is right for
UIs; fail-closed is right for delivery gating.

**The finding: Σ was incomplete.** The machine's input alphabet had
exactly one event — "the session stopped" — enriched into a real
signal only where a gate converted it into an exit code. Agents were
correctly barred from injecting events (I2). Gates injected them
soundly. Humans had no channel at all, so all human-borne information
collapsed into the one contentless event, with two consequences,
both verified against v0.1 by direct execution:

1. `__human__` was an *absorbing non-final state* — declared with no
   out-edges (by construction) yet not in F. A `[HUMAN]` task in the
   deliver flow parked the marker there permanently; the flow could
   never resume mechanically after the human resolved the blocker.
2. "A start node of kind human counts as satisfied" made resumption
   carry approval semantics it does not have. A session resumed to
   report *shake-out failed* FINISHED and disarmed the flow.

**The fix is I3 extended to humans (now I4).** The system already
held that nothing an agent asserts is a state signal; v0.1's human
handling was weaker still — it treated an assertion nobody made
(resumption) as a decision. v0.2 makes human decisions evidence:
`seal.py record` writes the decision into git notes exactly as
`attest.py` writes check results, and an ordinary gate after each
human node reads it back as an exit code. Approval, rejection, and
absence-of-decision each travel their own edge; `__end__` becomes the
only final state (lint-enforced: dead-end nodes FAIL, `__human__`
WARNs); the walker itself needed almost no change, which is the
strongest available evidence that the architecture was right and only
the alphabet was short. Under the Thm 6.3 framing: the human joint
was a pᵥ ≈ unknown validator implemented as *inference from silence*;
it is now a mechanical read of a recorded event, and the product
Π pᵥ loses its least defensible factor.

**Adjacent seams closed in the same pass.** The dry-loop counter no
longer eats agent-written checkboxes when a verifier's signal exists
(the walker prefers a gate-emitted `progress:` line — the ledger's
attest counts — over tasks.md counting); the ledger's FINISHED now
requires a clean worktree, closing tree-level drift that the
SUITE-on-HEAD rule missed; floor-check fails closed when its base ref
cannot be resolved instead of silently scanning a partial diff; the
schema is actually enforced at lint time (typo'd keys can no longer
degrade into unconditional edges); and the retired `pass:` field is
gone — a gate's out-edges are the single source of routing truth, and
a gate whose result no edge consumes fails the lint.

**Honest residue.** Seals are latest-wins: an approval can go stale
if the sealed artifact changes afterwards without a re-seal (records
carry the tree hash for audit; stricter freshness is deferred until a
drill shows a leak). Iteration and dry-loop budgets still live in the
hook, not the declared graph — the YAML under-describes termination;
moving budgets into guarded edges is the natural next formalization.
And the trust boundary is named, not enforced: git notes, the marker,
and the compiled twins are all forgeable by an agent with bash until
the pretooluse guard covers them.

---

## Key Sources

| Source | Score | Why It Matters |
|---|---|---|
| Kambhampati et al., *LLMs Can't Plan, But Can Help in LLM-Modulo Frameworks*, ICML 2024 + Stechly/Valmeekam self-verification papers | 10 [HC] | The verification asymmetry; external-verifier gains; warrant for I2 |
| Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (MAST), NeurIPS 2025 | 11 [HC] | Failure distribution: spec 42% / misalignment 37% / verification 21%; design-over-models |
| Hu Wei, *From Agent Loops to Structured Graphs*, arXiv 2604.11378 (2026) | 10 [HC theory / MC claims] | Scheduler framework; termination theorem; validation-gap bound (Thm 6.3); 70-system survey |
| van der Aalst, *Verification of Workflow Nets* (1997); *Soundness of Workflow Nets* , FAoC (2011) | 9 [HC, dated] | Soundness = proper termination + no dead transitions; decidable, tool-checked; flow-lint's ancestry |
| Anthropic, *Building Effective Agents* | 9 [MC] | Workflows vs. agents line; simplest-solution doctrine |
| *Uncovering Infinite Agentic Loops* (IAL-SCAN), arXiv 2607.01641 (2026) | 9 [MC] | Infinite loops as formal failure class; loop-dependence graphs; validates budgets/dry-guard |
| steipete posts (Jun 7 / Jul 18, 2026) + loop-engineering literature | 7 [MC] | Discourse timeline; the open graphs question |
| Harel, *Statecharts: A Visual Formalism for Complex Systems* (1987) | 9 [HC, dated] | Transient vs. stable states; run-to-completion semantics — the walker's formal shape |
| Classical FSM definition (5-tuple; Mealy/Moore; DFA determinism) via the Jul 2026 explainers (DavidKPiano thread; "From Loops to Graphs") | 8 [HC as theory / MC as discourse] | The audit frame for the v0.2 addendum: Σ-completeness surfaced both v0.1 defects |
| Bitter-lesson cluster (Sutton via practitioner essays; arXiv 2602.21193 aside; SWE-RL scaffold-family analysis) | 6–8 [LC–MC] | The genuine counter-position and the pipeline-scaffold trade |
| Routine / TDP / WorfBench (via Graph Harness related work) | 8 [MC] | Structure gains 41→96%; context isolation −82% tokens; 15% planner graph gap |
