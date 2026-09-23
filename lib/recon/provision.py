#!/usr/bin/env python3
"""Create an Omarchy installer VM and trusted, read-only guest setup media."""
import hashlib
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from host import ORCH, STATE, VM, IP, network_filter
import xml.etree.ElementTree as ET

IMAGE = 'omarchy-4.0.4.iso'
DEST = Path('/var/lib/libvirt/images/qj-recon')

def run(*args, **kwargs):
    if args[0] == 'sudo' and os.environ.get('QJ_VM_DESKTOP_AUTH') == '1':
        args = ('pkexec', *args[1:])
    return subprocess.run(list(args), check=True, **kwargs)

def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def verify_image(image, manifest):
    import re
    matches = []
    for line in manifest.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip('*') == image.name:
            matches.append(fields[0].lower())
    if len(matches) != 1 or not re.fullmatch('[a-f0-9]{64}', matches[0]):
        raise ValueError('Checksum manifest must contain exactly one matching ISO filename')
    if file_hash(image) != matches[0]:
        raise ValueError('Omarchy ISO checksum mismatch')
    return matches[0]

def setup(image=None, checksum=None):
    for tool in ('virsh', 'virt-install', 'qemu-img', 'genisoimage', 'ssh-keygen'):
        if not shutil.which(tool):
            raise ValueError('Install prerequisites: omarchy pkg add qemu-base libvirt virt-install dnsmasq cdrtools edk2-ovmf virt-viewer qemu-hw-display-virtio-gpu-pci')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    run('virsh', '-c', 'qemu:///system', 'list', '--all', stdout=subprocess.DEVNULL)
    if subprocess.run(['virsh', '-c', 'qemu:///system', 'dominfo', VM], capture_output=True).returncode == 0:
        raise ValueError('qj-recon already exists; refusing to replace it')
    if not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise ValueError('KVM is unavailable')
    import json, ipaddress
    routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route'], text=True))
    for route in routes:
        if route.get('dst', 'default') != 'default' and ipaddress.ip_network('192.168.231.0/24').overlaps(ipaddress.ip_network(route['dst'], strict=False)):
            raise ValueError('Recon subnet overlaps an existing route')
    for name in ('id_ed25519', 'guest_host_ed25519'):
        key = STATE / name
        if not key.exists():
            run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'qj-recon', '-f', str(key))
    (STATE / 'known_hosts').write_text(IP + ' ' + (STATE / 'guest_host_ed25519.pub').read_text())
    image = (image or STATE / IMAGE).resolve()
    checksum = checksum or image.with_name(image.name + '.sha256')
    if not image.is_file() or not checksum.is_file():
        raise ValueError('Download an official Omarchy ISO and matching .iso.sha256; use qj-vm setup --iso <path> [--checksum <path>]')
    print(f'Verifying local ISO: {image.name}', flush=True)
    expected = verify_image(image, checksum.read_text())
    (STATE / 'image-sha256.txt').write_text(f'{expected}  {image.name}\n')
    ET.ElementTree(network_filter()).write(STATE / 'filter.xml', encoding='unicode')
    with tempfile.TemporaryDirectory(prefix='qj-vm-') as temporary:
        temp = Path(temporary)
        for name in ('common.py', 'guest.py'):
            shutil.copyfile(ORCH / 'lib/recon' / name, temp / name)
        for name in ('prompt.md', 'bootstrap.sh'):
            shutil.copyfile(ORCH / 'templates/recon' / name, temp / name)
        shutil.copyfile(STATE / 'id_ed25519.pub', temp / 'authorized_keys')
        shutil.copyfile(STATE / 'guest_host_ed25519', temp / 'ssh_host_ed25519_key')
        shutil.copyfile(STATE / 'guest_host_ed25519.pub', temp / 'ssh_host_ed25519_key.pub')
        seed = STATE / 'setup.iso'
        run('genisoimage', '-quiet', '-output', str(seed), '-volid', 'QJSETUP', '-joliet', '-rock', str(temp))
        seed.chmod(0o600)
        # Disk creation is exclusive; a failed setup never overwrites a VM disk.
        disk = STATE / 'omarchy.qcow2'
        if disk.exists():
            raise ValueError('Staged VM disk exists from an earlier attempt; inspect it before retrying')
        run('qemu-img', 'create', '-f', 'qcow2', str(disk), '40G')
        run('sudo', 'bash', str(ORCH / 'lib/recon/install-host.sh'), str(STATE), str(ORCH), str(image))
    print('Omarchy installer is ready: virt-viewer --connect qemu:///system qj-recon')
    print('Complete installation on the 40 GiB virtual disk, then run the QJSETUP bootstrap inside the guest. See docs/recon.md.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=Path)
    parser.add_argument('--checksum', type=Path)
    args = parser.parse_args()
    try:
        setup(args.iso, args.checksum)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f'qj-vm: {exc}')
