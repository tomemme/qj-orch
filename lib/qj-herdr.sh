#!/usr/bin/env bash
# qj-orch shared helpers for driving herdr (https://github.com/omacom-io/herdr).
#
# herdr is a persistent server/client terminal workspace manager. Its CLI
# subcommands talk to a running server over ~/.config/herdr/herdr.sock and
# return JSON wrapped under `.result`. qj-orch adds workspaces + tracked agents
# to an already-running session; it does not manage the server lifecycle
# (except qj-desk, which will launch herdr if nothing is running).
#
# Source this from bin/* via:
#   source "$(dirname "$(readlink -f "$0")")/../lib/qj-herdr.sh"

# --- paths (env-overridable, defaults match the upstream README) --------------
ORCH_DIR="${QJ_ORCH_DIR:-$HOME/qj-orch}"
PROJECTS_DIR="${QJ_PROJECTS_DIR:-$HOME/ai-projects}"
WORK_DIR="${QJ_WORK_DIR:-$HOME/ai-work}"
TEMPLATE="$ORCH_DIR/templates/QJ_TASK.md"
NOTEBOOK="$ORCH_DIR/notebook.md"

# --- output -----------------------------------------------------------------
die()  { printf 'qj: %s\n' "$*" >&2; exit 1; }
warn() { printf 'qj: %s\n' "$*" >&2; }

# --- prerequisites --------------------------------------------------------
# qj_need <cmd>...  -- assert each command is on PATH
qj_need() {
  local missing=()
  local c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
  done
  (( ${#missing[@]} == 0 )) || die "missing required command(s): ${missing[*]}"
}

# qj_herdr_up  -- true if a herdr server is reachable.
# Note: `herdr` exits 0 even when the server is down (it prints a JSON
# {"error":...} envelope to stdout), so check for a `result` key instead.
qj_herdr_up() {
  herdr workspace list 2>/dev/null | jq -e 'has("result")' >/dev/null 2>&1
}

# qj_require_herdr  -- hard requirement; used by qj-agent / qj-clean
qj_require_herdr() {
  qj_herdr_up || die "herdr server not running — start it with: herdr  (or run: qj-desk)"
}

# qj_warn_integrations <kind>...  -- warn if a herdr agent integration isn't
# installed. Without it herdr's detection of that agent on a fresh pane is
# unreliable and `herdr agent start` may report "blocked during startup".
qj_warn_integrations() {
  local status kind
  status=$(herdr integration status 2>/dev/null) || return 0
  for kind in "$@"; do
    if ! printf '%s\n' "$status" | grep -E "^${kind}:" | grep -qvE 'not installed|missing|outdated'; then
      warn "herdr $kind integration not installed — run: herdr integration install $kind"
    fi
  done
}

# --- workspace / pane helpers ------------------------------------------------
# qj_ws_id <label>  -- print the workspace_id for a label, or nothing
qj_ws_id() {
  herdr workspace list 2>/dev/null \
    | jq -r --arg l "$1" \
        'first((.result.workspaces // [])[] | select(.label == $l) | .workspace_id) // empty'
}

# qj_ws_create <label> <cwd>  -- create a workspace; print "<workspace_id> <root_pane_id>"
qj_ws_create() {
  local json
  json=$(herdr workspace create --label "$1" --cwd "$2" --no-focus) \
    || die "herdr workspace create failed for '$1'"
  printf '%s %s\n' \
    "$(printf '%s' "$json" | jq -r '.result.workspace.workspace_id')" \
    "$(printf '%s' "$json" | jq -r '.result.root_pane.pane_id')"
}

# qj_split <pane_id> <right|down> <cwd>  -- split; print the new pane_id
qj_split() {
  herdr pane split --pane "$1" --direction "$2" --cwd "$3" --no-focus \
    | jq -r '.result.pane.pane_id' \
    || die "herdr pane split failed"
}

# qj_run <pane_id> <command-string>  -- run a command in a pane (text + Enter)
qj_run() { herdr pane run "$1" "$2" >/dev/null; }

# qj_pane_shell_idle <pane_id>  -- true if only the shell is in the foreground
qj_pane_shell_idle() {
  herdr pane process-info --pane "$1" 2>/dev/null | jq -e '
    .result.process_info as $p
    | (($p.foreground_processes // []) | length) == 1
    and (($p.foreground_processes // [])[0].name | test("^(ba|z|fi)?sh$"))
    and ($p.shell_pid == $p.foreground_process_group_id)
  ' >/dev/null 2>&1
}

# qj_wait_pane_ready <pane_id>  -- block until the pane's shell has been idle at
# its prompt across three consecutive checks (~1.5s stable). A freshly split
# pane's shell reports idle before rc files finish loading; `herdr agent start`
# then fires keystrokes into a not-quite-ready shell and the agent fails to come
# up. ~10s cap.
qj_wait_pane_ready() {
  local pane="$1" i seen=0
  for (( i = 0; i < 20; i++ )); do
    if qj_pane_shell_idle "$pane"; then
      seen=$((seen + 1))
      [[ "$seen" -ge 3 ]] && return 0
    else
      seen=0
    fi
    sleep 0.5
  done
  return 1
}

# qj_agent_start <name> <kind> <pane_id> [agent-args...]  -- start a tracked agent.
# Waits for the pane shell to settle, then tries up to 3x (a fresh pane sometimes
# rejects the first attempt). If herdr registers the agent but it's parked on a
# first-run prompt, stop retrying and point the user at the pane.
qj_agent_start() {
  local name="$1" kind="$2" pane="$3"; shift 3
  # Remaining args ("$@") are passed to the agent binary after `--`.
  local try
  for try in 1 2 3; do
    qj_wait_pane_ready "$pane" \
      || warn "pane $pane shell slow to settle; starting $kind anyway"
    if herdr agent start "$name" --kind "$kind" --pane "$pane" --timeout 20000 \
         ${1:+--} "$@" >/dev/null 2>&1; then
      printf 'qj: agent %s (%s) ready\n' "$name" "$kind"
      return 0
    fi
    # If herdr registered the agent anyway (e.g. it's parked on a first-run
    # prompt), stop retrying -- a retry would just report agent_name_taken.
    if herdr agent list 2>/dev/null \
         | jq -e --arg n "$name" 'any((.result.agents // [])[]; .name == $n)' >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  local st
  st=$(herdr agent list 2>/dev/null \
        | jq -r --arg n "$name" \
            'first((.result.agents // [])[] | select(.name == $n) | .agent_status) // empty')
  warn "agent '$name' (${kind}) not ready — check its pane; it may be waiting on a first-run prompt${st:+ (status: $st)}"
}

# qj_dispatch <agent-name> <text>  -- submit a prompt to an agent (fire and forget;
# watch the agent work in its pane). Does not wait for the turn to finish.
qj_dispatch() {
  herdr agent prompt "$1" "$2" >/dev/null 2>&1 \
    || warn "could not send the mission to '$1' — paste it into the pane yourself"
}

# qj_trust_claude_dir <abs-path>...  -- mark each directory trusted in
# ~/.claude.json so Claude Code skips its "trust this folder?" dialog. Per-action
# permission prompts are unaffected. No-op if jq or the config file is missing.
qj_trust_claude_dir() {
  local cfg="$HOME/.claude.json" tmp dir
  command -v jq >/dev/null 2>&1 || return 0
  [[ -f "$cfg" ]] || return 0
  for dir in "$@"; do
    tmp=$(mktemp) || return 0
    if jq --arg p "$dir" '.projects[$p].hasTrustDialogAccepted = true' "$cfg" >"$tmp" 2>/dev/null \
       && [[ -s "$tmp" ]]; then
      cp "$tmp" "$cfg"        # cp (not mv) preserves the config's own perms
    fi
    rm -f "$tmp"
  done
}

# qj_trust_codex_repo <repo-root>  -- mark a repo trusted in ~/.codex/config.toml
# (Codex trusts by repository root, so pass the main worktree path, not a linked
# worktree). Idempotent. Only affects the trust dialog; approval policy / sandbox
# still apply.
qj_trust_codex_repo() {
  local repo="$1" cfg="$HOME/.codex/config.toml" header
  header="[projects.\"$repo\"]"
  mkdir -p "$(dirname "$cfg")"
  [[ -f "$cfg" ]] && grep -qF "$header" "$cfg" && return 0
  printf '\n%s\ntrust_level = "trusted"\n' "$header" >> "$cfg"
}

qj_ws_focus() { herdr workspace focus "$1" >/dev/null 2>&1 || true; }
qj_ws_close() { herdr workspace close "$1" >/dev/null 2>&1 || true; }

# qj_ensure_notebook  -- create $NOTEBOOK from the template if it doesn't exist
qj_ensure_notebook() {
  [[ -f "$NOTEBOOK" ]] && return
  mkdir -p "$ORCH_DIR"
  cat > "$NOTEBOOK" <<'EOF'
# QJ Desk Notebook

## Active Maps
<!-- Wayfinder maps in progress -->

## Active Sessions

## Ideas

## Decisions

## Follow-ups

## Done Today
EOF
}
