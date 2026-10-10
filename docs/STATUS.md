# Deployment status

The application replacement is **prepared, not deployed**. On the Dell, the current `main` checkout completed `deploy/install-user-apps.sh prepare` with `READY`. Both native ACP initialize checks passed, and the fresh PostgreSQL/LiteLLM plus Redis/OmniRoute stacks passed temporary-port UI and persistence checks. The readiness marker records the prepared source revision.

The five legacy app units remain active, as do the dashboard, WireGuard, and Docker. The replacement services remain stopped. The user-level rollback action was exercised against inactive replacement units; it held their Quadlets, and the prepared files were restored. Temporary containers, pods, volumes, and the test-only hold were removed.

No final listener was replaced, no provider inference was sent, and no legacy data/account was deleted. Re-run `prepare` after any source update before switching. The owner must perform the switch and sign in to the browser UIs before deployment can be called verified.
