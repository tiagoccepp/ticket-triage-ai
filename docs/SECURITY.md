# Security & confidentiality notes

## Done

- Code-enforced validity gate: labels outside the taxonomy can never reach a
  queue or a route, regardless of what any model outputs.
- Append-only audit trail records every decision + rationale (inspectable,
  exportable, deletable per retention policy).
- Secrets from env/`.env` only; `.env` gitignored; live smoke prints key last4 only.
- CI runs fully keyless on the lexical backend — no customer-like text ever
  leaves the machine in tests (all fixtures synthetic).

## Not done (future work)

- No PII redaction on ticket title/body yet — customer text is stored as-is.
  Production needs the redact-before-store pattern (see the sibling
  support-agent project for the reference implementation) plus a retention
  window for bodies and payloads.
