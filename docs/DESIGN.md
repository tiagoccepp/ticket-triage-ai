# UI design contract — Ticket Triage AI ("Desk")

Family: dark ops console shared across the portfolio (Sora display / Public Sans body /
JetBrains Mono data, self-hosted woff2 inlined by `scripts/inline_fonts.py`).
Edit `src/static/ui.src.html`, regenerate with `python scripts/inline_fonts.py`.

## Palette (OKLCH-tuned hex)

- `--bg: #0B0F14` · `--panel: #10161D` · `--raised: #151D26`
- `--line: rgba(233,237,242,.09)` · `--text: #E8EDF2` · `--muted: #93A1B0`
- `--accent: #4CC3FF` (sky — flow/routing; the ONE accent)
- Status: auto-route emerald `#34C77B`, review amber `#E5A13D`,
  abstain violet `#9B7EDE`, duplicate/error `#E5484D`
- Contrast: body ≈13:1, muted ≈7:1 (≥4.5 ✓)

## Layout concept

"Triage desk": KPI strip on top, submit desk left, human queue right.
Submitting a ticket animates the confidence bar and either routes it
(toast + KPI tick) or parks it in the queue with Approve/Override inline.

```text
+--------------------------------------------------------------+
| ◈ Ticket Triage AI          lexical backend · keyless         |
| [TOTAL 3] [REVIEW 33%] [AUTO 67%] [LAST 5.0ms]               |
+------------------------------+-------------------------------+
| SUBMIT DESK                  |  HUMAN REVIEW QUEUE (1)       |
| title/body/customer          |  ┌ hmm · general_inquiry     |
| [Triage] samples             |  │ conf ▓▓ 0.30 · LOW_CONF    |
| verdict card (animated bar)  |  │ [Approve] [Override ▾]     |
+------------------------------+-------------------------------+
```

## Bold element

The verdict card: oversized label in Sora, animated confidence bar, reason
chips (LOW_CONFIDENCE, HIGH_SEVERITY…), duplicate warning. It reads like a
boarding pass for the ticket — the artifact a reviewer actually wants.

## Motion

- Load stagger; KPI numbers tick up on change; conf bar grows 600ms ease-out
- Queue items slide in; approve/override collapse with fade; toasts bottom-right
- `prefers-reduced-motion`: instant states, no animation

## States

idle · triaging (button spinner) · routed · queued · duplicate flag ·
queue empty (honest empty state) · error. Mobile ≤900px single column.
