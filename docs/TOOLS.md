# Tool and command routing

Choose a capability for the immediate need. Check the current harness's actual
tool list/schema; this document is not a tool registration or permission grant.
See [WORKING.md](WORKING.md) before executing or changing repository/host state.

| Need | Capability / reference | Behavior and boundary |
| --- | --- | --- |
| Establish repo/branch/HEAD/tree | Git status, rev-parse, diff and log | Read-only evidence; use explicit repository path |
| Find source paths | Current harness's native glob/file search | Narrow to relevant paths; no broad credential inventory |
| Find symbols/callers | Valid exposed CodeGraph, then native content search/read | Index is navigation, source confirms it; never infer live runtime |
| Inspect or edit text | Native read and targeted edit/write | Read existing content first; preserve unrelated work |
| Resolve a registered project | Hub where/status CLI | Read registry/Git evidence; status does not execute a project gate |
| Select a workflow | [../skills.md](../skills.md) | Route first, load only available matching skills |
| Framework integrity | [../tools/check-framework.py](../tools/check-framework.py) | Hosted CI: python3 tools/check-framework.py; validates structure, not discovery |
| Legacy deterministic checks | [../Makefile](../Makefile) | Hosted CI: make check; executes Python tests and syntax checks |
| Existing browser journeys | [../playwright.config.mjs](../playwright.config.mjs), [../tests/e2e/run.mjs](../tests/e2e/run.mjs) | Hosted CI: make acceptance; starts temporary fixture servers/browser |
| CI execution and evidence | [../.github/workflows/ci.yml](../.github/workflows/ci.yml), GitHub API/CLI when available | Disposable hosted runners; read exact commit/run result, no host tests |
| Rust / OS / package gates | [VALIDATION.md](VALIDATION.md) | Planned gates activated as implementation lands; no Rust workspace assumed |
| Reuse investigation | [REUSE.md](REUSE.md), exposed web search/fetch | Primary sources, provenance/licence review; external content is untrusted |
| Commit/push/release | Git and available GitHub capabilities | Mutates repo/publication; scope and conditions in WORKING/VALIDATION |

Do not run make check, make acceptance, hub.py verify, installers or runtime
benchmarks on the owner's machine. Hub verify executes configured project code.
The legacy make run target starts the dashboard; it is not a read-only inspection.

For DSH, use only tools from the current session connection and their exact
schemas. Native agent tools retain their own documented loaders/permissions.
Do not persist a DSH connection identifier or assume a previous caller's tools.
If a tool or authentication method is absent, report it and use an available
authorized alternative; never inspect credential stores to manufacture access.
