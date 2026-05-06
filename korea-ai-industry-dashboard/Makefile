PYTHON ?= python

.PHONY: inventory consolidate build-gold workbook data-clean all collect dashboard legacy-workbook

inventory:
	$(PYTHON) scripts/inventory_data_files.py

consolidate:
	$(PYTHON) scripts/consolidate_data.py

build-gold:
	$(PYTHON) scripts/build_gold.py

workbook:
	$(PYTHON) scripts/create_consolidated_workbook.py

data-clean: inventory consolidate build-gold workbook

all: data-clean

collect:
	$(PYTHON) scripts/collect_data.py

legacy-workbook:
	$(PYTHON) scripts/create_indicator_workbook.py

dashboard:
	streamlit run app/Home.py
