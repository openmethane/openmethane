ifneq (, $(shell command -v uv))
	RUN_CMD := uv run
	PYTHON_CMD := uv run python
else
	RUN_CMD :=
	PYTHON_CMD := python
endif

TEST_DIRS := tests

.PHONY: install
install:  ## create virtual env and fetch project dependencies
	uv sync

.PHONY: format
format:  ## format project source files according to ruff config
	uv format

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
		-v $(PWD):/app \
		-v /app/.venv \
		-v $(PWD)/../results:/app/data \
		-v ~/.cdsapirc:/root/.cdsapirc \
		openmethane

.PHONY: run
run: build clean fetch-domains  ## Run the test domain in the docker container using the bundled test-data
	# This requires a valid `~/.cdsapirc` file
	docker run --rm -it \
		-v $(PWD):app \
		-v app/.venv \
		-v $(PWD)/../results:app/data \
		-v ~/.cdsapirc:/root/.cdsapirc \
		openmethane \
		bash scripts/run-all.sh

.PHONY: fetch-domains
## Fetch the WRF geometry and Open Methane domain files
fetch-domains: data/domains/aust10km/v1/geo_em.d01.nc data/domains/aust10km/v1/domain.aust10km.nc data/domains/au-test/v1/geo_em.d01.nc data/domains/au-test/v1/domain.au-test.nc

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
	uv run towncrier build --draft

.PHONY: docker-test
docker-test: build fetch-test-data ## Run the tests
	docker run --rm -it \
		-v $(PWD):/app \
		-v /app/.venv \
		-v ~/.cdsapirc:/root/.cdsapirc \
		openmethane \
		make test

## Fetch the domain files and CAMS data required for tests
.PHONY: fetch-test-data
fetch-test-data: data/domains/au-test/v1/geo_em.d01.nc data/domains/au-test/v1/domain.au-test.nc data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc

data/domains/aust10km/v1/geo_em.d01.nc:
	mkdir -p data/domains/aust10km/v1
	curl -L https://github.com/openmethane/setup-wrf/raw/main/domains/aust10km/geo_em.d01.nc \
		-o data/domains/aust10km/v1/geo_em.d01.nc

data/domains/au-test/v1/geo_em.d01.nc:
	mkdir -p data/domains/au-test/v1
	curl -L https://github.com/openmethane/setup-wrf/raw/main/domains/au-test/geo_em.d01.nc \
		-o data/domains/au-test/v1/geo_em.d01.nc

data/domains/aust10km/v1/domain.aust10km.nc:
	mkdir -p data/domains/aust10km/v1
	curl -L https://openmethane.s3.amazonaws.com/domains/aust10km/v1/domain.aust10km.nc \
		-o data/domains/aust10km/v1/domain.aust10km.nc

data/domains/au-test/v1/domain.au-test.nc:
	mkdir -p data/domains/au-test/v1
	curl -L https://openmethane.s3.amazonaws.com/domains/au-test/v1/domain.au-test.nc \
		-o data/domains/au-test/v1/domain.au-test.nc

data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc:
	mkdir -p data/cams
	curl -L https://openmethane.s3.amazonaws.com/tests/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc \
		-o data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc
