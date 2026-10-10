.PHONY: run check acceptance

run:
	python3 web/app.py

check:
	sh -n tools/huou07-ssh-tunnel deploy/install.sh deploy/install-cockpit.sh deploy/install-cockpit-files.sh deploy/cockpit/huou07-move-files/move deploy/uninstall.sh deploy/configure-wg-private-web-access.sh deploy/remove-wg-private-web-access.sh deploy/configure-wg-udp-access.sh deploy/remove-wg-udp-access.sh deploy/install-opencode-launcher.sh deploy/install-user-apps.sh deploy/install-wg-easy.sh deploy/wg-easy-wait-ready.sh deploy/check-rootless-sandbox.sh deploy/install-codex-policy.sh deploy/check-codex-policy.sh
	python3 -m py_compile web/app.py web/private_services.py deploy/private_firewall.py deploy/dsh-dashboard-launcher.py deploy/check-user-app-health.py deploy/check-user-app-runtime.py deploy/admin/clean-playground-apps.py deploy/power.py deploy/gpu.py deploy/wg_status.py deploy/cockpit/huou07-move-files/list tests/test_app.py tests/test_clean_install.py tests/test_power.py tests/test_gpu.py tests/test_wg_status.py tests/test_file_list.py tests/test_file_move.py tests/test_ssh_tunnel.py tests/test_private_services.py tests/test_private_firewall.py
	python3 -m unittest discover -s tests -v

acceptance:
	npm run test:e2e
