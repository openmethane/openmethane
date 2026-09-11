# Architecture

This page describes the internals of the 4D-Var inversion in
`src/openmethane/fourdvar/`. You need it to change how the inversion works, or
to interpret an error raised deep in the transform chain. You do not need it to
run Open Methane.

For the pipeline as a whole, see [Overview](../overview.md).

## The problem being solved

The inversion minimises a cost function over emissions `x`:

```
J(x) = ½ (x - x_b)ᵀ B⁻¹ (x - x_b)  +  ½ (H(x) - y)ᵀ R⁻¹ (H(x) - y)
```

The first term penalises departure from the prior `x_b`, weighted by the prior
error covariance `B`. The second penalises mismatch against observations `y`,
weighted by observation error covariance `R`. `H` is the observation operator:
run the atmospheric model forwards, then sample it the way the satellite samples
the atmosphere.

In the code the background term appears as a plain sum of squares:

```python
bg_cost = 0.5 * np.sum((un_vector - bg_vector) ** 2)
```

because `B⁻¹` has already been absorbed into the change of variables — the
optimiser works in coordinates where the prior covariance is the identity. That
is the whole purpose of the `condition` transform described below, and it is why
those coordinates are called "unknown" rather than "emissions". The observation
term keeps its weighting explicit, as `½ · residual · (R⁻¹ residual)`.

Minimising this needs `∇J(x)`, and `H` is a full chemical transport model — far
too expensive to differentiate by perturbing inputs one at a time. That is what
the **adjoint** provides: one backward run yields the gradient with respect to
every emission cell at once. This is why the CMAQ adjoint is a hard dependency
rather than an optimisation.

## Data types

Each stage of the calculation has a class in `fourdvar/datadef/`. They exist so
that transitions between representations are explicit and type-checked, rather
than arrays of ambiguous meaning being passed around.

| Class | Represents |
| --- | --- |
| `PhysicalData` | Emissions in physical units on the model grid. What the prior provides and the posterior reports. |
| `UnknownData` | The same information in the optimiser's coordinates — dimensionless, scaled so the optimiser sees a well-conditioned problem. |
| `ModelInputData` | CMAQ input files on disk, ready for a forward run. |
| `ModelOutputData` | CMAQ concentration output from a forward run. |
| `ObservationData` | Observations, or simulated observations, in the satellite's sampling geometry. |
| `AdjointForcingData` | The observation-space residual converted into forcing for the adjoint model. |
| `SensitivityData` | Raw adjoint output: sensitivity of the cost function to model inputs. |
| `PhysicalAdjointData` | That sensitivity mapped back onto the physical emissions grid. |

Note the symmetry: the forward path descends from physical emissions to
observations, and the adjoint path climbs back up. Each rung has a type on the
way down and a corresponding type on the way up.

## The transform chain

Conversions live in `fourdvar/transfunc/`, and `fourdvar/_transform.py` maps each
`(input class, output class)` pair to the function implementing it:

```python
transform(model_input, datadef.ModelOutputData)
```

`transform` looks the pair up in `transmap` and dispatches. There is no
inheritance or registration magic — the table in `_transform.py` is the complete
list of legal transitions.

**Forward path**, from emissions to simulated observations:

| Transform | From → To | Function |
| --- | --- | --- |
| `uncondition` | `UnknownData` → `PhysicalData` | Convert optimiser coordinates back to physical units |
| `prepare_model` | `PhysicalData` → `ModelInputData` | Write CMAQ emissions input files |
| `run_model` | `ModelInputData` → `ModelOutputData` | Run `ADJOINT_FWD` |
| `obs_operator` | `ModelOutputData` → `ObservationData` | Sample concentrations the way the satellite does |

**Adjoint path**, from residuals to a gradient:

| Transform | From → To | Function |
| --- | --- | --- |
| `calc_forcing` | `ObservationData` → `AdjointForcingData` | Turn weighted residuals into adjoint forcing |
| `run_adjoint` | `AdjointForcingData` → `SensitivityData` | Run `ADJOINT_BWD` |
| `map_sense` | `SensitivityData` → `PhysicalAdjointData` | Map sensitivities onto the emissions grid |
| `condition_adjoint` | `PhysicalAdjointData` → `UnknownData` | Convert the gradient into optimiser coordinates |

`condition` (`PhysicalData` → `UnknownData`) completes the set, used to put the
prior into optimiser coordinates at the start.

`condition` and `condition_adjoint` are not the same operation: one transforms a
value, the other transforms a gradient, so the adjoint of the conditioning is
what is applied. Getting this pair wrong produces a gradient that is subtly
wrong rather than obviously broken, which is what the gradient verification
tests exist to catch.

## Driver layer

`_main_driver.py` implements the two functions the optimiser needs:

- **`cost_func(vector)`** — takes optimiser coordinates, walks the forward path
  to simulated observations, and returns `J(x)`.
- **`gradient_func(vector)`** — walks the forward path, computes weighted
  residuals, then walks the adjoint path to return `∇J(x)`.

Each call to either runs CMAQ, which is why iteration counts matter so much to
runtime. L-BFGS-B usually evaluates the cost and the gradient at the same point,
so `data_access.allow_fwd_skip` lets `cost_func` reuse the previous forward run
when called again with an identical vector, roughly halving the forward runs.
When it is enabled, CMAQ input files are deliberately not cleaned up between
calls, since the next call may need them.

`get_answer()` is the entry point, called by `runscript.py`.

`user_driver.py` holds the parts intended to be adjusted per experiment:
fetching the prior and the observations, the `scipy.optimize.fmin_l_bfgs_b` call
in `minim()`, the per-iteration `callback_func` that archives each successful
iteration, and `post_process`.

L-BFGS-B is used because it is quasi-Newton — it builds curvature information
from the gradients it has already seen rather than requiring a Hessian — and
because it supports bounds, which keep emissions non-negative unless
`ALLOW_NEGATIVE_EMISSIONS` is set.

## Configuration

`fourdvar/params/` holds configuration, read **at import time** from the
environment. `fourdvar/env.py` does the loading. See
[Configuration](configuration.md).

| Module | Contents |
| --- | --- |
| `root_path_defn.py` | `STORE_PATH` |
| `date_defn.py` | The run's date range |
| `cmaq_config.py` | Everything CMAQ needs: paths, executables, MPI decomposition, checkpoints |
| `input_defn.py` | Prior and observation file locations |
| `template_defn.py` | CMAQ template file locations |
| `archive_defn.py` | Experiment name and what gets archived per iteration |
| `data_access.py` | Which parts of the data structures the optimiser is allowed to vary |

## Verifying a change

Because a wrong gradient still produces plausible-looking output, changes to the
transform chain need gradient verification rather than only end-to-end checks.

`tests/integration/fourdvar/` holds tests that compare the adjoint gradient
against finite differences of the cost function. If the adjoint is correct they
agree to within numerical precision; if a transform and its adjoint have drifted
apart they do not.

These tests currently depend on input data that has not been provided
reproducibly, so they do not run in CI and are excluded from the default test
run. They should be fixed when possible. Until then, treat a change to
`transfunc/` as unverified unless you have run them by hand with suitable data.

`scripts/fourdvar/singlestep.py` runs one pass of the full chain — forward,
residual, adjoint — without optimising, which is the quickest way to find where
a chain change breaks.

## Historical notes

`data_space_definitions.txt` and `transform_definitions.txt` in this directory
are the original design notes for the data types and transforms. They predate
the current code and use older names, but describe the intended structure of the
framework, which has not fundamentally changed.
