"""
restart_script.py

Copyright 2016 University of Melbourne.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""
import os

import fourdvar._main_driver as main
import fourdvar.datadef as d
import fourdvar.user_driver as user
from fourdvar._transform import transform
from fourdvar.params import archive_defn
from fourdvar.util import archive_handle

# If true restart_script uses last iteration in archive
restart_from_last = False

# If restart_from_last = False provide restart number (integer)
restart_number = 0

# Must match filename used by user_driver.callback_func!
iter_fname = 'iter{:04}.ncf'

# name of restart log file saved to archive
restart_log_fname = 'restart_log.txt'



archive_path = os.path.join(archive_defn.archive_path, archive_defn.experiment)
archive_handle.archive_path = archive_path
archive_handle.finished_setup = True

if not restart_from_last:
    start_no = restart_number
else:
    start_no = 1
    while os.path.isfile( os.path.join( archive_path,
                                        iter_fname.format(start_no+1) ) ):
        start_no += 1

assert start_no == int(start_no), 'restart_number must be an integer.'
init_path = os.path.join( archive_path, iter_fname.format(start_no) )
assert os.path.isfile( init_path ), 'Cannot find {}'.format( init_path )

log_path = os.path.join( archive_path, restart_log_fname )
if os.path.isfile( log_path ):
    ftype = 'r+'
else:
    ftype = 'w'
with open( log_path, ftype ) as f:
    f.write( 'restarted from iteration {}\n'.format( start_no ) )

user.iter_num = start_no
init_phys = d.PhysicalData.from_file( init_path )
init_unk = transform( init_phys, d.UnknownData )
init_vec = init_unk.get_vector()

min_output = user.minim( main.cost_func, main.gradient_func, init_vec )
out_vector = min_output[0]
out_unknown = d.UnknownData( out_vector )
out_physical = transform( out_unknown, d.PhysicalData )
user.post_process( out_physical, min_output[1:] )
user.cleanup()
