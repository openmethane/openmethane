ifneq (, $(shell command -v poetry))
	RUN_CMD := poetry run
	PYTHON_CMD := poetry run python
else
	RUN_CMD :=
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
	# Requires local clones of setup-wrf and openmethane-prior
	docker run --rm -it \
		-v $(PWD):/opt/project \
		-v $(PWD)/../results:/opt/project/data \
		-v ~/.cdsapirc:/root/.cdsapirc \
		openmethane

.PHONY: run
run: build clean fetch-domains  ## Run the test domain in the docker container using the bundled test-data
	# This requires a valid `~/.cdsapirc` file
	docker run --rm -it \
		-v $(PWD):/opt/project \
		-v $(PWD)/../results:/opt/project/data \
		-v ~/.cdsapirc:/root/.cdsapirc \
		openmethane \
		bash scripts/run-all.sh

.PHONY: fetch-domains
## Fetch the latest WRF geometry domain data from setup-wrf
fetch-domains: data/domains/aust10km/v1/geo_em.d01.nc data/domains/au-test/v1/geo_em.d01.nc data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc

.PHONY: sync-domains-from-cf
sync-domains-from-cf:  ## Download all domain data from the Cloudflare bucket
	# This requires CloudFlare credentials
	aws s3 sync s3://openmethane-prior/domains data/domains \
		  --endpoint-url https://8f8a25e8db38811ac9f26a347158f296.r2.cloudflarestorage.com \
		  --profile cf-om-prior-r2

.PHONY: test
test:  ## Run the tests
	TARGET=docker-test $(PYTHON_CMD) -m pytest -r a -v $(TEST_DIRS) --ignore=tests/integration/fourdvar

.PHONY: test-regen
test-regen:  ## Regenerate the expected test data
	TARGET=docker-test $(PYTHON_CMD) -m pytest -r a -v $(TEST_DIRS) --ignore=tests/integration/fourdvar --ignore=tests/integration/obs_preprocess --force-regen

# Processing steps
.PHONY: prepare-templates
prepare-templates:  ## Prepare the template files for a CMAQ run
	$(PYTHON_CMD) scripts/cmaq_preprocess/make_emis_template.py
	$(PYTHON_CMD) scripts/cmaq_preprocess/make_template.py
	$(PYTHON_CMD) scripts/cmaq_preprocess/make_prior.py

.PHONY: changelog-draft
changelog-draft:  ## compile a draft of the next changelog
	$(RUN_CMD) towncrier build --draft

.PHONY: docker-test
docker-test: build fetch-test-data ## Run the tests
	docker run --rm -it \
		-v $(PWD):/opt/project \
		-v ~/.cdsapirc:/root/.cdsapirc \
		openmethane \
		make test

## Fetch the latest WRF geometry domain data and CAMS data required for tests
.PHONY: fetch-test-data
fetch-test-data: data/domains/aust10km/v1/geo_em.d01.nc data/domains/au-test/v1/geo_em.d01.nc data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc

data/domains/aust10km/v1/geo_em.d01.nc:
	mkdir -p data/domains/aust10km/v1
	curl -L https://github.com/openmethane/setup-wrf/raw/main/domains/aust10km/geo_em.d01.nc -o data/domains/aust10km/v1/geo_em.d01.nc

data/domains/au-test/v1/geo_em.d01.nc:
	mkdir -p data/domains/au-test/v1
	curl -L https://github.com/openmethane/setup-wrf/raw/main/domains/au-test/geo_em.d01.nc -o data/domains/au-test/v1/geo_em.d01.nc

data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc:
	mkdir -p data/cams
	$(PYTHON_CMD) scripts/cmaq_preprocess/download_cams_input.py \
		-s 2022-12-07 -e 2022-12-07 \
		data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc
