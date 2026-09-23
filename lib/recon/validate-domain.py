#!/usr/bin/env python3
"""Fail closed before defining a domain; prints only safe disk summaries."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from host import validate_vm

xml = Path(sys.argv[1]).read_text()
validate_vm(xml)
root = ET.fromstring(xml)
disks = root.findall('devices/disk')
if len(disks) != 3 or sum(d.get('device') == 'disk' for d in disks) != 1:
    raise SystemExit('Expected exactly one virtual hard disk and two CD images')
for disk in disks:
    source = disk.find('source')
    path = Path(source.get('file', ''))
    if disk.get('type') != 'file' or path.parent != Path('/var/lib/libvirt/images/qj-recon'):
        raise SystemExit('Refusing a non-file disk or a disk outside the recon directory')
    expected = {'disk': {'omarchy.qcow2'}, 'cdrom': {'installer.iso', 'setup.iso'}}
    if path.name not in expected.get(disk.get('device'), set()):
        raise SystemExit('Unexpected disk filename')
    if path.resolve() != path:
        raise SystemExit('Refusing a redirected disk path')
    print(f'Validated {disk.get("device")}: {path}')
