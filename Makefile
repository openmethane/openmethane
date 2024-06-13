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


.PHONY: test
test:  ## Run the tests
	poetry run python -m pytest -r a -v tests/unit tests/integration/cmaq_preprocess

.PHONY: test-regen
test-regen:  ## Regenerate the expected test data
	poetry run python -m pytest -r a -v tests/unit tests/integration/cmaq_preprocess --force-regen