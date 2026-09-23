#!/usr/bin/env python3
"""Host-side VM transport and review state. Repository source stays in the VM."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import resource
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import ipaddress
from common import repository, save_json, clean_text, MAX_REQUEST, MAX_REPORT

ORCH = Path(__file__).resolve().parents[2]
STATE = Path(os.environ.get('QJ_RECON_DIR', str(Path.home() / '.local/state/qj-recon')))
VM = 'qj-recon'
IP = '192.168.231.2'

def network_filter():
    """Also deny host public addresses and directly connected public LANs."""
    root = ET.parse(ORCH / 'templates/recon/filter.xml').getroot()
    routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route'], text=True))
    addresses = json.loads(subprocess.check_output(['ip', '-j', '-4', 'address'], text=True))
    networks = set()
    for interface in addresses:
        for entry in interface.get('addr_info', []):
            if entry.get('family') == 'inet':
                networks.add(entry['local'] + '/32')
    for route in routes:
        if route.get('scope') == 'link' and route.get('dst', 'default') != 'default':
            networks.add(str(ipaddress.ip_network(route['dst'], strict=False)))
    # This bridge appears only after setup. Its subnet is already denied.
    networks = {n for n in networks if not ipaddress.ip_network(n).subnet_of(ipaddress.ip_network('192.168.231.0/24'))}
    for network in sorted(networks):
        net = ipaddress.ip_network(network)
        rule = ET.SubElement(root, 'rule', action='drop', direction='out', priority='199')
        ET.SubElement(rule, 'all', dstipaddr=str(net.network_address), dstipmask=str(net.prefixlen))
    return root

def virsh(*args, capture=True):
    return subprocess.run(['virsh', '-c', 'qemu:///system', *args], check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout

def validate_vm(xml):
    root = ET.fromstring(xml)
    if root.get('type') != 'kvm':
        raise ValueError('Recon requires a KVM domain')
    devices = root.find('devices')
    allowed_namespace = '{http://libosinfo.org/xmlns/libvirt/domain/1.0}'
    if devices is None or any('}' in n.tag and not n.tag.startswith(allowed_namespace) for n in root.iter()):
        raise ValueError('Unsupported domain extensions or missing devices')
    if any(devices.findall(tag) for tag in ('filesystem', 'hostdev', 'redirdev', 'channel')):
        raise ValueError('VM has shared folders, host devices, redirection, or graphics enabled')
    for graphics in devices.findall('graphics'):
        if graphics.get('type') != 'vnc' or graphics.get('listen') != '127.0.0.1':
            raise ValueError('Only loopback VNC is permitted for the Omarchy console')
        if any(n.get('address') != '127.0.0.1' for n in graphics.findall('listen')):
            raise ValueError('Nonlocal graphics listener')
    interfaces = devices.findall('interface')
    if len(interfaces) != 1 or interfaces[0].get('type') != 'network':
        raise ValueError('Expected exactly one restricted network interface')
    nic = interfaces[0]
    if nic.find('source').get('network') != VM or nic.find('filterref') is None or nic.find('filterref').get('filter') != VM:
        raise ValueError('VM is missing the recon network/filter')
    for disk in devices.findall('disk'):
        source = disk.find('source')
        if (disk.get('device') == 'cdrom' and disk.get('type') == 'file' and
            (source is None or (set(source.attrib) <= {'index'} and len(source) == 0))):
            continue  # Live libvirt XML retains <source index='…'/> after eject.
        if (source is None or disk.get('type') != 'file' or
            Path(source.get('file', '')).parent != Path('/var/lib/libvirt/images/qj-recon') or
            Path(source.get('file', '')).name not in ('omarchy.qcow2', 'installer.iso', 'setup.iso')):
            raise ValueError('Unexpected VM disk source')
    return True

def ssh_args():
    return ['ssh', '-F', '/dev/null', '-i', str(STATE / 'id_ed25519'),
            '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none', '-o', 'ForwardAgent=no',
            '-o', 'ForwardX11=no', '-o', 'ClearAllForwardings=yes', '-o', 'PermitLocalCommand=no',
            '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={STATE / "known_hosts"}',
            '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', f'qj-review@{IP}']

def check():
    validate_vm(virsh('dumpxml', VM, '--inactive'))
    if virsh('domstate', VM).strip() == 'running':
        validate_vm(virsh('dumpxml', VM))
    # Compare policy structure, ignoring libvirt-added UUID and whitespace.
    expected = network_filter()
    actual = ET.fromstring(virsh('nwfilter-dumpxml', VM))
    def shape(node):
        return (node.tag, sorted(node.attrib.items()), [shape(c) for c in node if c.tag != 'uuid'])
    if shape(expected) != shape(actual):
        raise ValueError('VM network policy differs from the reviewed template')
    network = ET.fromstring(virsh('net-dumpxml', VM))
    if (network.find('bridge').get('name') != 'qj-recon0' or
        network.find('forward').get('mode') != 'nat' or
        len(network.findall('ip')) != 1 or network.find('ip').get('address') != '192.168.231.1'):
        raise ValueError('Unexpected recon network configuration')
    for name in ('id_ed25519', 'known_hosts'):
        if not (STATE / name).is_file():
            raise ValueError('VM transport missing; run qj-vm setup')

def start():
    check()
    if virsh('domstate', VM).strip() == 'shut off':
        virsh('start', VM)
    for _ in range(45):
        p = subprocess.run(ssh_args() + ['true'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.returncode == 0:
            ready = subprocess.run(ssh_args() + ['test -f /etc/qj-recon-ready'], stdout=subprocess.DEVNULL)
            if ready.returncode:
                raise ValueError('Run the QJSETUP bootstrap inside the installed Omarchy guest first')
            return
        time.sleep(2)
    raise ValueError('VM SSH did not become ready; inspect qj-vm status')

def new(repo):
    repo = repository(repo)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_id = secrets.token_hex(8)
    folder = STATE / 'reviews' / run_id
    folder.mkdir(parents=True, mode=0o700)
    request = {'id': run_id, 'repository': repo, 'persona': (ORCH / 'persona/qj.md').read_text()}
    specs = ORCH / 'persona/pc-specs.md'
    if specs.exists():
        request['pc_specs'] = specs.read_text()
    if len(json.dumps(request).encode()) > MAX_REQUEST - 100:
        raise ValueError('Persona/specs exceed request limit')
    save_json(folder / 'request.json', request)
    save_json(folder / 'state.json', {'status': 'pending', 'repository': repo})
    print(run_id)

def review(run_id):
    if len(run_id) != 16 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('Invalid review ID')
    folder = STATE / 'reviews' / run_id
    with (folder / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        request = json.loads((folder / 'request.json').read_text())
        print(f'QJ recon: {request["repository"]}', flush=True)
        if 'agent' not in request:
            print('Choose your account for this review: 1) Claude  2) Codex  q) Later')
            choice = input('Agent: ').strip().lower()
            if choice in ('q', ''):
                return
            agent = {'1': 'claude', 'claude': 'claude', '2': 'codex', 'codex': 'codex'}.get(choice)
            if not agent:
                raise ValueError('Choose Claude or Codex; no agent was started')
            request['agent'] = agent
            save_json(folder / 'request.json', request)
        start()
        print(f'Reviewing with {request["agent"]} inside the VM. This may take several minutes.', flush=True)
        save_json(folder / 'state.json', {'status': 'running', 'repository': request['repository'], 'agent': request['agent']})
        try:
            # Bound guest-controlled output on disk and in memory.
            with (folder / 'response.json').open('wb') as output:
                def limit_output():
                    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_REPORT + 65536, MAX_REPORT + 65536))
                result = subprocess.run(ssh_args() + ['python3 /opt/qj-recon/guest.py'],
                                        input=json.dumps(request).encode(), stdout=output,
                                        timeout=1900, preexec_fn=limit_output)
                code = result.returncode
            if code:
                raise ValueError('VM review transport failed; review can be resumed')
            response = json.loads((folder / 'response.json').read_text())
            if 'error' in response:
                raise ValueError(clean_text(response['error']))
            state = response['state']
            if any(state.get(key) != request[key] for key in ('id', 'repository', 'agent')):
                raise ValueError('Guest response identity does not match this review')
            save_json(folder / 'state.json', state)
            if state['status'] != 'report-ready':
                raise ValueError(clean_text(state.get('error', 'Review incomplete')))
            report = clean_text(response['report'])
            (folder / 'report.md').write_text(report)
            notebook = Path(os.environ.get('QJ_ORCH_DIR', str(ORCH))) / 'notebook.md'
            with notebook.open('a+') as note:
                fcntl.flock(note, fcntl.LOCK_EX)
                note.seek(0)
                existing = note.read()
                if run_id not in existing:
                    note.seek(0, 2)
                    if '## Project Reviews' not in existing:
                        note.write('\n## Project Reviews\n')
                    note.write(f'\n- [{request["repository"]} — {request["agent"]}]({folder / "report.md"}) <!-- {run_id} -->\n')
            print(f'Report saved: {folder / "report.md"}')
        except BaseException as exc:
            save_json(folder / 'state.json', {'status': 'incomplete', 'error': str(exc), 'repository': request['repository']})
            raise

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['new', 'review', 'status', 'start', 'login', 'shutdown', 'checkpoint', 'reset'])
    p.add_argument('value', nargs='?')
    args = p.parse_args()
    if args.action == 'new':
        new(args.value or '')
    elif args.action == 'review':
        review(args.value or '')
    elif args.action == 'status':
        check()
        print(virsh('domstate', VM).strip())
    elif args.action == 'start':
        start()
    elif args.action == 'shutdown':
        check()
        virsh('shutdown', VM, capture=False)
    elif args.action in ('checkpoint', 'reset'):
        check()
        if virsh('domstate', VM).strip() != 'shut off':
            raise ValueError('Shut down the VM first with qj-vm shutdown; wait until qj-vm status says shut off')
        if args.action == 'checkpoint':
            virsh('snapshot-create-as', VM, 'qj-clean', '--description', 'User-created review baseline', capture=False)
        else:
            virsh('snapshot-revert', VM, 'qj-clean', capture=False)
    elif args.action == 'login':
        if args.value not in ('claude', 'codex'):
            raise ValueError('Use qj-vm login claude|codex')
        start()
        cmd = 'claude auth login' if args.value == 'claude' else 'codex login --device-auth'
        ssh = ssh_args()
        ssh.insert(1, '-t')
        subprocess.run(ssh + [cmd], check=True)

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as exc:
        sys.exit(f'qj-recon: {exc}')
