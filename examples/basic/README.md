# basic

The smallest legal flow. One agent node, one gate, a deterministic
finish — I2 in six edges.

**Expected path:** `__start__ → build ⟲ gate-suite → __end__`. The
build loop repeats while the suite is red; the iteration budget and
dry-loop counter in the hook bound it.

**Gates used:** `gate-suite` — the project's own test command, bound
as `test_suite_cmd`.

**Evidence generated:** the suite's exit codes in the run journal
(red exits included); the FINISHED stop decision. No attest/ledger or
seals — this road has no tasks and no human node, which also means it
is only appropriate for work a green suite fully verifies.
