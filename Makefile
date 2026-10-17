.PHONY: run check acceptance

# The Rust lanes need a writable target directory and a usable cargo cache, and
# the Python lanes need somewhere to write bytecode caches. The Hub verify gate may
# run as a worker that owns neither this checkout nor the ambient caches, so resolve
# all three with a real writability probe (tools/cargo-env.sh) and honour explicit
# CARGO_TARGET_DIR/CARGO_HOME/PYTHONPYCACHEPREFIX values when they are usable.
CARGO_HOME := $(shell sh tools/cargo-env.sh cargo-home)
CARGO_TARGET_DIR := $(shell sh tools/cargo-env.sh target-dir)
PYTHONPYCACHEPREFIX := $(shell sh tools/cargo-env.sh pycache-prefix)
export CARGO_HOME
export CARGO_TARGET_DIR
export PYTHONPYCACHEPREFIX

run:
	python3 web/app.py

check:
	python3 -m py_compile deploy/security/*.py tests/test_dsh_boundary.py
	sh -n tools/huou07-ssh-tunnel deploy/install.sh deploy/install-cockpit.sh deploy/install-cockpit-files.sh deploy/cockpit/huou07-move-files/move deploy/uninstall.sh deploy/configure-wg-private-web-access.sh deploy/remove-wg-private-web-access.sh deploy/configure-wg-udp-access.sh deploy/remove-wg-udp-access.sh deploy/install-opencode-launcher.sh deploy/install-user-apps.sh deploy/install-wg-easy.sh deploy/wg-easy-wait-ready.sh deploy/check-rootless-sandbox.sh deploy/install-codex-policy.sh deploy/check-codex-policy.sh
	python3 -m py_compile web/app.py web/private_services.py deploy/private_firewall.py deploy/dsh-dashboard-launcher.py deploy/check-user-app-health.py deploy/check-user-app-runtime.py deploy/admin/clean-playground-apps.py deploy/power.py deploy/gpu.py deploy/wg_status.py deploy/cockpit/huou07-move-files/list tests/test_app.py tests/test_clean_install.py tests/test_power.py tests/test_gpu.py tests/test_wg_status.py tests/test_file_list.py tests/test_file_move.py tests/test_ssh_tunnel.py tests/test_private_services.py tests/test_private_firewall.py
	python3 -m py_compile tests/package/test_lifecycle.py tests/package/test_setup.py
	python3 -m unittest discover -s tests -v
	cargo fmt --all -- --check
	cargo clippy --workspace --all-targets --locked -- -D warnings
	cargo test --workspace --locked

acceptance:
	npm run test:e2e
