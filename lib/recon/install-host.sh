#!/usr/bin/env bash
# Privileged final stage of qj-vm setup. Inputs are locally generated artifacts.
set -euo pipefail
[[ $EUID == 0 && $# == 3 ]] || exit 1
STATE="$1"
ORCH="$2"
ISO="$3"
DEST=/var/lib/libvirt/images/qj-recon
virsh -c qemu:///system list --all >/dev/null
if virsh -c qemu:///system dominfo qj-recon >/dev/null 2>&1; then
  echo 'VM already defined; refusing to alter it through setup.' >&2
  exit 1
fi
install -d -m 0711 "$DEST"
# A retry may reuse identical staged files, but never overwrite an existing disk.
copy_new() {
  if [[ -e "$2" ]]; then
    cmp --silent "$1" "$2" || { echo "Existing file differs; refusing to overwrite: $2" >&2; exit 1; }
  else
    install -m 0600 "$1" "$2"
  fi
}
copy_new "$STATE/omarchy.qcow2" "$DEST/omarchy.qcow2"
copy_new "$STATE/setup.iso" "$DEST/setup.iso"
copy_new "$ISO" "$DEST/installer.iso"
FILTER=$(mktemp /tmp/qj-recon-filter.XXXXXX.xml)
DOMAIN=$(mktemp /tmp/qj-recon-domain.XXXXXX.xml)
trap 'rm -f "$DOMAIN" "$FILTER"' EXIT
# libvirt requires the existing UUID when redefining a named filter.
python3 - "$STATE/filter.xml" "$FILTER" <<'PY'
import subprocess, sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
old = subprocess.run(['virsh', '-c', 'qemu:///system', 'nwfilter-dumpxml', 'qj-recon'], capture_output=True, text=True)
if old.returncode == 0:
    uuid = ET.fromstring(old.stdout).find('uuid')
    if uuid is not None:
        root.append(uuid)
ET.ElementTree(root).write(sys.argv[2], encoding='unicode')
PY
virsh -c qemu:///system nwfilter-define "$FILTER"
virsh -c qemu:///system net-define "$ORCH/templates/recon/network.xml"
virsh -c qemu:///system net-start qj-recon
virsh -c qemu:///system net-autostart qj-recon
virt-install --connect qemu:///system --name qj-recon --memory 8192 --vcpus 4 \
  --cpu host-passthrough --virt-type kvm --machine q35 --boot uefi,hd,cdrom \
  --os-variant archlinux --disk "path=$DEST/omarchy.qcow2,format=qcow2,bus=virtio" \
  --disk "path=$DEST/setup.iso,device=cdrom" --cdrom "$DEST/installer.iso" \
  --network network=qj-recon,model=virtio,mac=52:54:00:71:23:02,filterref.filter=qj-recon \
  --graphics vnc,listen=127.0.0.1 --video virtio --channel none --noautoconsole --print-xml=1 >"$DOMAIN"
python3 "$ORCH/lib/recon/validate-domain.py" "$DOMAIN"
virsh -c qemu:///system define "$DOMAIN"
virsh -c qemu:///system start qj-recon
