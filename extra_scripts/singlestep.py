priorFile = '/scratch/q90/sa6589/data/gipnet_methane/archive/real_test/prior.ncf'
iterFile = '/scratch/q90/cm5310/store_share_p4d/archive/example_experiment/iter0023.ncf'
obsFile = '/scratch/q90/sa6589/data/gipnet_methane/archive/real_test/observed.pickle'
simulFile = '/scratch/q90/cm5310/plotting/simulations.pickle'
import fourdvar.user_driver as user
import fourdvar.datadef as d
from fourdvar._transform import transform

observed = d.ObservationData.from_file( obsFile)
physical = d.PhysicalData.from_file( priorFile)
#simul = d.ObservationData.from_file( simulFile )
modelInput = transform( physical, d.ModelInputData)
#modelInput.archive('/scratch/q90/cm5310/plotting/model_input')
modelOutput = transform( modelInput, d.ModelOutputData)
simul = transform( modelOutput, d.ObservationData)
residual = d.ObservationData.get_residual(observed, simul)
#residual.archive('/scratch/q90/cm5310/plotting/residual')
#simul.archive('/scratch/q90/cm5310/plotting/simulations.pickle')
w_residual = d.ObservationData.error_weight( residual )
adj_forcing = transform( w_residual, d.AdjointForcingData )
sensitivity = transform( adj_forcing, d.SensitivityData )
phys_sense = transform( sensitivity, d.PhysicalAdjointData )
un_gradient = transform( phys_sense, d.UnknownData )
        
