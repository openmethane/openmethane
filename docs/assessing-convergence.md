
# Assessing convergence for py4dvar


## Background

py4dvar is based on Gaussian Bayesian statistical inference. In
practice this means it calculates a set of emissions $\mathbf{x}$
which minimises a cost function
$$ J =\frac{1}{2}\left[\frac{(\mathbf{x} -\mathbf{x}_0)^2}{\sigma_x^2}
+\frac{(\mathbf{M}(\mathbf{x}) -\mathbf{y})^2}{\sigma_y^2}\right]
$$
where $\mathbf{x}_0$ is the prior estimate for $\mathbf{x}$,
$\sigma_x$ is the uncertainty of the prior estimate, $\mathbf{M}$ is
an atmospheric transport model (in this case CMAQ), $\mathbf{y}$ is
the set of observations and $\sigma_y$ the observational uncertainty.

py4dvar uses a limited-memory BFGS algorithm to iteratively minimise $J$. This means
rather than minimising the cost function it seeks to minimise the size
(norm) of its gradient. In a simple unimodal function the location of
the zero gradient and function minimum are identical. BFGS algorithms
calculate a direction of likely update then evaluate the cost function
at one point along the direction of that update in order to recommend
a step size.


## Stopping the minimisation

The implementation used in py4dvar has several stopping criteria of
its own. It will stop when
the gradient
norm is sufficiently small. This is usually based on a ratio with the
initial value of the gradient norm rather than an absolute criterion
since the value of $J$ will increase as the size of the problem increases.
It may also stop if the cost function has failed to decrease over
several iterations. this is usually regarded as a failure if the
gradient norm is still significant. Such problems usually arise when
the adjoint model is not an exact match for the forward model but it
may also arise from fine structure in the cost function "trapping" the
minimiser.

Frequently the minimiser will not stop on its own but we may want to
stop it manually. Evidence for this includes:

1.  there is little reduction in the cost function or gradient norm  from one iteration to the nex;
2.  the cost function may increase from one iteration to the next, suggesting the minimiser is failing to find a direction and step size to reduce it;
3.  Iterations are taking longer and longer, suggesting the minimisation has reached the maximum possible given the accuracy of the adjoint or being caught up in fine structure of the cost function.

Criterion 1 is the most common cause. There is no absolute rule but if
one sees significant reduction for a few iterations then little change
after that it is time to intervene.


## Considerations of Noise and Uncertainty

In all Bayesian inversions there is a balance to strike between
fitting real structures in the data but not trying to fit noise. This
is operationalised via the normalised chi-squared statistic reported
as chisq in py4dvar. It is defined as
$$ \chi^2 = \frac{2J}{N} $$
where $N$ is the number of observations. It roughly describes the
average of the distance between a simulation and an observation
divided by the observational uncertainty. If $\chi^2 < 1$ then we are
already matching the observations as well as we can expect given their
uncertainty. Much lower $\chi^2$ says we are risking over-fitting.
$\chi^2 >1$ suggests we are not matching the observations as well as
we should. Unfortunately there are two causes for this:

1.  our iteration has not yet converged;
2.  We have been too optimistic about our ability to fit the data.

Generally large $\chi^2$ is not a problem for convergence but low
$\chi^2$ suggests further iterations might only be matching noise and
so we should be less reticent in stopping the iteration. It does not
mean we should stop the iteration as soon as $\chi^2$ reaches 1
though. There might still be regions of the data space where further
improvement is possible.

