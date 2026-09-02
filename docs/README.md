# Open Methane documentation

Open Methane estimates gridded methane emissions by comparing satellite
observations of atmospheric methane against a simulation of what the atmosphere
*should* look like given an initial emissions estimate, then correcting the
emissions to reduce the difference.

If you are new here, read [Overview](overview.md) first — it explains the
moving parts and which repository does what.

## Guides

Task-oriented walkthroughs, roughly in the order you are likely to need them.

| Guide | Use it when |
| --- | --- |
| [Quickstart](guides/quickstart.md) | You want to see a complete run finish on a small test domain, using public Docker images. Start here. |
| [Running your own domain](guides/running-a-domain.md) | You have an area and a time period you care about and want emissions estimates for it. |
| [Creating a custom domain](guides/custom-domain.md) | Your area of interest isn't covered by an existing domain, so you need to define a new grid. |
| [Installing locally](guides/local-install.md) | You want to run Open Methane on a Linux machine without Docker. |
| [Development](guides/development.md) | You want to change the code, run the tests, or cut a release. |

## Reference

Look-up material, not meant to be read end to end.

| Reference | Contents |
| --- | --- |
| [Configuration](reference/configuration.md) | How configuration is loaded: targets, `.env` files, precedence, credentials. |
| [Parameters](reference/parameters.md) | Every environment variable, its type and default. |
| [Scripts](reference/scripts.md) | What each script in `scripts/` does and what it expects. |
| [CMAQ preprocessing](reference/cmaq-preprocess.md) | The MCIP/ICON/BCON/template stage in detail. |
| [TROPOMI data](reference/tropomi.md) | Where the satellite observations come from, which products are used, and how far back they go. |
| [Outputs](reference/outputs.md) | The files a run produces and what the variables mean. |
| [Architecture](reference/architecture.md) | Internals of the 4D-Var inversion: data types and the transform chain. |

## Other

- [Troubleshooting](troubleshooting.md) — common failures, logging, and how to
  inspect a run that went wrong.
- [Changelog](changelog.md) — release history.
- [Methodology](methodology/) — background notes on the scientific method,
  written for a general audience.
- [Running on NCI/Gadi](../examples/nci/README.md) — unsupported, kept for
  reference for anyone running on an HPC system.