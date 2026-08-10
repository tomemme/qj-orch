# qj-orch

Orchestration tools for managing AI-assisted coding sessions with multiple agents (Claude, Codex) using git worktrees and tmux.

## Setup

Add the `bin` directory to your PATH:

```bash
export PATH="$HOME/qj-orch/bin:$PATH"
```

## Commands

### qj-desk

Opens a tmux session for managing multiple projects. Creates a `notebook.md` file in `~/qj-orch` for tracking ideas, decisions, and follow-ups.

```bash
qj-desk
```

### qj-agent

Spin up AI coding sessions with isolated git worktrees.

```bash
# Plan a new idea (wayfinding session)
qj-agent plan my-app build a task manager with collaboration

# Start implementation with a clear mission
qj-agent start my-app implement JWT auth

# Add a project window to qj-desk
qj-agent add my-app fix login page

# Clone from remote
qj-agent start my-app --from git@github.com:user/app.git fix the API
```

### qj-clean

Clean up worktrees and branches when done with a project.

```bash
qj-clean my-app
```

## How It Works

- Creates isolated git worktrees for each agent (Codex, Claude)
- Sets up tmux layouts with panes for each agent plus merge authority
- Generates `QJ_TASK.md` files with mission context and rules
- Keeps your main branch clean while agents work on separate branches
