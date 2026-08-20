---
name: hermes-bridge
description: Use when talking to Hermes, driving the user's personal Hermes Agent CLI, or exchanging knowledge with it (asking it what it knows, teaching it something new) — including requests phrased as "ask Hermes", "tell Bean", "check in with my agent", or anything hermes-related
---

# Hermes Bridge

## Overview

`~/.claude/skills/hermes-bridge/scripts/hermes-bridge` is a tmux bridge that drives the user's local Hermes Agent CLI (`hermes chat --cli`) as a live, scriptable process — start it, send messages, poll for state, react to approval/secret/clarify prompts, stop it. It crash-resumes the same Hermes conversation automatically. Always invoke it by its absolute path.

## Quick Reference

| Subcommand | Purpose |
|---|---|
| `start [--fresh] [--session NAME] [--timeout N]` | Launch (or resume) Hermes in tmux |
| `send MESSAGE` | Type one single-line message + Enter |
| `send-file FILE` | Send file content as one message (multiline safe) |
| `wait` | Block until idle or an action-needed state |
| `peek [-n LINES]` | Print recent pane text, no state change |
| `state` | Print `idle\|busy\|approval\|secret\|clarify\|dead\|missing` |
| `session` | Print the saved underlying Hermes session id |
| `approve` | Select "Allow once" in an approval menu |
| `deny [REASON]` | Select "Deny"; REASON is logged to stderr only |
| `stop` | Kill the tmux session |
| `log [-n N]` | Tail `~/.hermes/logs/agent.log` |

`--session NAME` and `--timeout N` are accepted by every subcommand except `log` (which only takes `-n` and always tails the fixed agent.log, ignoring `--session`) — but `SESSION` resets to the default (`hermes-bridge`) on each separate invocation of the script. If you `start --session foo`, every later call (`send`, `wait`, `state`, `stop`, ...) MUST repeat `--session foo`, or it silently targets the default session instead of yours. `approve`/`deny` parse `--timeout` without erroring but ignore it — they always wait on the fixed internal default, not your value.

Exit codes: `0` ok, `1` generic error, `2` session missing, `3` approval, `4` secret, `5` clarify, `6` timeout, `7` dead, `8` busy (`send`/`send-file` only — refused rather than silently interrupting in-flight work). Two exceptions: `state` always exits `0` — read its printed word, not the exit code; `stop` on an already-missing session also exits `0` (nothing to stop is not an error).

## Workflow

1. `start` (add `--fresh` only if the user wants a brand-new conversation, not a resume).
2. Always check `state` before `send` — don't send into approval/secret/clarify.
3. Loop: `send` (or `send-file` for multiline) → `wait` → act on the resulting state → repeat.
4. `stop` at the end of the conversation, unless the user wants the session left running.

Multiline messages MUST go through `send-file` — `send` rejects embedded newlines by design (Hermes's live REPL submits on Enter/LF; only bracketed paste, which `send-file` uses, inserts literal newlines).

## Session Lifecycle — Claude decides (standing authority from the user, 2026-08-20)

Claude owns the life and death of Hermes sessions on this machine; do not ask permission for lifecycle operations — decide, act, and mention what you did in the reply:

- **Bridge sessions**: start/resume/`--fresh`/stop are your calls. Default: `stop` at conversation end; leave running only when ongoing work benefits. Hermes conversations are SQLite-persisted, so `stop` loses nothing — `start` resumes the same conversation.
- **Stale/outdated Hermes processes** (e.g. long-lived `hermes --tui`/CLI sessions still running pre-upgrade code, zombie processes, sessions wedging the Ladybug DB lock): kill them (`kill PID`, then `-9` if ignored). Their conversations remain resumable (`hermes --continue <name>` / `hermes sessions list`), so the cost is only in-flight turn state. Always say in the reply which PIDs you killed and why.
- **Gateway**: restart with `hermes gateway restart` (the sanctioned command — never launchctl bootout/bootstrap). Restart it after venv/plugin upgrades or config changes so it runs current code. Note in the reply that Telegram goes quiet for the duration.
- **The one lifecycle exception**: a session that is mid-approval (⚠) — resolve or surface the approval first; never kill a session as a way to dodge an approval decision.

This authority covers lifecycle only. It does NOT extend to approving Hermes's dangerous-command prompts (see States table), modifying Hermes config, or sending to external platforms.

## States and Required Handling

| State | Meaning | Required handling |
|---|---|---|
| `idle` | Ready for input | safe to `send` |
| `busy` | Agent/tool running | `wait` |
| `approval` (⚠) | Dangerous-command menu open | **surface to the human user in chat; only run `approve` after they say yes.** Never approve on your own initiative. |
| `secret` (🔐/🔑) | Credential/secret prompt open | **surface to the human user; do not type a secret into the pane yourself** |
| `clarify` (?/✎) | Hermes asked a clarifying question | you may answer directly via `send` if you already know the answer from context |
| `dead` | tmux session present, Hermes process gone | don't retry sends; check `log`, then `start` again |
| `missing` | No tmux session (or crash destroyed it) | `start` (auto-resumes prior conversation unless `--fresh`) |

Safety, non-negotiable: never pass `--yolo` or `--tui` to Hermes (this script never does either). Never run `approve` unless the human user has just approved it in chat. Never use this bridge to relay instructions that make Hermes message an external platform (Telegram/Discord/Slack/etc.) on the user's behalf unless the user explicitly asked for that.

## Knowledge-Exchange Recipes

**Learn about the user (read-only, ground truth, no session needed):** read `~/.hermes/memories/USER.md` and `~/.hermes/memories/MEMORY.md` directly, or `~/.hermes/SOUL.md` for persona/behavior rules. Faster than asking Hermes and always current on disk.

**Ask Hermes directly:** `start` → `send "..."` → `wait` → `peek`. Simplest when the answer requires Hermes's own reasoning, not just its memory files.

**Teach Hermes something:** `send-file` a message asking it to remember, or drive `/learn` in-session to capture a reusable skill. Memory writes may be approval-gated (`⚠`) — handle per the approval row above. Memory is a **frozen snapshot taken at session start**: a fact taught mid-session won't be reflected in that same session's behavior. To verify it landed, `stop` and `start` a fresh session (or `start --fresh` for a wholly new conversation) and probe again.

## Slash Commands Worth Knowing

`/help /learn /memory /journey /init /steer /queue /approve /deny` — typed via `send` like any message once `state` is idle. (`/quit` is not listed: the script itself only ever sends `/exit`, and `/quit` was never independently confirmed — if you need to exit the CLI's own session from inside a message, use `/exit`.)

## Gotchas

- **NO_REPLY persona rule**: Hermes's "Raw Means Raw" behavior means a short or empty reply can be intentional, not a bridge failure — don't treat it as an error by default.
- **Paste-collapse**: very large `send-file` payloads get auto-collapsed by Hermes into a temp-file reference in its UI; this is normal Hermes behavior.
- **Crash usually surfaces as `missing`/exit 2, not `dead`/exit 7**: a resume/respawn launch runs Hermes as the pane's own direct-argv process, so a crash destroys the tmux session itself — use `log` for post-mortem diagnostics, not `peek`. Exception: the very first-ever `start` (no saved session id yet) types `hermes chat ...` into a live shell instead, so if Hermes crashes there the shell survives and you'll see `dead`/exit 7 instead; same remediation (`log`, then `start` again).
- **A malformed saved session id self-heals, it does not error**: `start` warns on stderr and silently proceeds as a normal fresh launch — it does NOT fail. `--fresh` is for deliberately abandoning a valid saved conversation and starting a new one on purpose, not an error-recovery step.
- **A stale-but-correctly-formatted saved session id does NOT self-heal.** Unlike a malformed one, a validly-formatted id that Hermes itself no longer recognizes (e.g. pruned from its own session store) makes `start` retry `--resume <that id>` every single time, fail to reach idle the same way every time, and exit `2` every time. If `start` keeps exiting `2` with a saved id in play, don't keep retrying plain `start` — run `start --fresh` instead.
- **Foreign `hermes-bridge` tmux session**: every subcommand refuses to touch a session named `hermes-bridge` that this script didn't create (ownership marker). Under the lifecycle authority above you may `tmux kill-session -t hermes-bridge` yourself — peek at its content first (`tmux capture-pane -p -t hermes-bridge | tail`) to confirm it's a stale Hermes leftover and not something unrelated the user reused the name for; say what you found and did in the reply.
- **Glyph detection is version-pinned to Hermes v0.20.0.** After the user runs `hermes update`, re-verify with a manual `start` + `peek` before trusting `state` again.
- Alternative non-tmux path for one-shot exchanges that don't need live approval handling: `hermes -z "..." --resume <id>` (get `<id>` from this bridge's `session` subcommand).
