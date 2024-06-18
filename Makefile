ifneq (, $(shell which poetry))
	PYTHON_CMD := poetry run python
else
	PYTHON_CMD := python
endif


TEST_DIRS := tests

.PHONY: virtual-environment
virtual-environment:  ## update virtual environment, create a new one if it doesn't already exist
	poetry lock --no-update
	# Put virtual environments in the project
	poetry config virtualenvs.in-project true
	poetry install --all-extras
	# TODO: Add last line back in when pre-commit is set up
	# poetry run pre-commit install

.PHONY: ruff-fixes
ruff-fixes:  # Run ruff on the project
 	# Run the formatting first to ensure that is applied even if the checks fail
	poetry run ruff format .
	poetry run ruff check --fix .
	poetry run ruff format .

.PHONY: clean
clean:  ## remove generated temporary files
	find data ! -path "data/tropomi*" -delete

.PHONY: build
build:  ## Build the docker container locally
	docker build --platform=linux/amd64 -t openmethane .

.PHONY: start
start: build  ## Start the docker container locally
	# Requires local clones of setup_wrf and openmethane-prior
	docker run --rm -it \
		-v $(PWD):/opt/project \
		-v $(PWD)/../setup_wrf:/opt/openmethane/setup_wrf \
		-v $(PWD)/../openmethane-prior:/opt/openmethane/openmethane-prior \
		openmethane

.PHONY: run
run: build clean  ## Run the test domain in the docker container using the bundled test-data
	docker run --rm -it \
		-v $(PWD):/opt/project \
		-e TARGET=docker-test \
		openmethane \
		bash scripts/run-all.sh

.PHONY: test
test:  ## Run the tests
	$(PYTHON_CMD) -m pytest -r a -v $(TEST_DIRS)

.PHONY: test-regen
test-regen:  ## Regenerate the expected test data
	$(PYTHON_CMD) -m pytest -r a -v $(TEST_DIRS)  --force-regen

# Processing steps
.PHONY: prepare-templates
prepare-templates:  ## Prepare the template files for a CMAQ run
	$(PYTHON_CMD) scripts/cmaq_preprocess/make_emis_template.py
	$(PYTHON_CMD) scripts/cmaq_preprocess/make_template.py
	$(PYTHON_CMD) scripts/cmaq_preprocess/make_prior.py