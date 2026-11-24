VENV   := .venv
PYTHON := $(VENV)/bin/python
export PYTHONPATH := src
# Spark needs a JVM. Use JAVA_HOME if it is set, otherwise the runtime bundled
# with the jdk4py wheel installed into the venv.
JAVA_HOME ?= $(shell $(PYTHON) -c "import jdk4py,sys; sys.stdout.write(str(jdk4py.JAVA_HOME))" 2>/dev/null)
export JAVA_HOME
export PATH := $(JAVA_HOME)/bin:$(PATH)

.PHONY: setup setup-dev data run test screenshots clean

setup:
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -q -r requirements.txt

# optional: only needed for `make screenshots`
setup-dev: setup
	$(PYTHON) -m pip install -q -r requirements-dev.txt

data:
	$(PYTHON) scripts/generate_data.py --customer plant_alpha --out data/raw/plant_alpha
	$(PYTHON) scripts/generate_data.py --customer plant_beta --out data/raw/plant_beta

run: data
	$(PYTHON) -m pipeline.run --config configs/plant_alpha.yaml
	$(PYTHON) -m pipeline.run --config configs/plant_beta.yaml
	$(PYTHON) -m pipeline.onboarding_diff configs/plant_alpha.yaml configs/plant_beta.yaml

test:
	$(PYTHON) -m pytest -q

# Needs the optional dev requirements (playwright) and a Chromium or Chrome binary.
screenshots:
	$(PYTHON) scripts/take_screenshots.py

clean:
	rm -rf data/raw output spark-warehouse
