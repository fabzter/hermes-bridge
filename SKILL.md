---
name: hermes-bridge
description: Use when talking to Hermes, driving the user's personal Hermes Agent CLI, or exchanging knowledge with it (asking it what it knows, teaching it something new) — including requests phrased as "ask Hermes", "tell Bean", "check in with my agent", or anything hermes-related
---

# Hermes Bridge

## Overview

`~/.claude/skills/hermes-bridge/scripts/hermes-bridge` drives the user's local Hermes Agent CLI (`hermes chat --cli --source tool`) as a live, scriptable process, inside a pane of the named herdr session `agents` — start it, send messages, poll for state, react to approval/secret/clarify prompts, stop it. Always invoke it by its absolute path.

Requires herdr ≥ 0.8.2 and python3. The bridge starts the `agents` herdr server itself if it isn't already running — no separate setup step.

## Quick Reference

| Subcommand | Purpose |
|---|---|
| `start [NAME] [--fresh] [--timeout N] [--yolo]` | Launch or resume Hermes in a pane of herdr session `agents` (default timeout 120s; first start on a brand-new pane can take up to ~2 min while the bridge waits for the shell to settle); `--fresh` on a session that's currently running is refused — `stop NAME` first |
| `send [NAME] TEXT` | Send one message (multiline safe) and print Hermes's reply (default timeout 600s) |
| `state [NAME]` | Print `idle\|busy\|approval\|secret\|clarify\|blocked\|unknown\|dead\|missing`; exits 0 for whatever it prints, except 2 on a bad NAME, 1 if NAME is ambiguous (multiple live agents), 9 if the herdr server can't be reached |
| `wait [NAME] [--timeout N]` | Block until Hermes settles, then print the state; falls back to polling if the herdr socket drops |
| `peek [NAME] [-n LINES]` | Print recent pane text, no state change (default 80 lines) |
| `approve [NAME]` | Select "Allow once" in an approval menu — only after the human has said yes |
| `deny [NAME] [REASON]` | Select "Deny"; REASON is logged to stderr only |
| `answer [NAME] TEXT` | Answer a clarification prompt; waits up to 5 s for the prompt to clear |
| `session [NAME]` | Print the Hermes session id (exit 1 with a message until the first turn completes — send one message first) |
| `stop [NAME]` | Send `/exit` and close the tab; conversation stays resumable; exits 0 even with nothing to stop |
| `forget [NAME]` | Delete the stored record for NAME (pane, tab, session id and launch flags; next `start` begins a brand-new conversation); refused with exit 1 while NAME is running — `stop NAME` first |
| `list` | List bridge sessions: name, pane, state, session id, launch flags (`--yolo` or `-`) |
| `gc` | Close tabs whose Hermes process has already exited |
| `log [-n N]` | Tail `~/.hermes/logs/agent.log` (default 40 lines; no NAME — one shared log) |

For multiline text use `send NAME -f FILE` or pipe stdin with `send NAME -` — multiline is now just an argument to `send`, not a separate subcommand.

## Argument order

`hermes-bridge <cmd> NAME [TEXT] [--options]` — options go *after* the positionals, not between them: `send bean --timeout 900 "hi"` fails, `send bean "hi" --timeout 900` works, `send bean -f FILE --timeout 900` works (no TEXT positional to collide with). `--session NAME` is a deprecated alias for the NAME positional and cannot be combined with a NAME positional in the same call.

## Naming

NAME is the herdr agent name: `^[a-z][a-z0-9_-]{0,31}$` (lowercase start, then lowercase/digits/`_`/`-`, ≤32 chars). Pick **one stable name per purpose** and reuse it for every call in that conversation/task — e.g. `cv`, `sync-prep`, `standup-2026-09-01`. Names with dots or uppercase letters (`Hermes.Main`, `hermes.cv`, `Bean_1`) no longer validate — pick a conforming name instead. Existing hyphenated/lowercase names such as `hermes-cv`, `hermes-sync-prep`, `standup-2026-08-21` already conform and remain valid — no renaming needed. They migrate automatically on first use: their `.session-id` files become `.json` and are renamed `.session-id.migrated`.

## Exit Codes

`0` ok, `1` generic error, `2` missing (no tab/agent found for NAME), `3` approval (also the exit for the generic `blocked` state), `4` secret, `5` clarify, `6` timeout, `7` dead (also the exit for `unknown`), `8` busy — refused rather than silently interrupting in-flight work; not `send`-only, `start`/`wait`/`answer` can exit `8` too, `9` server (herdr server unreachable). Exceptions: `state` exits `0` for whatever state it prints — read the printed word, not the exit code — except `2` on an invalid NAME, `1` if NAME matches multiple live agents (ambiguous), and `9` when the herdr server can't be reached; `stop` on an already-missing session also exits `0`.

## Workflow

1. `start NAME` (add `--fresh` only if the user wants a brand-new conversation, not a resume; refused with exit 1 if NAME is currently running — `stop NAME` first).
2. Always check `state NAME` before `send NAME ...` — don't send into approval/secret/clarify. herdr's own `agent prompt` also refuses to type into a blocked agent, so `send` never interrupts an in-flight approval.
3. Loop: `send NAME MESSAGE` (or `send NAME -f FILE` for multiline) → act on the resulting state → repeat.
4. `stop NAME` at the end of the conversation, unless the user wants the session left running.

## States and Required Handling

| State | Meaning | Required handling |
|---|---|---|
| `idle` | Ready for input (herdr's `idle` and `done` agent statuses both map here) | safe to `send` |
| `busy` | Agent/tool running | `wait` |
| `approval` | Dangerous-command menu open | **surface to the human in chat; only run `approve` after they say yes.** Never approve on your own initiative. |
| `secret` | Credential/secret prompt open | **surface to the human; never type the secret into the pane yourself** |
| `clarify` | Hermes asked a clarifying question | answer with `answer NAME TEXT` if you already know the answer from context — `send` refuses in this state |
| `blocked` | A menu/prompt is open but herdr's rule set didn't classify it as approval/secret/clarify | `peek`, then surface the dialog to the human |
| `unknown` | herdr couldn't classify the agent's status at all | don't retry blindly — `peek`/`log`, then treat like `dead` |
| `dead` | Tab/pane present, Hermes process gone (crash) | don't retry sends; `dead` after a turn (Ladybug crash) → `start NAME` resumes the same conversation; `--fresh` only when the user wants a new one |
| `missing` | No tab/agent found for NAME | `start NAME` (auto-resumes the prior conversation unless `--fresh`) |

State comes from herdr's own screen classification plus `agent explain NAME --json` (`matched_rule` sits at the JSON's top level), not from matching literal prompt symbols pinned to a Hermes version — a `hermes update` no longer requires re-verifying anything here.

## Session Lifecycle — Claude decides (standing authority from the user, 2026-08-20)

Claude owns the life and death of Hermes sessions on this machine; do not ask permission for lifecycle operations — decide, act, and mention what you did in the reply:

- **Bridge sessions**: start/resume/`--fresh`/stop are your calls. Default: `stop` at conversation end; leave running only when ongoing work benefits. Hermes conversations are persisted, so `stop` loses nothing — `start` resumes the same conversation.
- **Stale panes**: clean them with `gc` (closes tabs whose Hermes process has already exited). Foreign same-name agents cannot occur — herdr enforces unique agent names within the `agents` session, so `start NAME` never collides with something else already using that name.
- **Stale/outdated Hermes processes** (e.g. long-lived sessions still running pre-upgrade code, zombie processes, sessions wedging the Ladybug DB lock): kill them (`kill PID`, then `-9` if ignored). Their conversations remain resumable, so the cost is only in-flight turn state. Always say in the reply which PIDs you killed and why.
- **Gateway**: restart with `hermes gateway restart` (the sanctioned command — never launchctl bootout/bootstrap). Restart it after venv/plugin upgrades or config changes so it runs current code. Note in the reply that Telegram goes quiet for the duration.
- **The one lifecycle exception**: a session that is mid-approval — resolve or surface the approval first; never stop/kill a session as a way to dodge an approval decision.

This authority covers lifecycle only. It does NOT extend to approving Hermes's dangerous-command prompts (see States table), modifying Hermes config, or sending to external platforms.

## herdr Specifics You Must Know

- **Session id timing**: the Hermes session id only exists after Hermes's first LLM call, so `session NAME` right after `start` may report none known yet — send one message first.
- **Server restarts don't duplicate agents**: after a herdr server restart, herdr relaunches `hermes --resume <id>` on its own and keeps the same name; `start NAME` finds it rather than creating a second one.
- **Known host issue — Hermes segfaults after a turn**: a native crash in the LadybugDB memory provider (`_lbug`) has been observed right after Hermes completes a turn, both in resumed sessions and on the second turn of otherwise-fresh sessions. The bridge reports `dead`. Remedy: `start NAME` again (the conversation resumes from the saved session id). If it keeps dying, tell the user this is a Hermes/Ladybug problem, not something to work around — never pass `--yolo`, never modify Hermes's own config.
- **Fresh-start race**: a brand-new pane's shell can still be mid-startup (e.g. `pyenv rehash` contention) when herdr would otherwise report `agent_pane_busy`. The bridge now waits for the shell to settle (up to `shell_settle_s`, default 70s) and retries `agent_pane_busy` itself before giving up — no manual retry needed. First `start` on a brand-new pane can take up to ~2 minutes as a result; a `start NAME` on an existing/resumed pane is fast as before.
- **Approval menu unreadable**: `approve`/`deny` refuse with "approval menu not recognized" when herdr's screen parser can't read the current menu render. When that happens, `peek` the dialog and surface it to the human — never press keys manually to approve or deny on their behalf.
- **Human visibility**: the human can watch live with `herdr session attach agents` or `HERDR_SESSION=agents herdr agent attach NAME`.

## Knowledge-Exchange Recipes

**Learn about the user (read-only, ground truth, no session needed):** read `~/.hermes/memories/USER.md` and `~/.hermes/memories/MEMORY.md` directly, or `~/.hermes/SOUL.md` for persona/behavior rules. Faster than asking Hermes and always current on disk.

**Ask Hermes directly:** `start NAME` → `send NAME "..."` → check the printed state → `peek NAME` if you need more than the extracted reply. Simplest when the answer requires Hermes's own reasoning, not just its memory files.

**Teach Hermes something:** `send NAME -f FILE` a message asking it to remember, or drive `/learn` in-session to capture a reusable skill. Memory writes may be approval-gated — handle per the approval row above. Memory is a **frozen snapshot taken at session start**: a fact taught mid-session won't be reflected in that same session's behavior. To verify it landed, `stop NAME` then `start NAME --fresh` for a wholly new conversation and probe again — `--fresh` on a still-running session is refused (`stop` it first).

## Safety

Never pass `--yolo` on your own initiative; use it only when the user explicitly asked for a yolo/autonomous Hermes session for this conversation, and say so in your reply; yolo sessions never produce `approval` states, so `approve`/`deny` do not apply. Never pass `--tui` to Hermes (this bridge never does). Never run `approve` unless the human user has just approved it in chat. Never use this bridge to relay instructions that make Hermes message an external platform (Telegram/Discord/Slack/etc.) on the user's behalf unless the user explicitly asked for that. Never `herdr session stop agents` as a way to dodge an approval decision.

## Gotchas

- **NO_REPLY persona rule**: Hermes's "Raw Means Raw" behavior means a short or empty reply can be intentional, not a bridge failure — don't treat it as an error by default.
- **`send` exits with the state code, not a delivery flag**: if the agent was blocked before the message could even be typed, the printed reply is empty and the dialog text is prefixed `MESSAGE NOT DELIVERED` — never assume a message landed just because `send` returned an approval/secret/clarify state; check for that prefix.
- **Paste-collapse**: very large `send -f` payloads get auto-collapsed by Hermes into a temp-file reference in its UI; this is normal Hermes behavior.
- **Truncated replies**: reply extraction falls back to the raw pane tail and warns on stderr when the expected echo line isn't found. If a reply looks cut off, `peek NAME -n 200` for the full text.
