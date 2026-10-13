# Offline checks for the Connected Care Data Platform. `make check` runs everything CI runs.
PYTHON ?= python3
BRIDGE_RECONCILER := analytics/batches/hl7-portal-refresh-20261007T183326824850Z/reconcile_bridge.py

.PHONY: check lint test reconcile reproduce

check: lint test reconcile reproduce

lint:
	$(PYTHON) -m black --check .
	$(PYTHON) -m pyflakes $$(git ls-files '*.py' | grep -v '^archive/')

test:
	cd analytics && $(PYTHON) -B -m unittest test_export test_reconcile
	cd worklist && $(PYTHON) -B -m unittest test_demo_check test_viewer_auth
	cd worklist && $(PYTHON) -B test_worklist.py
	$(PYTHON) -B converters/appointment_bridge.py --self-test

# Re-check every downloaded Snowflake load against the exported batch it came from.
reconcile:
	$(PYTHON) -B analytics/reconcile_csv.py analytics/batches/synthetic-20261004T225801Z-5dd08717 \
		results/2026-10-05-internal-stage/internal-raw-first-20261005.csv --evidence $$(mktemp)
	$(PYTHON) -B $(BRIDGE_RECONCILER) analytics/batches/hl7-bridge-20261007T160123921786Z \
		results/2026-10-07-hl7-bridge/raw-download-hl7-bridge.csv
	$(PYTHON) -B $(BRIDGE_RECONCILER) analytics/batches/hl7-appointment-bridge-20261007T162957465413Z \
		results/2026-10-07-hl7-bridge/raw-download-appointment-bridge.csv
	$(PYTHON) -B $(BRIDGE_RECONCILER) analytics/batches/hl7-portal-refresh-20261007T183326824850Z \
		results/2026-10-07-portal-refresh/raw-download.csv
	$(PYTHON) -B analytics/compare_fc30_outcomes.py

# The converters and the dataset generator must reproduce the committed artifacts byte for byte.
reproduce:
	for message in lab-002 lab-003 lab-portal-update-004; do \
		$(PYTHON) -B converters/convert_lab.py samples/$$message.hl7 > /dev/null || exit 1; \
	done
	cd datasets/fc30-failure-cases && $(PYTHON) -B generate_dataset.py > /dev/null
	git diff --exit-code -- samples datasets
