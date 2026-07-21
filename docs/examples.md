# Examples — index

Four small flows under `examples/`, each lint-clean and each
demonstrating one protocol idea. They are illustrations: before
driving a real run, copy the flow next to your project's flows, bind
its commands, and run `flow-lint --compile` — the walker only trusts
a twin the lint wrote.

| Example | Demonstrates | Gates | Evidence |
| --- | --- | --- | --- |
| [`basic/`](../examples/basic/) | the minimum legal flow — I2 in six edges | suite | journal only |
| [`wordpress-plugin/`](../examples/wordpress-plugin/) | ledger-driven build + human shake-out seal | gate-check · ledger · seal | attest notes, seal, journal |
| [`security-sensitive-change/`](../examples/security-sensitive-change/) | floor-class work: two seals, review as a gate (I5 structural) | gate-check · review · suite · 2× seal | seals, review exits, journal |
| [`migration/`](../examples/migration/) | evidence at both ends: backup proven first, human sign-off last | backup · verify · seal | backup/verify exits, seal, journal |

Every example follows the same conventions as the production flows:
closed edge grammar (I1), finish only through gate or human (I2),
human nodes as yield points read back by seal gates (I4), and
project-specific commands as bound placeholders — the flow file
carries no judgment, only structure.
