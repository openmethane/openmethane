obsDir = '/scratch/q90/cm5310/store_share_p4d/archive/december2019/'
obsFile = obsDir+'observed.pickle'
iterFile = obsDir+'obs_lite_iter0022.pic.gz'
import numpy as np
from fourdvar.util import file_handle as fh
import pdb
import matplotlib.pyplot as plt
obsList = fh.load_list( obsFile)
iterList = fh.load_list( iterFile)
obsCount = np.zeros((obsList[0]['NROWS'], obsList[0]['NCOLS']))
obsMean = np.zeros_like( obsCount)
iterMean = np.zeros_like( obsCount)
def obs2ppm( ob, wg): return ob['value']*(np.array(list(wg['weight_grid'].values()))@ob['ref_profile'])
for ob, sim in zip( obsList[1:], iterList[1:]):
    obsCount[ sim['lite_coord'][3:5]] +=1
    obsMean[ sim['lite_coord'][3:5]] +=1000*obs2ppm(ob, ob)
    iterMean[ sim['lite_coord'][3:5]] +=1000*obs2ppm( sim, ob)
hasObs = ( obsCount > 0.5) # at least one observation
obsMean[ hasObs] /=  obsCount[ hasObs] # avoiding 0/0 error
iterMean[ hasObs] /= obsCount[ hasObs]
sim2956=[1000*obs2ppm(o,w) for o,w in zip(iterList[1:],obsList[1:]) if list(w['weight_grid'].keys())[0][3:5]  == (26,55)]
obs2956=[1000*obs2ppm(o,o) for o in obsList[1:] if list(o['weight_grid'].keys())[0][3:5] == (27,41)]
day2956=[list(o['weight_grid'].keys())[0][0] % 100 for o in obsList[1:] if list(o['weight_grid'].keys())[0][3:5] == (26,55)]

obs_series = [float('NaN')]*len(sim2956)
#for day in range(len(day2956)):
#    if day+1 not in day2956:
#        obs_series[day] = float('NaN')
#        obs_series.append(obs_series[day+1])
for day in range(1,len(day2956)): 
    if day2956[day] == day2956[day - 1]:
       obs_series.insert(day ,(obs2956[day]+obs2956[day-1])/2)
    elif day+1 in day2956:
        obs_series.insert(day ,obs2956[day])
   # if day not in day2956:
   #     obs_series[day] = float("NaN")
   #     obs_series.append(obs_series[day])

obs_series = obs_series[:31]
#sim2956 = sim2956[:-1]
print(obs2956, len(obs2956))
print(obs_series, len(obs_series))
print(day2956)

plt.plot(obs_series, label = 'Observations')
plt.plot(sim2956, label = 'Simulated Observations')
plt.legend()
plt.xticks(np.arange(len(sim2956)), np.arange(1, len(sim2956)+1))
plt.title('Batemans Bay Simulated and True Observations December 2019')
plt.xlabel('Day')
plt.ylabel('Concentration (ppm)')
plt.savefig('batemans_dec_sim_obs.png')
plt.show()
