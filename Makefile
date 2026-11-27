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

.PHONY: fetch-domains
## Fetch the WRF geometry and Open Methane domain files
fetch-domains: data/domains/aust10km/v1/geo_em.d01.nc data/domains/aust10km/v1/domain.aust10km.nc data/domains/au-test/v1/geo_em.d01.nc data/domains/au-test/v1/domain.au-test.nc

.PHONY: test
test:  ## Run the tests. The WRF test downloads 3.4 GB of FNL analyses into data/fnl the first time
	$(PYTHON_CMD) -m pytest -r a -v $(TEST_DIRS)

.PHONY: test-regen
test-regen:  ## Regenerate the expected test data
	$(PYTHON_CMD) -m pytest -r a -v $(TEST_DIRS) --ignore=tests/integration/obs_preprocess --ignore=tests/integration/workflows -m "not wrf" --force-regen

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
		-v ~/.cdsapirc:/home/app/.cdsapirc \
		openmethane \
		make test

## Fetch the domain files and CAMS data required for tests
.PHONY: fetch-test-data
fetch-test-data: data/domains/au-test/v1/geo_em.d01.nc data/domains/au-test/v1/domain.au-test.nc data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc

data/domains/aust10km/v1/geo_em.d01.nc:
	mkdir -p data/domains/aust10km/v1
	curl -fL https://openmethane.s3.amazonaws.com/domains/aust10km/v1/geo_em.d01.nc \
		-o data/domains/aust10km/v1/geo_em.d01.nc.part
	mv data/domains/aust10km/v1/geo_em.d01.nc.part data/domains/aust10km/v1/geo_em.d01.nc

data/domains/au-test/v1/geo_em.d01.nc:
	mkdir -p data/domains/au-test/v1
	curl -fL https://openmethane.s3.amazonaws.com/domains/au-test/v1/geo_em.d01.nc \
		-o data/domains/au-test/v1/geo_em.d01.nc.part
	mv data/domains/au-test/v1/geo_em.d01.nc.part data/domains/au-test/v1/geo_em.d01.nc

data/domains/aust10km/v1/domain.aust10km.nc:
	mkdir -p data/domains/aust10km/v1
	curl -fL https://openmethane.s3.amazonaws.com/domains/aust10km/v1/domain.aust10km.nc \
		-o data/domains/aust10km/v1/domain.aust10km.nc.part
	mv data/domains/aust10km/v1/domain.aust10km.nc.part data/domains/aust10km/v1/domain.aust10km.nc

data/domains/au-test/v1/domain.au-test.nc:
	mkdir -p data/domains/au-test/v1
	curl -fL https://openmethane.s3.amazonaws.com/domains/au-test/v1/domain.au-test.nc \
		-o data/domains/au-test/v1/domain.au-test.nc.part
	mv data/domains/au-test/v1/domain.au-test.nc.part data/domains/au-test/v1/domain.au-test.nc

data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc:
	mkdir -p data/cams
	curl -fL https://openmethane.s3.amazonaws.com/tests/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc \
		-o data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc.part
	mv data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc.part data/cams/cams_eac4_methane_2022-12-07-2022-12-07.nc
