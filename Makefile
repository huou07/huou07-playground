.PHONY: run check acceptance
run:
	python3 web/app.py
check:
	sh -n tools/huou07-ssh-tunnel deploy/install.sh deploy/install-cockpit.sh deploy/install-cockpit-files.sh deploy/cockpit/huou07-move-files/move deploy/uninstall.sh deploy/configure-wg-private-web-access.sh deploy/remove-wg-private-web-access.sh deploy/configure-wg-udp-access.sh deploy/remove-wg-udp-access.sh deploy/install-opencode-launcher.sh deploy/install-opencode-web.sh deploy/install-litellm.sh deploy/litellm-prepare.sh deploy/litellm-wait-postgres.sh deploy/install-omniroute.sh deploy/omniroute-prepare.sh deploy/omniroute-wait-ready.sh deploy/omniroute-wait-redis.sh deploy/install-wg-easy.sh deploy/wg-easy-wait-ready.sh deploy/check-opencode-web-sandbox.sh deploy/check-rootless-sandbox.sh deploy/install-codex-policy.sh deploy/check-codex-policy.sh deploy/check-litellm-mock-routing.sh deploy/install-dsh.sh deploy/inspect-one-user-migration.sh
	bash -n deploy/opencode-bash-sandbox
	python3 -m py_compile web/app.py web/private_services.py deploy/private_firewall.py deploy/dsh-launcher.py deploy/user/dsh-launcher.py deploy/state.py deploy/power.py deploy/gpu.py deploy/wg_status.py deploy/patch_dsh_workspace_policy.py deploy/patch_dsh_directory_picker.py deploy/cockpit/huou07-move-files/list tests/test_app.py tests/test_dsh_launcher.py tests/test_dsh_user_launcher.py tests/test_user_units.py tests/test_dsh_policy_patch.py tests/test_dsh_directory_picker_patch.py tests/test_power.py tests/test_gpu.py tests/test_state.py tests/test_wg_status.py tests/test_file_list.py tests/test_file_move.py tests/test_ssh_tunnel.py tests/test_private_services.py tests/test_private_firewall.py
	python3 -m unittest discover -s tests -v

acceptance:
	npm run test:e2e
