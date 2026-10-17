#!/usr/bin/env python3
"""Clone the preserved worker projects without discarding any worktree edits."""
import json
import os
from pathlib import Path
import shutil
import subprocess

HOME = Path('/home/huou07')
BACKUP = HOME / 'clean-reinstall-20261015'
SOURCE = BACKUP / 'projects-snapshot'
PROJECTS = {
    'AEH': ('home/huou07/dsh projects', HOME / 'AEH'),
    'OR': ('home/huou07/Projects/OR', BACKUP / 'prepared-projects/OR'),
    'VCE': ('home/huou07/Projects/VCE', BACKUP / 'prepared-projects/VCE'),
    'H07P': ('home/huou07/Projects/huou07-playground', HOME / 'Projects/H07P'),
    'H07P-setup': ('home/huou07/huou07-playground-setup', BACKUP / 'prepared-projects/H07P-setup'),
}

def git(path, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=*', '-C', str(path), *args])

def main():
    assert os.getuid() == 1000 and Path.home() == HOME
    assert (BACKUP.stat().st_mode & 0o077) == 0
    if not SOURCE.exists():
        SOURCE.mkdir(mode=0o700)
        subprocess.run(['tar', '--no-same-owner', '--no-same-permissions', '-xf',
                        str(BACKUP / 'projects.tar'), '-C', str(SOURCE)], check=True)
    evidence = {}
    for name, (relative, destination) in PROJECTS.items():
        source = SOURCE / relative
        # Check every indexed file before relying on a cache-excluding archive.
        for raw in git(source, 'ls-files', '-z').split(b'\0'):
            if raw:
                p = source / os.fsdecode(raw)
                # Deleted tracked files are legitimate worktree edits.
                if not p.exists() and not p.is_symlink():
                    status = git(source, 'status', '--porcelain', '--', os.fsdecode(raw))
                    sparse = git(source, 'ls-files', '-v', '--', os.fsdecode(raw)).startswith(b'S ')
                    assert b'D' in status[:2] or sparse, raw
        destination.parent.mkdir(parents=True, exist_ok=True)
        already_verified = destination.exists()
        if already_verified:
            assert git(source, 'rev-parse', 'HEAD') == git(destination, 'rev-parse', 'HEAD')
            assert git(source, 'status', '--porcelain') == git(destination, 'status', '--porcelain')
        else:
            subprocess.run(['git', 'clone', '--no-hardlinks', str(source), str(destination)], check=True)
        # Clone gives independent object storage. Restore all local branches and
        # original remote metadata, then overlay the exact index and worktree.
        for line in git(source, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads').decode().splitlines():
            ref, sha = line.split()
            git(destination, 'update-ref', ref, sha)
        shutil.copy2(source / '.git/config', destination / '.git/config')
        shutil.copy2(source / '.git/index', destination / '.git/index')
        if (source / '.git/config.worktree').exists():
            shutil.copy2(source / '.git/config.worktree', destination / '.git/config.worktree')
        for shared_index in (source / '.git').glob('sharedindex.*'):
            shutil.copy2(shared_index, destination / '.git' / shared_index.name)
        if (source / '.git/info/sparse-checkout').exists():
            shutil.copy2(source / '.git/info/sparse-checkout', destination / '.git/info/sparse-checkout')
        if not already_verified:
            for entry in destination.iterdir():
                if entry.name == '.git':
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
        for entry in source.iterdir():
            if entry.name == '.git':
                continue
            target = destination / entry.name
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
            if entry.is_symlink():
                target.symlink_to(entry.readlink())
            elif entry.is_dir():
                shutil.copytree(entry, target, symlinks=True)
            else:
                shutil.copy2(entry, target)
        # Remove files deleted in the source worktree but checked out by clone.
        deleted = git(source, 'ls-files', '--deleted', '-z').split(b'\0')
        for raw in deleted:
            if raw:
                (destination / os.fsdecode(raw)).unlink(missing_ok=True)
        assert git(source, 'rev-parse', 'HEAD') == git(destination, 'rev-parse', 'HEAD')
        assert git(source, 'status', '--porcelain') == git(destination, 'status', '--porcelain'), name
        assert git(source, 'diff', '--binary') == git(destination, 'diff', '--binary'), name
        assert git(source, 'diff', '--cached', '--binary') == git(destination, 'diff', '--cached', '--binary'), name
        git(destination, 'fsck', '--no-dangling')
        evidence[name] = {'source': relative, 'destination': str(destination),
                          'head': git(destination, 'rev-parse', 'HEAD').decode().strip(),
                          'status': git(destination, 'status', '--porcelain').decode(),
                          'verified': ['HEAD', 'index', 'worktree diff', 'untracked status', 'git fsck']}
        print(name, 'preserved and verified', flush=True)
    (BACKUP / 'projects-verified.json').write_text(json.dumps(evidence, indent=2) + '\n')
    os.chmod(BACKUP / 'projects-verified.json', 0o600)

if __name__ == '__main__':
    main()
