#!/usr/bin/env bash
# Run once, as root, INSIDE the freshly installed Omarchy guest.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run this guest setup with sudo.' >&2; exit 1; }
[[ -d /usr/share/omarchy ]] || { echo 'This setup requires an Omarchy guest.' >&2; exit 1; }
[[ $(systemd-detect-virt) == kvm || $(systemd-detect-virt) == qemu ]] || { echo 'Refusing setup outside a QEMU/KVM guest.' >&2; exit 1; }
MEDIA="$(dirname "$(readlink -f "$0")")"
[[ -f "$MEDIA/guest.py" && -f "$MEDIA/authorized_keys" ]] || exit 1
# A dedicated non-admin account keeps normal Omarchy user configuration and
# desktop integrations out of the automated reviewer session.
if ! id qj-review >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash qj-review
fi
if id -nG qj-review | grep -Eq '(^| )(wheel|sudo|docker|libvirt)( |$)'; then
  echo 'qj-review must not belong to privileged groups.' >&2
  exit 1
fi
omarchy pkg add python nodejs npm openssh
npm install -g @openai/codex @anthropic-ai/claude-code
install -d -m 0755 /opt/qj-recon
install -m 0644 "$MEDIA/common.py" "$MEDIA/guest.py" "$MEDIA/prompt.md" /opt/qj-recon/
install -d -m 0700 -o qj-review -g qj-review /home/qj-review/.ssh
install -m 0600 -o qj-review -g qj-review "$MEDIA/authorized_keys" /home/qj-review/.ssh/authorized_keys
# Lock password authentication in sshd; a non-locked random password hash allows
# public-key login on distributions where a locked account rejects keys too.
PASSWORD_HASH=$(openssl rand -base64 48 | openssl passwd -6 -stdin)
usermod --password "$PASSWORD_HASH" qj-review
unset PASSWORD_HASH
install -m 0600 "$MEDIA/ssh_host_ed25519_key" /etc/ssh/ssh_host_ed25519_key
install -m 0644 "$MEDIA/ssh_host_ed25519_key.pub" /etc/ssh/ssh_host_ed25519_key.pub
cat >/etc/ssh/sshd_config.d/00-qj-recon.conf <<'EOF'
HostKey /etc/ssh/ssh_host_ed25519_key
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers qj-review
AllowAgentForwarding no
AllowTcpForwarding no
X11Forwarding no
EOF
sshd -t
systemctl enable --now sshd
systemctl restart sshd
if command -v ufw >/dev/null; then
  ufw allow from 192.168.231.1 to any port 22 proto tcp
fi
printf 'qj-recon-omarchy-v1\n' >/etc/qj-recon-guest
touch /etc/qj-recon-ready
echo 'Guest setup complete. Sign into your chosen agent with qj-vm login from the host.'
