# Dependency and Debian package audit, 2026-10-16

This is scoped evidence for the dependency graph and inspected package candidate,
not publication approval or proof of the final deployed source revision. Product
state remains in ROADMAP. No production service was installed or restarted.

## Dependency identity and current advisories

- Cargo.lock SHA-256: `69878fef9f60f4a2f4e0b5d123475d21b23e07a6dba0004d43abe5dc691087b7`.
- cargo-audit 0.22.2, built separately with its own locked dependencies.
- Fresh RustSec database: [`edb58f5974b83eb8302332821cb6d389777aa351`](https://github.com/RustSec/advisory-db/commit/edb58f5974b83eb8302332821cb6d389777aa351),
  updated 2026-10-14, 1,329 advisories. An independent upstream HEAD lookup matched.
- Complete lockfile scan: **169 dependencies, zero reported vulnerabilities,
  zero warnings, no advisory ignores and no target filtering**. `--deny warnings`
  was enabled. Network/tool failures produce an incomplete gate, never a pass.

[Cargo's metadata interface](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html)
and [cargo-audit](https://github.com/rustsec/rustsec/blob/main/cargo-audit/README.md)
are the primary tool references. This detects known published RustSec advisories;
it does not establish absence of unknown vulnerabilities or audit operating-system
packages and external native harness installations.

## License inventory and SBOM

The Linux amd64 metadata graph has 144 components: one workspace package and
143 third-party crates. All 143 declare licenses and have collected upstream
license/notice documents. Normalized expressions contain MIT, Apache-2.0, ISC,
BSD-3-Clause, Zlib, Unicode-3.0, Unlicense, BSL-1.0 and
CDLA-Permissive-2.0; some expressions require multiple licenses. No declared
third-party copyleft expression appeared in this graph.

The first-party Cargo manifest omits its license field. Existing README/LICENSE
declare GPL-3.0; the SBOM records that provenance as a named license instead of
inventing a precise SPDX `only`/`or-later` choice. That metadata omission remains
visible. The existing Google Noto turtle Apache-2.0 attribution is retained.
This manifest/text inventory is not a complete legal compatibility opinion.

`tools/release-audit.py` produces CycloneDX 1.6 JSON, a license inventory, collected
public upstream notices and a sanitized advisory report. The generated SBOM
validated against the [official CycloneDX 1.6 schema](https://github.com/CycloneDX/specification/tree/1.6/schema),
including its SPDX and JSF schemas. It contains public crate purls, source archive
SHA-256 checksums and graph edges; it excludes absolute checkout/cache/home paths.
Build/dev components are included. Lock entries outside the Linux metadata graph
have advisory coverage but are outside this license inventory. Bundled C/assembly
code is represented by enclosing crates and their upstream notices, not separate
binary components.

The inspected SBOM SHA-256 is
`51e30e727e0535e60a830e2a59228f2c9d451e560ead29e927111ed06f220313`.
Generated artifacts are ignored under `artifacts/release-audit/`; they must be
regenerated and retained with the final release artifact. Crate checksums do not
identify a compiled executable.

## Package gate and repairs

Lintian 2.122.0 ran from downloaded/extracted packages in an isolated temporary
tree. No audit-tool package was installed into the running OS. The inspected
`huou07-playground_0.2.0_amd64.deb` passes with no errors or warnings using no user
configuration. One narrowly scoped packaged override covers the explicitly
required versioned `/opt/huou07-playground` layout; this is an owner-distributed
application package, not a claim of Debian archive policy compliance.

Concrete findings were repaired: Python-dependent postrm, absent copyright and
changelog, unstripped ELF, invalid local-only maintainer address, permissive
umask-created metadata modes and macOS AppleDouble files copied into static
assets. postrm is now essential-tool shell and restores original worker entry
points without requiring Python. Other maintainer phases use shell wrappers and
the declared Python pre-dependency. Bundled upstream notices and the SBOM are
installed with documentation. Real package builds require a passing audit report
whose lockfile hash matches the checkout; synthetic package fixtures opt out
explicitly.

Inspected candidate SHA-256:
`d0e4af5c089f5bfa3c69241ec3a961f257d145005f83857724d1961254150981`.
This identifies the candidate that was linted, not a later rebuilt release.

The updated isolated dpkg gate passed repeat-build byte equality, install,
upgrade, intentionally invalid postinst and automatic rollback, repeated manual
rollback, removal with Python absent from PATH, purge preserving subsequent
owner configuration, and fresh reinstall/removal preserving the newer original
worker configuration. Synthetic apps/policy/NAS hashes remained unchanged.
Six package boundary tests also passed. The fixture uses `dpkg --root` and a
harmless ELF with forced dependency resolution; it does not prove full real-server
installation, apt dependency resolution or health-failure behavior in a fresh VM.
