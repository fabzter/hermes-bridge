# Live e2e check

`e2e_hermes.sh` drives the real `herdr` daemon and a real Hermes Agent through the bridge CLI (start, send, session, approval/deny, list, peek, stop, gc) to confirm the bridge works end-to-end, not just against fakes.

It requires herdr >= 0.8.2 running on the host and a working `hermes` CLI on PATH.

It creates its own throwaway named herdr session (`bridge-test-$$`) and stops/deletes it on exit, so the `default` and `agents` sessions are never touched. Allow up to 10 minutes: Hermes startup and each turn take 20-60s.
