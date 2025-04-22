import numpy as np
from netCDF4 import Dataset
import scipy.stats
import scipy.linalg
prior_file = "out-om-domain-info.nc"
posterior_file = "posterior_emissions.nc"



def multi_regr( x, y):
    """ solves multiple linear regression without offset and without bayesian term"""
    k = x @ x.transpose()
    result = scipy.linalg.solve( k, x@y)
    return result

with Dataset(prior_file) as prior_nc:
    layer_names = [k for k in prior_nc.variables.keys() if k.startswith("OCH4")]
    layers = [prior_nc[l][...].mean(axis=0).squeeze().flatten() for l in layer_names]
with Dataset(posterior_file) as posterior_nc:
    prior= posterior_nc["prior_CH4"][...].squeeze().flatten().data
    posterior = posterior_nc['CH4'][...].squeeze().flatten().data
layers = np.array(layers)
print("prior"<multi_regr( layers, prior))
print("posterior",multi_regr( layers, posterior))
