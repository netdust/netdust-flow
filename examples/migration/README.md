# migration

Schema/data migration with evidence at both ends: the walk cannot
reach the apply step until the backup command has exited 0 this run,
and cannot finish until verification is green AND a human has sealed
the result. Migrations are floor-class by definition — this road
assumes that.

**Expected path:** `__start__ → gate-backup → apply → gate-verify →
signoff (yield) → gate-signoff → __end__`. A failing backup yields to
a human `env` node (fix credentials, disk, target); resuming re-runs
the backup gate — it never assumes the fix worked. A failing verify
routes back to apply; a rejected sign-off does too.

**Gates used:** `gate-backup` (`backup_cmd`), `gate-verify`
(`verify_cmd`), `gate-signoff` (seal read).

**Evidence generated:** backup and verify exit codes in the journal
(including every red attempt), the migration seal, stop decisions. If
the migration is part of a larger delivery, run it as a task on the
deliver road instead and attest it — this standalone flow is for
operational migrations outside a feature.
