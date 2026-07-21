# security-sensitive-change

The road for floor-class work — auth, user-input handling,
schema/migrations, payments. Two human seals bracket the build, and
the independent review is a gate of its own rather than a craft
declaration: run 0001 measured what happens when review is prose
(eight escaped defects), so here its absence blocks the walk.

**Expected path:** `__start__ → plan → gate-plan → approve (yield) →
gate-approval → build → gate-review → gate-suite → signoff (yield) →
gate-signoff → __end__`. Any red gate routes back to build; a
rejected approval reopens the plan; a rejected sign-off reopens the
build.

**Gates used:** `gate-plan` (`gate_check_cmd`), `gate-approval` /
`gate-signoff` (seal reads), `gate-review` (`review_check_cmd` — a
command that runs an independent reviewer and exits non-zero on
findings), `gate-suite` (`test_suite_cmd`).

**Evidence generated:** two seals; the review gate's exit codes in
the journal (a red review is recorded history, not a vanished
conversation); suite exits; stop decisions.
