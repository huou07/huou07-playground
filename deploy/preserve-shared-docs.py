#!/usr/bin/env python3
"""Keep the former shared instructions as AEH documentation, byte for byte."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HOME = Path('/home/huou07')
BACKUP = HOME / 'clean-reinstall-20261015'
SOURCE = BACKUP / 'shared-framework'

def files(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            result[str(path.relative_to(root))] = {'symlink': str(path.readlink())}
        elif path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def main():
    assert os.getuid() == 1000 and (BACKUP / 'projects-verified.json').exists()
    os.umask(0o077)
    assert not SOURCE.exists()
    SOURCE.mkdir(mode=0o700)
    subprocess.run(['tar', '--no-same-owner', '--no-same-permissions', '-xf',
                    str(BACKUP / 'shared-framework.tar'), '-C', str(SOURCE)], check=True)
    skills = HOME / 'AEH/skills'
    docs = HOME / 'AEH/docs/writing-agents-md'
    assert not skills.exists() and not docs.exists()
    shutil.copytree(SOURCE / 'skills', skills, symlinks=True)
    docs.mkdir()
    shutil.copy2(SOURCE / 'AGENTS.md', docs / 'shared-AGENTS.md')
    shutil.copy2(SOURCE / 'skills.md', docs / 'shared-skills-catalog.md')
    assert files(SOURCE / 'skills') == files(skills)
    assert (SOURCE / 'AGENTS.md').read_bytes() == (docs / 'shared-AGENTS.md').read_bytes()
    (docs / 'README.md').write_text('''# Writing AGENTS.md: preserved operating example

`shared-AGENTS.md` is the exact former `/srv/agent-workbench/AGENTS.md`.
It is a historical reference, not the active policy for a new installation.
`shared-skills-catalog.md` preserves its skill catalog; complete shared skill
bodies are now in `../../skills/`.

When writing a project AGENTS.md, state the project objective, working paths,
allowed actions, verification requirements and handoff expectations explicitly.
Review historical account names, wrappers, isolation assumptions and absolute
paths before reusing any example. Instructions in these documents do not
authorize reinstating the retired worker setup.

Full instruction history, pending proposals and the former framework Git
history are retained privately in `~/clean-reinstall-20261015/shared-framework`.
''')
    (BACKUP / 'shared-docs-verified.json').write_text(json.dumps({
        'skills': files(skills), 'agents_sha256': hashlib.sha256((docs / 'shared-AGENTS.md').read_bytes()).hexdigest(),
        'destination': str(docs)}, indent=2) + '\n')
    print('Shared skills and AGENTS.md copied to AEH documentation; all bytes verified.')

if __name__ == '__main__':
    main()
