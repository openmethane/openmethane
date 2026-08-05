# Open Methane

Open Methane is a system for estimating methane emissions over a large area
without needing direct measurement.

It uses a system called atmospheric inversion, which produces monthly gridded
methane emissions estimates. The inversion works by producing initial bottom-up
emission estimates (the prior), simulating the atmosphere and meteorology, and
comparing the resulting concentrations with actual atmospheric observations
satellites. The inversion corrects the initial estimates iteratively until it
finds emissions which produce similar atmospheric methane to the observations.

This repository holds the inversion itself: it converts weather model output into
inputs for the CMAQ atmospheric chemistry model, processes TROPOMI satellite
observations, and runs a 4D-Var data assimilation using the CMAQ adjoint model to
produce posterior emissions estimates.

Open Methane is built for Australia, but can be extended to work in any region.
Results are published at [openmethane.org](https://openmethane.org).

## Getting started

The fastest way to see it work is the
**[Quickstart](docs/guides/quickstart.md)** — a complete run on a small test
domain using public Docker images. No compilation, no private repositories.

Then, depending on what you need:

| I want to… | Start here |
| --- | --- |
| Understand how the pipeline fits together | [Overview](docs/overview.md) |
| Estimate emissions for my own area and time period | [Running your own domain](docs/guides/running-a-domain.md) |
| Model an area no existing domain covers | [Creating a custom domain](docs/guides/custom-domain.md) |
| Run without Docker, on a Linux machine | [Installing locally](docs/guides/local-install.md) |
| Change the code | [Development](docs/guides/development.md) |
| Look up a setting, script or output file | [Reference](docs/README.md#reference) |
| Work out why a run failed | [Troubleshooting](docs/troubleshooting.md) |

Full documentation index: **[docs/](docs/README.md)**

## Related repositories

Running the full pipeline needs two companion repositories, each of which also
publishes a public Docker image:

- [openmethane-prior](https://github.com/openmethane/openmethane-prior) — builds
  the initial (prior) emissions estimate from inventories and land-use data.
- [setup-wrf](https://github.com/openmethane/setup-wrf) — runs the WRF weather
  model to produce the meteorology that drives atmospheric transport, and holds
  the domain definitions.

The CMAQ adjoint model is built in
[CMAQ-Adjoint](https://github.com/openmethane/CMAQ-Adjoint) and bundled into this
repository's Docker image.

> [!NOTE]
> The CMAQ-Adjoint repository and its container image are not public, so the
> `openmethane` image cannot be built from source without access. The published
> images are public and require no credentials. If this affects you, please
> create an issue or contact us at inquiries@openmethane.org.

## Contributing

Bug reports and pull requests are welcome. See
[Development](docs/guides/development.md) for how to set up, run the tests, and
add a changelog entry.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
