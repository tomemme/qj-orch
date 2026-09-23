# QJ Desk Repository Recon — Proposed Plan

Status: implementation in progress. The dedicated VM guest must run Omarchy,
as requested by QJ. Host runtime: QEMU/KVM + libvirt, without Docker.
See `docs/recon.md` for the implementation and validation status.

## User experience

```bash
qj-desk
qj-desk recon https://github.com/owner/repo
qj-desk recon owner/repo
```

Keep the existing notebook command. Recon opens or focuses the desk with the
repository request pending, then lets QJ choose Claude or Codex based on current
account usage limits. Do not launch or dispatch to an agent before that choice.
Use the selected agent through QJ's existing account setup; no additional model
provider setup is planned.

After selection, collect evidence for a pinned repository commit, show progress,
write a report, and add a link under a Project Reviews notebook section. Either
agent performs the complete review: persona fit, architecture, adoption costs,
and execution risk. There are no mandatory agent-specific roles or paired reviews.
Agent selection is manual; automatic quota detection is outside the initial scope.
Use one selected agent per review. If it hits a limit, preserve completed evidence
and findings and mark the review incomplete so it can be resumed later. Mid-review
agent switching and cross-agent handoff are outside the initial scope.

Preserve pending requests when starting herdr; the current desk startup asks the
user to rerun the command. Opening or refocusing a pending review must not start
an agent or duplicate an existing review.

Use `persona/qj.md` for fit. Report execution risk separately. Do not assign a
numeric score or claim a project is unconditionally safe.

Use a user-authored `persona/pc-specs.md` for machine compatibility. Suggested
fields: date verified, Linux distribution, kernel, CPU/architecture, RAM, GPU and
VRAM, GPU driver, available disk space, and relevant installed runtimes. Include
only compatibility facts, not serial numbers, hostnames, addresses, or credentials.
The file is optional: missing or outdated facts remain unverified. Record its hash
with each review and distinguish documented requirements from estimates. Do not
automatically inventory the PC. Machine specs describe capability, not permission
to install software or change the system.

## Intake and review boundaries

- Validate GitHub repository identifiers and safely handle arguments, paths, and
  display text. Never interpolate repository content into shell commands.
- Store review inputs separately from development repositories and worktrees.
- Pin the source commit and record retrieval time, persona hash, tool versions,
  and evidence provenance. Account for repository size, timeouts, and rate limits.
- Collect source as inert data. Do not execute installation/build/test scripts,
  fetch submodule or LFS payloads automatically, or load project agent/editor
  configuration, hooks, plugins, or tools.
- Run the reviewer from a controlled directory outside the target source. Treat
  README instructions and agent files as untrusted evidence, including attempts
  to redirect the review. Enforce filesystem, credential, execution, and network
  boundaries outside the prompt; select and verify the isolation mechanism
  before implementation of automated review.
- Separate network-enabled collection from constrained analysis. Define what
  evidence may be sent to a model provider; private-repository support requires
  an explicit data-handling policy and is deferred from the initial scope.
- Do not reuse qj-agent's automatic trust setup. Recon never installs or launches
  the target project or changes user trust configuration.

## Evidence and report

Inspect documentation, manifests/lockfiles, entry points, install/build scripts,
containers, CI, authentication, secret handling, data flows, network bindings,
updates, licensing, and repository health. Supplement with current advisories
where available; failures or unavailable scans are coverage gaps, not clean bills
of health. Distinguish declared dependencies from resolved/transitive coverage.

Produce Markdown for the desk and structured JSON for later automation. Include:

- Repository identity, reviewed commit, date, persona hash, PC-specs hash (if
  supplied), selected agent, and review status.
- Persona assessment using the format in `persona/qj.md`.
- Risk findings with severity, confidence, evidence locations, and implications.
- Expected machine impact, resources, permissions, and external services.
- Completed checks, skipped content, limitations, and unresolved questions.
- Recommendation: pass on adoption, investigate further, or consider an isolated
  trial. These recommendations do not authorize execution.

Reports describe the reviewed snapshot. A changed commit, persona, or PC profile
makes prior results potentially stale; never silently transfer approval to new code.

## Implementation increments

1. Persona and report contracts, including explicit/inferred/unknown handling.
2. Validated public-repository intake, bounded evidence collection, pinned
   commits, persistent run status, and repeat/interrupted-run behavior.
3. Enforced review isolation, static checks, constrained analysis, and reports.
4. Desk agent picker, progress/report presentation, notebook links, herdr startup
   handling, and same-agent resume behavior.
5. Verification with benign and hostile fixtures: URL/path injection, symlinks,
   instruction injection, attempted execution, credential access, network access,
   changed commits, partial scans, concurrent/repeated requests, no agent launch
   before selection, and usage-limit interruption without automatic fallback.

Acceptance: one command opens the desk, QJ picks Claude or Codex, and the chosen
agent produces an evidence-backed review without executing target code or
granting trust. Failed/incomplete reviews stay visibly incomplete; existing
notebook and agent flows continue working.

## Decisions still needed before implementation

- Enforceable isolation mechanism for both selectable agents.
- Allowed outbound evidence through the existing Claude/Codex accounts.
- QJ will supply `persona/pc-specs.md`; compatibility stays unverified for missing
  facts until it is available.
- Local machine policy for acceptable execution privileges and changes. Persona
  concerns do not automatically become hard policy rules.

Runtime trials, installation, and promotion into development sessions are later,
separate actions. Static review cannot prove runtime safety.
