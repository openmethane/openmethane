Removed the `docker-test` target and `make fetch-test-data`.

- `.env.docker-test` pointed at test data that is now downloaded by the tests instead. To run a step locally, use the `docker` or `docker-monthly` target and set `STORE_PATH`, the dates and the domain, as in [Inspecting the resolved configuration](https://github.com/openmethane/openmethane/blob/main/docs/reference/configuration.md#inspecting-the-resolved-configuration).
- The tests fetch the domain files they need themselves, so nothing needs fetching before running them. `make fetch-domains` still downloads the domain files into `data/domains/`.
