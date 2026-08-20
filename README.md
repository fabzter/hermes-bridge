# hermes-bridge

A tmux bridge that lets [Claude Code](https://claude.com/claude-code) drive a local [Hermes Agent](https://github.com/NousResearch) CLI as a live, scriptable peer — send it messages and slash commands, read its replies reliably, and react to its approval prompts, so the two agents can exchange knowledge and collaborate.

Built agent-to-agent: Claude Code wrote it (spec, implementation, adversarial reviews) to talk to the Hermes install on this machine, then both agents used it to co-author real work.

## What's inside

| File | Purpose |
|---|---|
| `scripts/hermes-bridge` | Self-contained bash CLI (tmux + coreutils only) that runs `hermes chat --cli` in a detached tmux session and exposes it as subcommands |
| `SKILL.md` | Claude Code skill that teaches any session how to use the bridge safely |

## Usage

```bash
scripts/hermes-bridge start            # launch (or crash-resume) Hermes in tmux
scripts/hermes-bridge send "hello"     # one message -> prints Hermes's reply
scripts/hermes-bridge send-file msg.md # multiline (bracketed paste)
scripts/hermes-bridge state            # idle|busy|approval|secret|clarify|dead|missing
scripts/hermes-bridge approve|deny     # act on a dangerous-command menu (human-gated)
scripts/hermes-bridge stop             # graceful /exit + kill session
```

Distinct exit codes per state (3 approval, 4 secret, 5 clarify, 6 timeout, 8 busy…) make it scriptable; see `SKILL.md` for the full contract.

## Design notes

- **Crash-resume**: the Hermes session id is captured (format-validated) and persisted; any relaunch `--resume`s the same conversation.
- **Fail-closed safety**: approval menus are navigated with cursor-verified, label-checked keystrokes; `approve` always picks least-privilege "Allow once"; nothing is ever auto-approved, and `--yolo` is never used.
- **Session hygiene**: bridge sessions are ownership-marked (foreign same-name sessions are refused) and use `--source tool` to stay out of the user's session history.
- **Robust I/O**: response extraction is anchor-based with chrome stripping; multiline input uses tmux bracketed paste (Hermes's REPL submits on any bare newline).

## Caveats

- Prompt-glyph detection is pinned to Hermes Agent **v0.20.0** — after `hermes update`, re-verify with `start` + `peek` before trusting `state`.
- macOS/Linux (bash 3.2 compatible). Single-machine, single-user tool; paths assume `~/.hermes`.
