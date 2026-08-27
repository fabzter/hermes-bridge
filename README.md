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
scripts/hermes-bridge start --session hermes-cv            # launch (or crash-resume) Hermes in tmux
scripts/hermes-bridge send --session hermes-cv "hello"      # one message -> prints Hermes's reply
scripts/hermes-bridge send-file --session hermes-cv msg.md  # multiline (bracketed paste)
scripts/hermes-bridge state --session hermes-cv             # idle|busy|approval|secret|clarify|dead|missing
scripts/hermes-bridge approve|deny --session hermes-cv      # act on a dangerous-command menu (human-gated)
scripts/hermes-bridge stop --session hermes-cv              # graceful /exit + kill session
```

`--session NAME` is mandatory on every subcommand above (letters/digits/`.`/`_`/`-`, 1-64 chars) — there's no default, so concurrent bridge users on the same machine never silently collide on one shared tmux session/Hermes conversation. Pick one stable name per purpose and reuse it for every call. `log` is the one exception (no session, tails a fixed shared log file).

Distinct exit codes per state (3 approval, 4 secret, 5 clarify, 6 timeout, 8 busy…) make it scriptable; see `SKILL.md` for the full contract.

## Design notes

- **Crash-resume**: the Hermes session id is captured (format-validated) and persisted; any relaunch `--resume`s the same conversation.
- **Fail-closed safety**: approval menus are navigated with cursor-verified, label-checked keystrokes; `approve` always picks least-privilege "Allow once"; nothing is ever auto-approved, and `--yolo` is never used.
- **Session hygiene**: bridge sessions are ownership-marked (foreign same-name sessions are refused) and use `--source tool` to stay out of the user's session history.
- **Robust I/O**: response extraction is anchor-based with chrome stripping; multiline input uses tmux bracketed paste (Hermes's REPL submits on any bare newline).

## Caveats

- Prompt-glyph detection is pinned to Hermes Agent **v0.20.0** — after `hermes update`, re-verify with `start` + `peek` before trusting `state`.
- macOS/Linux (bash 3.2 compatible). Single-machine, single-user tool; paths assume `~/.hermes`.

## The other direction: Hermes → Claude Code

`hermes-side/` holds the mirror bridge, which lets Hermes (Bean) hold a conversation with Claude Code:

```bash
claude-bridge ask "what changed in the CV?"     # continuing conversation, not one-shot
claude-bridge ask-file long-context.md          # multiline / large context
claude-bridge session | reset | list            # inspect or restart the conversation
```

It drives `claude -p` with `--session-id`/`--resume` so follow-ups keep context, and it is
**read-only by design**: allowed tools are `Read Grep Glob WebSearch WebFetch`, so Claude can
look things up and reason but cannot write, edit, or run shell commands on Hermes's behalf —
anything else is denied automatically (headless has no human to approve it).

Deployed location (what Hermes actually loads): `~/.hermes/skills/claude-bridge/`.
`hermes-side/` here is the versioned copy — after changing one, copy to the other.
