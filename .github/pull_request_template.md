## What & why
<!-- One or two sentences. Link the checkpoint/slice, e.g. CP4 / S1. -->

## How it was verified
<!-- Tests added, commands run, manual checks. -->

## Checklist
- [ ] Tests written first; happy, bad-input, edge and failure paths covered
- [ ] No layer violations; dependencies injected
- [ ] Inputs validated; authorization checked
- [ ] Outbound calls have timeouts (and retries/breaker where relevant)
- [ ] Idempotency decided for every write
- [ ] Logs (no PII), metrics, traces added
- [ ] Migration is backward compatible
- [ ] Docs updated (07 system doc, 08 concepts, ADR if a decision was made)
