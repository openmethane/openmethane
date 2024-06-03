from fourdvar.util import file_handle as fh
import numpy as np

obsList = fh.load_list('/scratch/q90/cm5310/store_share_p4d/archive/november2019/observed.pickle')
obsList = obsList[1:]
def obs2ppm( ob): return ob['value']*(np.array(list(ob['weight_grid'].values()))@ob['ref_profile'])
obsVector = np.array([1000*obs2ppm(o) for o in obsList])
def obs2ppm( ob, wg): return ob['value']*(np.array(list(wg['weight_grid'].values()))@ob['ref_profile'])
iter1Vector = 1000*np.array([obs2ppm(o, w) for o,w  in zip(fh.load_list('/scratch/q90/cm5310/store_share_p4d/archive/november2019/obs_lite_iter0001.pic.gz')[1:], obsList)])
iter22Vector = 1000*np.array([obs2ppm(o, w) for o,w  in zip(fh.load_list('/scratch/q90/cm5310/store_share_p4d/archive/january2020/obs_lite_iter0018.pic.gz')[1:], obsList)])
def obs2ppm( ob, wg): return ob['uncertainty']*(np.array(list(wg['weight_grid'].values()))@ob['ref_profile'])
uncertaintyVector = 1000*np.array([obs2ppm(o, w) for o,w  in zip(fh.load_list('/scratch/q90/cm5310/store_share_p4d/archive/november2019/obs_lite_iter0022.pic.gz')[1:], obsList)])
print(iter22Vector.min(), iter22Vector.max())



cost_fn = np.sum(((iter1Vector- obsVector)/uncertaintyVector)**2)/2 # + np.sum(((iter22Vector-100)/300)**2)/2 

print(cost_fn)

