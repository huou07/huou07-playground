.PHONY: run check
run:
	python3 web/app.py
check:
	sh -n deploy/install.sh deploy/install-cockpit.sh deploy/uninstall.sh deploy/check-rootless-sandbox.sh
	python3 -m py_compile web/app.py deploy/state.py deploy/power.py tests/test_app.py tests/test_power.py tests/test_state.py
	python3 -m unittest discover -s tests -v
