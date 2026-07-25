# Communication Policy

Referenced by `AGENTS.md` (Final Response, Owner Gates).

## Register

Short. The owner reads for decisions, not for narrative.

- **One line per action.** Every pending action gets exactly one line, phrased
  as a go/no-go the owner can answer with one word.
- **Never bury an action in prose.** A decision the owner must make is never
  embedded in a paragraph explaining background. If it needs a decision, it is
  its own line in the action list.
- **Detail on request, not by default.** Do not pre-emptively explain design
  reasoning, red-proof mechanics, or what was deliberately not changed. That
  belongs in the commit message and the finding record, which are durable and
  searchable. Summarize in one line; expand only if asked.
- **Lead with the bottom line**, per `AGENTS.md`. One or two lines of outcome,
  then the action list. Nothing between them.
- Report failures and skipped work plainly and immediately — brevity never
  means omitting a bad result.

## Provenance

Owner feedback, 2026-07-25: a response was "too long", it "buries several
potential actions in a wall of text", and the owner asked for "simple, one-line
per action, go/no-go decisions".
