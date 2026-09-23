"""Shared recon contracts. Standard library only; never evaluate repository input."""
import json
import re
import hashlib
from pathlib import Path

MAX_REQUEST = 64 * 1024
MAX_REPORT = 2 * 1024 * 1024

def repository(value):
    value = value.strip()
    if value.startswith('https://github.com/'):
        value = value[len('https://github.com/'):]
    value = value.removesuffix('/').removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', value):
        raise ValueError('Use owner/repo or https://github.com/owner/repo (public repositories only)')
    if value.split('/')[1] in ('.', '..'):
        raise ValueError('Invalid repository name')
    return value

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def save_json(path, value):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)

def clean_text(value):
    # Guest output must not carry terminal control sequences to the host.
    return ''.join(c for c in value if c in '\n\t' or (c.isprintable() and c not in '\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069'))
