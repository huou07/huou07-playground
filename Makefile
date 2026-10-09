.PHONY: run check
run:
	python3 web/app.py
check:
	sh -n deploy/install.sh deploy/install-cockpit.sh deploy/install-cockpit-files.sh deploy/uninstall.sh deploy/configure-wg-private-web-access.sh deploy/remove-wg-private-web-access.sh deploy/install-opencode-launcher.sh deploy/install-opencode-web.sh deploy/install-litellm.sh deploy/litellm-prepare.sh deploy/litellm-wait-postgres.sh deploy/install-omniroute.sh deploy/omniroute-prepare.sh deploy/omniroute-wait-ready.sh deploy/omniroute-wait-redis.sh deploy/install-wg-easy.sh deploy/wg-easy-wait-ready.sh deploy/check-opencode-web-sandbox.sh deploy/check-rootless-sandbox.sh deploy/install-codex-policy.sh deploy/check-codex-policy.sh
	bash -n deploy/opencode-bash-sandbox
	python3 -m py_compile web/app.py deploy/state.py deploy/power.py deploy/gpu.py deploy/wg_status.py tests/test_app.py tests/test_power.py tests/test_gpu.py tests/test_state.py tests/test_wg_status.py
	python3 -m unittest discover -s tests -v
