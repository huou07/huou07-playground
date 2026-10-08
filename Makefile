.PHONY: run check
run:
	python3 web/app.py
check:
	python3 -m py_compile web/app.py tests/test_app.py
	python3 -m unittest discover -s tests -v
