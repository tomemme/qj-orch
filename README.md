# qj-orch

Orchestration tools for managing AI-assisted coding sessions with multiple agents
(Claude, Codex) using git worktrees and [herdr](https://github.com/omacom-io/herdr).

Each project gets its own **herdr workspace**; Claude and Codex run in isolated git
worktrees as herdr-tracked agents (lifecycle states: idle / working / blocked / done).

## Requirements

- [`herdr`](https://github.com/omacom-io/herdr) — terminal workspace manager
- `jq`, `git`, `nvim`
- `claude` and `codex` on `PATH` (for the agent panes)
- For repository recon: QEMU/KVM, libvirt, `virt-install`, `dnsmasq`, UEFI
  firmware, and `virt-viewer` (see [recon setup](docs/recon.md))

tmux is no longer used.

## Setup

Add `bin` to your `PATH` (and optionally point the folders wherever you like):

```bash
export QJ_ORCH_DIR="$HOME/qj-orch"            # this checkout (templates + notebook.md)
export QJ_PROJECTS_DIR="$HOME/ai-projects"    # project repos
export QJ_WORK_DIR="$HOME/ai-work"            # git worktrees
export PATH="$QJ_ORCH_DIR/bin:$PATH"
```

All three default to `$HOME/<name>` if unset.

Install the herdr agent integrations once (**required** — without them herdr's
detection of a freshly launched Claude/Codex is unreliable and `qj-agent` will
report agents as "not ready"):

```bash
herdr integration install claude
herdr integration install codex
```

A herdr server must be running before `qj-agent` / `qj-clean` — start one with
`herdr`, or run `qj-desk` (it launches herdr if nothing is up).

## Commands

### qj-desk

Opens `notebook.md` (ideas, decisions, follow-ups, active maps) in a `qj-desk`
herdr workspace. If no herdr server is running, it starts one and preserves a
pending recon request while the server comes up.

```bash
qj-desk
```

### Repository recon (VM-backed)

```bash
qj-vm setup --iso <omarchy.iso>     # Create the dedicated Omarchy VM
qj-vm login claude                   # Authenticate inside the guest (or codex)
qj-desk recon owner/repo             # Open desk, then choose Claude or Codex
qj-desk resume <review-id>           # Retry with the same agent and saved evidence
```

Repositories are collected inside an Omarchy VM and reviewed as bounded static
evidence. The host receives a report linked from the notebook. No project
installation or execution is part of recon. The first setup requires installing
Omarchy on the VM's new 40 GiB virtual disk, running the guest bootstrap, and
authenticating the selected agent inside the guest. Complete live isolation
verification before first untrusted use.

The VM has no host-folder sharing, clipboard integration, SSH-agent forwarding,
physical-disk passthrough, or Docker socket access. Recon pins a public GitHub
commit, supplies bounded source evidence to the selected agent, and records
skipped coverage. It does not claim runtime safety or run the target project.

See [setup, boundaries, and lifecycle](docs/recon.md), the
[QJ persona](persona/qj.md), and [optional PC-specs template](persona/pc-specs.example.md).

### qj-agent

Spin up AI coding sessions.

```bash
# Plan a loose idea (Claude wayfinding session, no worktrees)
qj-agent plan my-app build a task manager with collaboration

# Start implementation with a clear mission (Claude + Codex worktrees, mission dispatched)
qj-agent start my-app implement JWT auth

# Launch the agents but don't send them the mission yet
qj-agent start my-app --no-dispatch overhaul the parser

# Clone from a remote first
qj-agent start my-app --from git@github.com:user/app.git fix the API
```

By default `start` launches Claude + Codex **and hands them the mission
immediately** (`plan` launches one Claude and sends `/wayfinder <idea>`). Since
qj-agent creates the worktree and writes `QJ_TASK.md` itself, it also marks that
folder trusted so the agents skip their "trust this folder?" dialog — Claude via
`~/.claude.json`, Codex via a `[projects]` entry in `~/.codex/config.toml`. Codex
also starts with `--sandbox workspace-write`. **Per-command approval prompts are
unaffected** — the agents still ask before running shell commands, hitting the
network, etc.

Flags:

| Flag | Effect |
|------|--------|
| `--no-dispatch` | Launch the agents but leave them idle (don't send the mission) |
| `--no-agents`   | Open panes at the worktrees but don't launch Claude/Codex |
| `--safe`        | Don't pre-trust the folder or relax Codex's sandbox; agents get their normal first-run prompts |
| `--from <url>`  | Clone the project from a remote first |
| `--map <url>`   | Link a wayfinder map into `QJ_TASK.md` (`start` only) |

`plan` creates workspace `qj-plan-<project>`; `start` creates workspace
`qj-<project>` with a merge pane plus Claude and Codex worktree panes. Running
`start` again for an existing workspace just focuses it.

### qj-clean

Remove worktrees and branches when done, and close the herdr workspaces.

```bash
qj-clean my-app
```

## How It Works

- Each project → one herdr workspace (`qj-<project>` / `qj-plan-<project>`).
- Claude and Codex work in isolated `git worktree` checkouts on
  `qj/claude-<project>` and `qj/codex-<project>` branches; your main branch stays clean.
- `QJ_TASK.md` is rendered into each worktree from `templates/QJ_TASK.md` with the
  mission, project name, and map URL filled in.
- Agents are started as herdr-tracked agents, so `herdr agent list`, `herdr agent
  wait`, and blocked/idle notifications work.
- `qj-clean` removes the worktrees and branches and closes the `qj-<project>` /
  `qj-plan-<project>` workspaces. The pre-trust entries it wrote to
  `~/.claude.json` / `~/.codex/config.toml` are left in place.
