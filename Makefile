PYTHON ?= python

.PHONY: install test demo evaluate
install:
	$(PYTHON) -m pip install -e .
test:
	$(PYTHON) -m unittest discover -s checks -v
demo:
	$(PYTHON) -m agent_regression demo --output results/demo.json
evaluate:
	$(PYTHON) -m agent_regression evaluate --output results/evaluation.json
