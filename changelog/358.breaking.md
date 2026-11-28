Removed the `docker-test` configuration target (`.env.docker-test`) and `make fetch-test-data`.

- `.env.docker-test` pointed at test data tracked in the repository, so a step could run locally without a previous run. That data is now downloaded by the tests, and there is no replacement target: to run a step locally, use the `docker` or `docker-monthly` target and set `STORE_PATH`, the dates and the domain, with the outputs of the earlier steps under `STORE_PATH`.
- The tests fetch the domain files they need themselves, so nothing needs fetching before running them. `make fetch-domains` still downloads the domain files into `data/domains/`.

Note: `make docker-test`, which runs the tests in the image, is unchanged.
