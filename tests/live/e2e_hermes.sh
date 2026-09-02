#!/usr/bin/env bash
# tests/live/e2e_hermes.sh — end-to-end check against real herdr + Hermes in a throwaway named session.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
export HERDR_BRIDGE_SESSION="bridge-test-$$"
B="python3 $here/scripts/hermes-bridge"; [[ -x $here/scripts/hermes-bridge && ! -f $here/scripts/hermes-bridge.new ]] && B="$here/scripts/hermes-bridge"
cleanup() { HERDR_SESSION="$HERDR_BRIDGE_SESSION" herdr session stop "$HERDR_BRIDGE_SESSION" --json >/dev/null 2>&1 || true
            herdr session delete "$HERDR_BRIDGE_SESSION" --json >/dev/null 2>&1 || true; }
trap cleanup EXIT
echo "## start"; $B start e2e --fresh
echo "## state"; st=$($B state e2e); [[ $st == idle ]] || { echo "expected idle, got $st"; exit 1; }
echo "## send"; reply=$($B send e2e "Reply with exactly the word PONG and nothing else."); echo "reply=<$reply>"
[[ $reply == *PONG* ]] || { echo "reply did not contain PONG"; exit 1; }
echo "## session"; $B session e2e
echo "## multiline send"; printf 'Answer with one word: what colour is the sky on a clear day?\nSecond line is context only.\n' | $B send e2e -
echo "## approval"; set +e
$B send e2e "Run this exact shell command and show me its output: rm -rf /tmp/hermes-bridge-e2e-does-not-exist" >/tmp/e2e-approval.out 2>&1; rc=$?
set -e; cat /tmp/e2e-approval.out
if [[ $rc == 3 ]]; then echo "approval detected (exit 3)"; $B peek e2e -n 20; echo "## deny"; $B deny e2e "e2e test"; sleep 2; $B state e2e
else echo "NOTE: no approval prompt (rc=$rc) — Hermes may have auto-approved via smart mode; record this in the task notes"; fi
echo "## list"; $B list
echo "## capture fixture"; $B peek e2e -n 60 > /tmp/hermes_live_capture.txt
echo "## stop"; $B stop e2e; $B state e2e
echo "## gc"; $B gc
echo "ALL LIVE CHECKS PASSED"
