# Agents may route. Only gates finish.

## An evidence-driven delivery protocol for AI-assisted software development

The most dangerous sentence in AI-assisted software delivery is:

> "Done."

Not because the work is necessarily finished.

Because someone decided it was.

A hallucinated API can be fixed. A wrong file can be replaced. An over-engineered abstraction can be removed. Those failures happen inside the work.

"Done" is different.

"Done" ends the work.

When the system that creates software is also allowed to decide that the software is complete, every safeguard downstream depends on the judgment of the least reliable participant in the process.

That is the fundamental problem with many AI-assisted development workflows.

The interesting question is not:

* Should agents use loops?
* Should agents use graphs?
* Should agents plan more effectively?

Those are routing questions.

The deeper question is:

> Who has authority to advance delivery state?

netdust-flow is built around a simple answer:

> Agents may route. Only gates and recorded human decisions may finish.

The implementation is intentionally small:

* a declarative YAML workflow graph
* one Claude Code Stop hook
* deterministic gate scripts
* recorded evidence and evaluation data

The code is not the main idea.

The main idea is the separation of **generation** from **authority**.

Agents create.

Evidence decides.

---

# The problem with agent-defined completion

Modern AI coding systems are increasingly capable of planning, editing, testing, and iterating.

That creates a natural temptation:

Give the agent tools.

Give it a loop.

Let it continue until it believes the task is complete.

This works surprisingly often.

The problem is that the final decision is still a judgment made by the same system that produced the output.

The model writes the code.

The model writes the tests.

The model evaluates the tests.

The model decides the work is finished.

The loop may be sophisticated, but the authority model has not changed.

The generator remains the judge.

That is the seam where trust breaks.

---

# Generation and verification must be separated

A useful architecture separates two responsibilities:

## Generation

Creating possibilities.

Examples:

* writing code
* proposing changes
* designing solutions
* suggesting next steps

## Verification

Determining whether reality matches expectations.

Examples:

* running tests
* checking builds
* validating schemas
* recording human approval

Large language models are powerful generators.

They are much less reliable as independent verifiers of their own work.

Research into LLM self-verification has demonstrated the problem: models can confidently produce incorrect evaluations of their own reasoning.

The architectural lesson is straightforward:

> The component that creates an artifact should not be the only component deciding whether the artifact is correct.

This is the same principle behind LLM-Modulo style approaches:

1. Let the model generate.
2. Use external verification.
3. Allow evidence to determine progress.

netdust-flow applies that principle to software delivery.

---

# netdust-flow: a delivery protocol

netdust-flow is not primarily an agent framework.

It is a delivery protocol.

A workflow is a versioned YAML graph.

There are three node types.

## Agent nodes

Agents perform work.

They can:

* inspect code
* write files
* run tools
* propose the next step

They cannot finish the workflow.

---

## Gate nodes

Gates perform verification.

They execute deterministic checks and produce evidence.

Examples:

* tests
* linters
* builds
* security checks
* policy checks

A gate does not say:

"Looks good."

A gate returns:

* success
* failure
* recorded evidence

---

## Human nodes

Humans provide explicit decisions.

A human decision is not an invisible interruption.

It is an event.

Approval becomes evidence.

Rejection becomes evidence.

No assumption is made from the fact that a session resumed.

Resuming work is not approval.

---

# The central rule: evidence changes state

The entire system can be summarized by one principle:

> Assertions do not change workflow state. Evidence does.

An agent saying:

> "The tests passed."

is an assertion.

A recorded successful test execution is evidence.

A task file saying:

> "Security review completed."

is an assertion.

An attested security review is evidence.

A conversation message saying:

> "The customer approved."

is an assertion.

A recorded approval seal is evidence.

The system treats claims as proposals.

Only evidence becomes state.

---

# The five invariants

Everything in netdust-flow follows from this principle.

## 1. Routing conditions must be machine-readable

A workflow transition must be something the system can evaluate.

Valid:

```
gate.exit == 0
```

Invalid:

```
if the work looks safe
```

The second example hides judgment inside the workflow.

A decision that cannot be evaluated is not a control.

---

## 2. Agents may route, but cannot terminate

Agents can decide:

"What should happen next?"

They cannot decide:

"The work is complete."

The exit state is protected.

`__end__` can only be reached through verified transitions.

---

## 3. Evidence is produced by verifiers

Progress cannot come from agent-written status.

The system does not care that an agent claims a test was run.

It cares that a test runner produced evidence.

---

## 4. Human decisions are explicit events

Humans are part of the protocol.

They are not exceptions to it.

A decision must be recorded before it affects state.

---

## 5. Important craft becomes evidence

A review that exists only in instructions is not a review.

A security checklist that nobody executes is not security evidence.

If something matters enough to influence delivery, it must become measurable.

---

# The first real run

Theory documents are cheap.

The real test is shipping something.

The first complete workflow built a WordPress form builder.

Because the project handled user input, it followed the more rigorous delivery path.

The workflow itself performed exactly as designed:

* ten stops
* seven iterations
* two human approval points
* every gate executed
* no manual overrides

The process was sound.

Then independent reviewers examined the delivered code.

They found eight escaped defects.

Three were high severity.

The result was important.

The workflow had not failed.

It had exposed its boundary.

The gates proved that verification happened.

They did not prove that the verification was strong enough.

The tests accurately tested the simulated environment.

The simulated environment did not fully reproduce platform behavior.

The lesson was not:

"More automation is needed."

The lesson was:

> Verification itself must become measurable.

That produced a new design requirement:

Reviews must become evidence-producing tasks rather than optional descriptions.

---

# The system can guarantee the road, not the traveler

This distinction matters.

A workflow system can guarantee:

* valid transitions
* required checks
* recorded decisions
* evidence history
* reproducibility

It cannot guarantee:

* that every test is good
* that every reviewer is correct
* that every assumption is valid

No process can remove uncertainty completely.

The purpose of the system is not perfection.

The purpose is visibility.

When something fails, the system should reveal:

* where it failed
* why it failed
* which assumption was wrong
* what changed afterward

---

# The Bitter Lesson: what survives better models?

A reasonable objection is:

"Won't better models make all this unnecessary?"

Possibly some of it.

Many parts of AI infrastructure are temporary.

Prompt engineering.

Routing strategies.

Task decomposition.

Agent instructions.

These are capability infrastructure.

Better models replace capability infrastructure.

Evidence infrastructure behaves differently.

Exit codes.

Attestations.

Audit trails.

Recorded decisions.

These become more valuable as systems become more autonomous.

A perfect model would still need to prove:

* which commit was tested
* which checks ran
* which decisions were made

Evidence is not a workaround for weak models.

Evidence is what makes strong models trustworthy.

---

# Measure instead of believing

The important question is not:

"Does this architecture sound right?"

The question is:

"Does it reduce escaped defects?"

Every workflow execution produces a journal:

* gate executions
* failures
* human decisions
* attestations
* workflow version

The evaluation loop is simple:

```
Run workflow

      ↓

Measure outcomes

      ↓

Modify YAML

      ↓

Run again
```

The metric that matters is not:

"Did the agent feel finished?"

It is:

> What escaped verification?

The first run produced eight escaped defects.

Future runs should reduce that number.

If they do not, the design must change.

---

# Why this matters beyond netdust-flow

General-purpose agent frameworks solve a different problem.

They answer:

"How do we coordinate intelligent systems?"

netdust-flow answers:

"Who is allowed to say the work is complete?"

In domains where mechanical verification exists, this distinction matters.

Software delivery has:

* tests
* builds
* linters
* migrations
* security scanners
* review processes

Those are opportunities for evidence.

The opportunity is not simply making agents more autonomous.

The opportunity is making autonomous delivery accountable.

---

# Conclusion

The future of software development will likely involve increasingly capable agents.

The important architectural question will not be:

"How much can the agent do?"

It will be:

"Who has authority to decide that what it did is correct?"

netdust-flow chooses a strict answer:

The model does the work.

The model proposes the route.

The model never gets the last word.

**Agents may route. Only gates finish.**
