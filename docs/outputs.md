
# Open Methane Outputs

The Open Methane workflows each produce a small number of key outputs which
are published in the public Open Methane Data Store.

## Alerts

Methane alerts are produced for each calendar day, and represent grid cells
in which the observed concentration of methane is significantly different than
the simulated concentration.

This is produced by `scripts/alerts/create_alerts.py`, and outputs a NetCDF
file (`alerts.nc` by default), which includes:

### `alerts`

A boolean field with a `1` value for any cells in which a methane anomaly was
detected. A `NaN` value represents a cell where not enough data was available
to achieve a result.

### `obs_enhancement`

The difference, in ppb, between nearby observations (the "near field") and far
away observations (the "far field"). The distances which determine inclusion in
the near and far fields are available in the `alerts_near_threshold` and
`alerts_far_threshold` global attributes.

# Emissions

TBC