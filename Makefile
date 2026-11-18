PYTHON ?= python3

.PHONY: verify figures
verify:
	$(PYTHON) scripts/check_reference.py
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -O -m unittest discover -s tests -v
	$(PYTHON) scripts/check_evidence.py
	$(PYTHON) scripts/collect_board_results.py
	$(PYTHON) scripts/check_release.py deploy/B11_20261118T204214272606Z_audit3.zip deploy/K44_20261118T205854106482Z_audit3.zip
	$(PYTHON) scripts/check_report.py

figures:
	$(PYTHON) scripts/plot_results.py
	$(PYTHON) scripts/plot_board_results.py
