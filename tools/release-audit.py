#!/usr/bin/env python3
"""Produce path-free CycloneDX/license artifacts and a freshly fetched RustSec gate.

Requires Python >=3.11, Cargo, cargo-audit, and network access. It does not execute
application code or build scripts. Outputs omit metadata's local paths and crate
source contents except public upstream license/notice documents.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import quote

REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'


def run(command, cwd=None, check=True):
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=300)
    if check and result.returncode:
        # Tool stderr may contain local paths; keep it out of distributable artifacts.
        raise RuntimeError('Release audit command failed: ' + Path(command[0]).name)
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_license(value):
    return value.replace('/', ' OR ') if value else None


def license_notices(package):
    root = Path(package['manifest_path']).parent
    notices = []
    total = 0
    # Only registry crate source license documents; do not follow links or read arbitrary license_file paths.
    for parent, directories, files in os.walk(root, followlinks=False):
        relative = Path(parent).relative_to(root)
        directories[:] = sorted(name for name in directories if not (Path(parent) / name).is_symlink() and len(relative.parts) < 3)
        for name in sorted(files):
            if not re.match(r'(?i)^(license|licence|copying|notice)(?:[._-]|$)', name):
                continue
            candidate = Path(parent) / name
            if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 1_000_000:
                continue
            text = candidate.read_text(errors='replace')
            total += len(text.encode())
            if total > 3_000_000:
                raise RuntimeError('Crate license documents exceed audit bound')
            notices.append((candidate.relative_to(root).as_posix(), text))
    return notices


def generate(metadata, lock, repository):
    locked = {(p['name'], p['version'], p.get('source')): p for p in lock['package']}
    refs = {p['id']: 'pkg:cargo/' + quote(p['name'], safe='') + '@' + quote(p['version'], safe='') for p in metadata['packages']}
    members = set(metadata['workspace_members'])
    components, inventory, notices, problems = [], [], [], []
    for package in sorted(metadata['packages'], key=lambda p: (p['name'], p['version'])):
        key = (package['name'], package['version'], package.get('source'))
        entry = locked.get(key)
        if entry is None:
            raise RuntimeError('Metadata package is absent from Cargo.lock')
        expression = normalize_license(package.get('license'))
        first_party = package['id'] in members
        if not first_party and package.get('source') != REGISTRY:
            problems.append('Non-crates.io source requires review: ' + package['name'])
        if not first_party and not expression:
            problems.append('Missing declared third-party license: ' + package['name'])
        component = {'type': 'application' if first_party else 'library', 'name': package['name'], 'version': package['version'], 'bom-ref': refs[package['id']], 'purl': refs[package['id']]}
        if expression:
            component['licenses'] = [{'expression': expression}]
        elif first_party and (repository / 'LICENSE').is_file():
            component['licenses'] = [{'license': {'name': 'GPL-3.0 (repository LICENSE; Cargo manifest undeclared)'}}]
        if entry.get('checksum'):
            component['hashes'] = [{'alg': 'SHA-256', 'content': entry['checksum']}]
        if not first_party:
            component['externalReferences'] = [{'type': 'distribution', 'url': 'https://crates.io/crates/' + quote(package['name'], safe='') + '/' + quote(package['version'], safe='')}]
        documents = license_notices(package) if not first_party else []
        if not first_party and not documents:
            problems.append('No upstream license/notice document found: ' + package['name'])
        inventory.append({'name': package['name'], 'version': package['version'], 'license_expression': expression, 'source': 'workspace' if first_party else 'crates.io' if package.get('source') == REGISTRY else 'unreviewed', 'checksum_sha256': entry.get('checksum'), 'license_documents': [name for name, _ in documents]})
        for name, text in documents:
            notices.append('\n' + '=' * 72 + '\n' + package['name'] + ' ' + package['version'] + ' / ' + name + '\n' + '=' * 72 + '\n' + text + '\n')
        components.append(component)
    graph = []
    for node in metadata['resolve']['nodes']:
        if node['id'] in refs:
            graph.append({'ref': refs[node['id']], 'dependsOn': sorted(refs[dependency] for dependency in node['dependencies'] if dependency in refs)})
    sbom = {'$schema': 'http://cyclonedx.org/schema/bom-1.6.schema.json', 'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
            'metadata': {'properties': [{'name': 'h07p:scope', 'value': 'Cargo Linux amd64 metadata graph, including build/dev dependencies; not a compiled binary inventory'}, {'name': 'h07p:lockfile-sha256', 'value': digest(repository / 'Cargo.lock')}]},
            'components': components, 'dependencies': sorted(graph, key=lambda item: item['ref'])}
    return sbom, inventory, ''.join(notices), problems


def sanitized_advisories(audit):
    result = []
    for vulnerability in audit.get('vulnerabilities', {}).get('list', []):
        advisory, package = vulnerability.get('advisory', {}), vulnerability.get('package', {})
        result.append({'id': advisory.get('id'), 'title': advisory.get('title'), 'url': advisory.get('url'), 'package': package.get('name'), 'version': package.get('version'), 'patched': vulnerability.get('versions', {}).get('patched', [])})
    warnings = {key: len(value) for key, value in audit.get('warnings', {}).items()}
    return result, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--cargo', default='cargo')
    parser.add_argument('--cargo-audit', default='cargo-audit')
    parser.add_argument('--advisory-db', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('artifacts/release-audit'))
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        assert normalize_license('MIT/Apache-2.0') == 'MIT OR Apache-2.0'
        assert sanitized_advisories({'warnings': {'notice': [{}]}, 'vulnerabilities': {'list': []}}) == ([], {'notice': 1})
        print('PASS: license normalization and advisory redaction self-check')
        return
    repository = args.repo.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / '.gitignore').write_text('*\n')
    (output / 'report.json').write_text(json.dumps({'schema': 1, 'status': 'incomplete', 'reason': 'Fresh metadata and RustSec audit have not completed'}) + '\n')
    lock_path = repository / 'Cargo.lock'
    lock_sha = digest(lock_path)
    metadata = json.loads(run([args.cargo, 'metadata', '--locked', '--format-version', '1', '--filter-platform', 'x86_64-unknown-linux-gnu'], cwd=repository).stdout)
    lock = tomllib.loads(lock_path.read_text())
    sbom, inventory, notices, problems = generate(metadata, lock, repository)
    (output / 'sbom.cdx.json').write_text(json.dumps(sbom, indent=2) + '\n')
    (output / 'licenses.json').write_text(json.dumps(inventory, indent=2) + '\n')
    (output / 'THIRD_PARTY_LICENSES.txt').write_text(notices)
    audit = run([args.cargo_audit, 'audit', '--db', str(args.advisory_db.resolve()), '--file', str(lock_path), '--json', '--deny', 'warnings'], cwd=repository, check=False)
    try:
        advisory = json.loads(audit.stdout)
    except ValueError:
        raise RuntimeError('RustSec audit did not return valid JSON; network/tool failure is not a pass') from None
    database = advisory.get('database', {})
    if not database.get('last-commit'):
        raise RuntimeError('RustSec audit lacks an advisory database revision')
    remote = run(['git', 'ls-remote', 'https://github.com/RustSec/advisory-db.git', 'HEAD']).stdout.split()[0]
    if database['last-commit'] != remote:
        raise RuntimeError('Advisory database differs from current upstream HEAD; retry fresh audit')
    vulnerabilities, warnings = sanitized_advisories(advisory)
    if advisory.get('settings', {}).get('ignore'):
        problems.append('Ignored RustSec advisories are not accepted by this release gate')
    if advisory.get('settings', {}).get('target_arch') or advisory.get('settings', {}).get('target_os'):
        problems.append('RustSec audit must inspect the complete unfiltered lockfile')
    if audit.returncode or vulnerabilities or any(warnings.values()):
        problems.append('RustSec vulnerabilities/warnings or audit failure require resolution')
    if digest(lock_path) != lock_sha:
        raise RuntimeError('Cargo.lock changed during dependency audit')
    report = {'schema': 1, 'audited_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'pass' if not problems else 'fail', 'lockfile_sha256': lock_sha,
              'scope': 'Linux amd64 metadata licenses/SBOM; RustSec scans complete lockfile; declared licenses are not full legal compliance proof',
              'rustsec_tool': run([args.cargo_audit, '--version']).stdout.strip(), 'rustsec_database': database,
              'rustsec_locked_dependency_count': advisory.get('lockfile', {}).get('dependency-count'), 'linux_metadata_component_count': len(inventory),
              'declared_license_counts': dict(Counter(item['license_expression'] or 'workspace LICENSE' for item in inventory)),
              'vulnerabilities': vulnerabilities, 'warning_counts': warnings, 'problems': problems,
              'limitations': ['First-party Cargo manifest omits license; repository README/LICENSE declare GPL-3.0.', 'Build/dev dependencies included; entries outside the Linux graph lack this metadata license inventory.', 'Cargo package checksums identify source archives, not compiled binary hashes.', 'Bundled C/assembly subcomponents are represented by enclosing crates and upstream notices.']}
    payload = json.dumps(report, indent=2) + '\n'
    for value in (payload, json.dumps(sbom), json.dumps(inventory), notices):
        if any(prefix in value for prefix in ('/home/huou07', '/Users/', '/tmp/h07p')):
            raise RuntimeError('A local path leaked into a distributable audit artifact')
    (output / 'report.json').write_text(payload)
    for name in ('sbom.cdx.json', 'licenses.json', 'THIRD_PARTY_LICENSES.txt', 'report.json'):
        (output / name).chmod(0o644)
    print(json.dumps({'status': report['status'], 'components': len(inventory), 'vulnerabilities': len(vulnerabilities), 'warnings': sum(warnings.values()), 'lockfile_sha256': lock_sha, 'database_commit': database['last-commit']}))
    if problems:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
        print('Release audit failed: ' + str(error), file=sys.stderr)
        sys.exit(2)
