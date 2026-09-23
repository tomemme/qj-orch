# VM-backed repository recon

`qj-desk recon owner/repo` opens the desk and an agent picker. Choose Claude or
Codex based on your available usage. One agent reviews the supplied static
evidence inside a dedicated Linux VM. No repository checkout is made on the host.

## Setup

Host requirements: Linux with working `/dev/kvm`, Python 3.11+, OpenSSH,
QEMU/KVM, libvirt, virt-install, dnsmasq, UEFI firmware, virt-viewer, and genisoimage. On Omarchy:

```bash
omarchy pkg add qemu-base libvirt virt-install dnsmasq cdrtools edk2-ovmf virt-viewer qemu-hw-display-virtio-gpu-pci qemu-hw-display-virtio-vga
sudo systemctl enable --now virtqemud.socket virtnetworkd.socket virtnwfilterd.socket virtstoraged.socket virtsecretd.socket
qj-vm setup --iso ~/.local/state/qj-recon/omarchy-4.0.3.iso
qj-vm status
qj-vm login claude
qj-vm login codex
```

Download an official Omarchy ISO and its matching `.iso.sha256` file first.
Setup verifies the local ISO against that manifest (not an independent signature
check); `--checksum <path>` selects a manifest stored elsewhere. The current VM
uses the user-supplied Omarchy 4.0.3 ISO, verified against the official checksum. It creates a KVM guest
with 4 vCPUs, 8 GiB RAM, a 40 GiB virtual disk, UEFI, and a loopback-only VNC console.
No host disk is passed through. Libvirt management may request desktop authentication.

The first version uses the ordinary Omarchy installer:

1. Open `virt-viewer --connect qemu:///system qj-recon`.
2. Install Omarchy on the sole **40 GiB virtual disk**. Create your guest admin
   account using a name other than `qj-review` (reserved for automation).
3. If you choose disk encryption, unlock it through the VM console after each
   cold boot; SSH automation cannot bypass the disk-unlock prompt.
4. Boot the installed system, open its terminal, and run:

   ```bash
   sudo mkdir -p /mnt/qj-setup
   sudo mount -o ro /dev/disk/by-label/QJSETUP /mnt/qj-setup
   sudo bash /mnt/qj-setup/bootstrap.sh
   sudo umount /mnt/qj-setup
   ```

The trusted setup disc installs the reviewer and clients, creates the separate
non-admin `qj-review` account, installs pinned SSH host keys, and permits SSH only
from the host gateway. It does not clone your host account or configuration.
The guest must finish this step before `qj-vm start` can report readiness.
Installer automation is deferred until its version-specific contract is verified.

Sign in inside the VM with the accounts you want to use. Host authentication
files are not copied. Credentials inside the guest remain sensitive. A restored
snapshot can contain expired login state; sign in again if necessary.

Copy `persona/pc-specs.example.md` to `persona/pc-specs.md` and fill in verified
compatibility facts. That local file is ignored by Git. Missing specs are allowed.
Persona and supplied specs are sent to the selected provider with the evidence.

## Review and resume

```bash
qj-desk recon https://github.com/owner/repo
qj-desk resume <review-id>
# In an ordinary terminal, bypassing desk layout:
qj-recon review <review-id>
```

A new request does not launch either agent. The agent choice is saved on first
selection. Each request gets an ID and local state beneath
`~/.local/state/qj-recon/reviews/`. Override the state root with `QJ_RECON_DIR`.
On failure or a usage limit, state remains incomplete. Resume reruns the selected
agent against saved evidence for the same commit; this is not conversation
continuation and can consume usage again. Switching agents is deferred.

The first version supplies a bounded evidence bundle to the agent, rather than
allowing arbitrary shell exploration. Claude has no built-in tools or MCP
servers enabled; Codex has shell, unified execution, subagents, apps, hooks, and
web search disabled, with a read-only sandbox and no approval escalation.
Provider behavior must be checked against the installed client versions.
The VM is the host isolation boundary, not a promise that a model cannot make
mistakes or that guest account credentials are invulnerable.

The collector uses GitHub metadata and a commit-pinned source archive. It never
checks out a repository, extracts archive paths to disk, loads repository agent
configuration, initializes submodules, fetches LFS objects, installs project
dependencies, or executes target code. Source is supplied as numbered text.
Downloads, file count, expanded archive size, file size, evidence size, review
time, and returned output are bounded. Skipped files and missing checks are
reported explicitly. This is an initial static review, not an exhaustive audit.

Reports contain persona fit and execution risk separately, with unknowns and
coverage gaps. No numeric score or automatic adoption. Current advisories and
transitive dependency scans are not implemented; the report must not imply they
ran. Open issue/PR and release samples are bounded, not a complete history.

Reports are pulled through SSH into fixed local files and linked from the
notebook. Terminal controls are removed. Treat report content and links as
untrusted; don't execute suggested commands without assessing them. Recon's
notebook editor disables user configuration and modelines via `nvim -u NONE`.

## Isolation and VM lifecycle

The guest has no shared folders, clipboard integration, host device
passthrough, SSH-agent forwarding, or host credentials. Dedicated SSH keys and
pinned guest host keys are created during setup. VM disks live under
`/var/lib/libvirt/images/qj-recon/`. No Docker or GPU passthrough is required. The console uses virtual graphics.
Omarchy may include Docker inside the guest, but recon does not use it and its
review account must not belong to the docker group.

A dedicated libvirt NAT network and per-interface filter permit DHCP/DNS,
host-initiated SSH, and public HTTP/HTTPS. New connections to private, loopback,
link-local, carrier-grade NAT (including Tailscale), and multicast/reserved
ranges are blocked; IPv6 is blocked. Internet HTTPS remains available to the
reviewer, so this is not a provider-domain allowlist. Validate the policy on the
actual host before reviewing untrusted repositories.

```bash
qj-vm shutdown
qj-vm status                 # Wait for 'shut off'
qj-vm checkpoint             # Create qj-clean after setup/login, before reviews
qj-vm start
# After exporting any needed reports and shutting down:
qj-vm reset                  # Restore qj-clean; discards subsequent guest changes
```

Reset is explicit. It discards guest evidence, sessions, and login changes since
the checkpoint; exported host reports remain. Keep the baseline patched and
refresh it deliberately. Do not checkpoint a guest you suspect is compromised.

## Validation

```bash
python3 -m unittest discover -s tests -v
bash -n bin/qj-desk bin/qj-recon bin/qj-vm
```

Before first untrusted use, verify live host/LAN blocking, public HTTPS, SSH key
pinning, absent shared mounts/devices, both clients' restricted launch options,
and successful report export. Unit tests alone do not establish VM isolation.

References: [libvirt filters](https://libvirt.org/formatnwfilter.html),
[virsh](https://www.libvirt.org/manpages/virsh.html),
[Codex configuration](https://developers.openai.com/codex/config-reference),
[Claude CLI](https://code.claude.com/docs/en/cli-reference).
