# hermes-bridge

A Python bridge that lets [Claude Code](https://claude.com/claude-code) drive the user's local [Hermes Agent](https://github.com/NousResearch) CLI as a live, scriptable peer over [herdr](https://github.com/fabzter/herdr) — send it messages and slash commands, read its replies reliably, and react to its approval prompts, so the two agents can exchange knowledge and collaborate.

Claude Code is the agent that *uses* this bridge to reach Hermes; it does not run inside it.

## What's inside

| File | Purpose |
|---|---|
| `scripts/hermes-bridge` | Thin launcher — resolves `sys.path` and calls into `hermes_bridge_cli.main()` |
| `scripts/hermes_bridge_cli.py` | The CLI: argument parsing, subcommands, exit-code mapping |
| `scripts/herdrbridge.py` | Vendored copy of the shared `herdrbridge` library (state store, herdr socket/CLI client, reply extraction, menu navigation) |
| `SKILL.md` | Claude Code skill that teaches any session how to use the bridge safely |
| `tools/sync-lib.sh` | Re-vendors `herdrbridge.py` (+ test fakes/fixtures) from the canonical library repo at a pinned ref |
| `tests/` | Unit tests (fakes, no live herdr/Hermes needed) |
| `tests/live/e2e_hermes.sh` | End-to-end check against a real herdr server and real Hermes, in a throwaway named session |

## Requirements

- [herdr](https://github.com/fabzter/herdr) ≥ 0.8.2, with the Hermes integration installed: `herdr integration install hermes`
- Hermes Agent CLI installed and working (`hermes chat --cli`)
- python3 (stdlib only — no pip install)

## Usage

```bash
scripts/hermes-bridge start cv                    # launch (or resume) Hermes in herdr session "agents"
scripts/hermes-bridge send cv "hello"              # one message -> prints Hermes's reply
scripts/hermes-bridge send cv -f msg.md            # multiline, from a file
scripts/hermes-bridge state cv                     # idle|busy|approval|secret|clarify|blocked|unknown|dead|missing
scripts/hermes-bridge approve cv                   # act on a dangerous-command menu (human-gated)
scripts/hermes-bridge deny cv "not needed"
scripts/hermes-bridge stop cv                      # /exit + close the tab (conversation stays resumable)
scripts/hermes-bridge list                         # every bridge session: name, pane, state, session id
```

NAME is a herdr agent name (`^[a-z][a-z0-9_-]{0,31}$`) — pick one stable name per purpose and reuse it for every call in that conversation/task. `log` is the one subcommand that takes no NAME (it tails a single shared log file). Distinct exit codes per state (3 approval, 4 secret, 5 clarify, 6 timeout, 7 dead, 8 busy, 9 server unreachable…) make it scriptable; `state` always exits 0 regardless of what it prints. See `SKILL.md` for the full contract, including the states table and known host issues.

## How herdr is used

The bridge doesn't manage terminals or panes directly — herdr does, and the bridge is a thin client over herdr's CLI/socket API:

- **One named herdr session, `agents`**, holds every bridge conversation as its own tab/pane; the bridge starts that server itself if it isn't already running.
- Sending a message is a single atomic call: `agent prompt NAME TEXT --wait`, which honors bracketed paste (multiline safe), refuses to type into a blocked agent, and waits server-side for the settled state — no polling loop needed on our end.
- State detection comes from herdr's own screen classification plus `agent explain NAME --json`, which names the matched rule (dangerous-command approval, credential prompt, clarification prompt, etc.) instead of the bridge doing its own prompt-symbol matching.
- Session identity is native: the Hermes integration reports the underlying Hermes session id to herdr, exposed via `agent get`. After a herdr server restart, herdr relaunches `hermes --resume <id>` on its own and keeps the same agent name, so `start` finds the existing agent instead of creating a duplicate.

## Design notes

- **Fail-closed approvals**: `approve` always picks least-privilege "Allow once"; nothing is ever auto-approved, and `--yolo` is never used.
- **No auto-approve, ever**: approval and secret prompts are always surfaced to the human first; the bridge itself never decides to proceed past one.
- **Session ids come from herdr**, not from scraping pane text — see "How herdr is used" above.
- **Stdlib only**: `hermes_bridge_cli.py` and `herdrbridge.py` use only the Python 3 standard library (`subprocess`, `socket`, `json`, `argparse`, `re`) — no dependencies to install.

## Testing

```bash
python3 -m unittest discover -s tests -v
```

Runs entirely against fakes — no herdr server or live Hermes process required.

For a real end-to-end check against actual herdr + Hermes, in a throwaway named session that cleans up after itself:

```bash
tests/live/e2e_hermes.sh
```

See `tests/live/README.md` for what it exercises and expects.

## The vendored library

The state store, herdr client, reply-extraction, and menu-navigation logic live in [`fabzter/herdrbridge`](https://github.com/fabzter/herdrbridge), a shared library used by both directions of this bridge pair. This repo vendors a pinned copy at `scripts/herdrbridge.py` (pin recorded in `scripts/herdrbridge.version`). To pull in a newer pinned commit:

```bash
tools/sync-lib.sh [REF]   # REF defaults to the currently pinned commit, else main
```

Change the library in its own repo first, then re-vendor here — don't hand-edit `scripts/herdrbridge.py` directly.

## The other direction: Hermes → Claude Code

The mirror bridge — letting Hermes hold a continuing, read-only conversation with Claude Code — lives in its own repo and installs through Hermes's own skill manager:

```bash
hermes skills install fabzter/hermes-claude-bridge/claude-bridge --yes
```

See [fabzter/hermes-claude-bridge](https://github.com/fabzter/hermes-claude-bridge).

## Migration from the tmux version

- **Names changed shape**: NAME is now a herdr agent name, `^[a-z][a-z0-9_-]{0,31}$` (lowercase, digits, `_`, `-`, ≤32 chars). Old names with dots or uppercase (`hermes-cv`) no longer validate — pick a new conforming name (`hermes-cv` → `cv`).
- **`send-file` is gone**: use `send NAME -f FILE` or pipe stdin with `send NAME -` for multiline messages.
- **`--session NAME` still works** as a deprecated alias for the positional NAME argument.
- **State storage moved**: per-session state now lives at `state/<name>.json` instead of the old flat `.session-id` files. Existing `<name>.session-id` files are picked up automatically the first time that name is used and migrated into the new format (renamed to `<name>.session-id.migrated` once done) — no manual migration step needed.
- **No more tmux**: the bridge no longer manages tmux sessions or scrapes prompt glyphs pinned to a specific Hermes version; herdr owns the pane and the state detection instead.

## Caveats

macOS/Linux. Single-machine, single-user tool; paths assume `~/.hermes`.
