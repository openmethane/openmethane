"""
cmaq_handle.py

Copyright 2016 University of Melbourne.
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
"""

import os
import glob
import subprocess

import fourdvar.util.date_handle as dt
import fourdvar.params.cmaq_config as cfg
import fourdvar.params.template_defn as template
import fourdvar.util.netcdf_handle as ncf
import fourdvar.util.file_handle as fh


import setup_logging as logging
logger= logging.get_logger( __file__ )

def parse_env_dict( env_dict, date ):
    """
    extension: convert date patterns into values
    input: dictionary (envvar_name: pattern_value), dt.date
    output: dictionary (envvar_name: actual_value)
    
    notes: all names and values must be strings
    """
    parsed = {}
    for name,value in env_dict.items():
        try:
            parsed[ name ] = dt.replace_date( value, date )
        except Exception as e:
            logger.error( 'failed parsing {}: {}'.format( name, value ) )
            raise e
    return parsed

def load_env( env_dict ):
    """
    extension: load dictionary into environment variables
    input: dictionary (envvar_name: value)
    output: None
    
    notes: all names and values must be strings
    """
    for name, value in env_dict.items():
        if logging.verbose_logfile is True:
            logger.debug( 'setenv {} = {}'.format( name, value ) )
        os.environ[ name ] = value
    # now remove empty strings from environment which are killing CMAQ multiprocessing
    for name, value in os.environ.items():
        if value == '': del( os.environ[name])
    return None

def clean_env( env_dict ):
    """
    extension: remove dictionary keys from environment variables
    input: dictionary (envvar_name: value)
    output: None
    """
    for name in env_dict.keys():
        try:
            del os.environ[ name ]
        except KeyError:
            logger.warning('environment variable {name} not found')
    return None

def setup_run():
    """
    extension: setup all the constant environment variables
    input: None
    output: None
    """
    env_dict = {}
    env_dict['NPCOL_NPROW'] = '{:} {:}'.format(cfg.npcol, cfg.nprow)
    env_dict['IOAPI_LOG_WRITE'] = 'T' if cfg.ioapi_logging else 'F'
    env_dict['CTM_MAXSYNC'] = str(cfg.maxsync)
    env_dict['CTM_MINSYNC'] = str(cfg.minsync)
    env_dict['CTM_PT3DEMIS'] = 'Y' if cfg.pt3demis else 'N'
    env_dict['KZMIN'] = 'Y' if cfg.kzmin else 'N'
    env_dict['FL_ERR_STOP'] = 'T' if cfg.fl_err_stop else 'F'
    env_dict['PROMPTFLAG'] = 'T' if cfg.promptflag else 'F'
    env_dict['EMISDATE'] = cfg.emisdate
    env_dict['CTM_STDATE'] = cfg.stdate
    env_dict['CTM_STTIME'] = ''.join( [ '{:02d}'.format(i) for i in cfg.sttime ] )
    env_dict['CTM_RUNLEN'] = ''.join( [ '{:02d}'.format(i) for i in cfg.runlen ] )
    env_dict['CTM_TSTEP'] = ''.join( [ '{:02d}'.format(i) for i in cfg.tstep ] )
    
    if str( cfg.emis_lays ).strip().lower() == 'template':
        fname = dt.replace_date( template.emis, dt.start_date )
        emlays = int(ncf.get_attr( fname, 'NLAYS' ) )
        env_dict['CTM_EMLAYS'] = str( emlays )
    else:
        env_dict['CTM_EMLAYS'] = str( cfg.emis_lays )
    
    if str( cfg.conc_out_lays ).strip().lower() == 'template':
        conclays = int( ncf.get_attr( template.conc, 'NLAYS' ) )
        env_dict['CONC_BLEV_ELEV'] = '1 {:}'.format( conclays )
    else:
        env_dict['CONC_BLEV_ELEV'] = str( cfg.conc_out_lays )
    
    if str( cfg.avg_conc_out_lays ).strip().lower() == 'template':
        conclays = int( ncf.get_attr( template.conc, 'NLAYS' ) )
        env_dict['ACONC_BLEV_ELEV'] = '1 {:}'.format( conclays )
    else:
        env_dict['ACONC_BLEV_ELEV'] = str( cfg.avg_conc_out_lays )
    
    if str( cfg.conc_spcs ).strip().lower() == 'template':
        concspcs = str( ncf.get_attr( template.conc, 'VAR-LIST' ) )
        env_dict['CONC_SPCS'] = ' '.join( concspcs.split() )
    else:
        env_dict['CONC_SPCS'] = str( cfg.conc_spcs )
    
    if str( cfg.avg_conc_spcs ).strip().lower() == 'template':
        concspcs = str( ncf.get_attr( template.conc, 'VAR-LIST' ) )
        env_dict['AVG_CONC_SPCS'] = ' '.join( concspcs.split() )
    else:
        env_dict['AVG_CONC_SPCS'] = str( cfg.avg_conc_spcs )
    
    env_dict['ADJ_CHEM_CHK'] = cfg.chem_chk + ' -v'
    env_dict['ADJ_VDIFF_CHK'] = cfg.vdiff_chk + ' -v'
    env_dict['ADJ_AERO_CHK'] = cfg.aero_chk + ' -v'
    env_dict['ADJ_CPL_CHK'] = cfg.cpl_chk + ' -v'
    env_dict['ADJ_HA_RHOJ_CHK'] = cfg.ha_rhoj_chk + ' -v'
    env_dict['ADJ_VA_RHOJ_CHK'] = cfg.va_rhoj_chk + ' -v'
    env_dict['ADJ_HADV_CHK'] = cfg.hadv_chk + ' -v'
    env_dict['ADJ_VADV_CHK'] = cfg.vadv_chk + ' -v'
    env_dict['ADJ_EMIS_CHK'] = cfg.emis_chk + ' -v'
    env_dict['ADJ_EMIST_CHK'] = cfg.emist_chk + ' -v'
    env_dict['GRIDDESC'] = cfg.griddesc
    env_dict['GRID_NAME'] = cfg.gridname
    env_dict['DEPV_TRAC_1'] = cfg.depv_trac
    #env_dict['OCEAN_1'] = cfg.ocean_file
    env_dict['EMIS_1'] = cfg.emis_file
    env_dict['BNDY_GASC_1'] = cfg.bcon_file
    env_dict['BNDY_AERO_1'] = cfg.bcon_file
    env_dict['BNDY_NONR_1'] = cfg.bcon_file
    env_dict['BNDY_TRAC_1'] = cfg.bcon_file
    env_dict['GRID_DOT_2D'] = cfg.grid_dot_2d
    env_dict['GRID_CRO_2D'] = cfg.grid_cro_2d
    env_dict['MET_CRO_2D'] = cfg.met_cro_2d
    env_dict['MET_CRO_3D'] = cfg.met_cro_3d
    env_dict['MET_DOT_3D'] = cfg.met_dot_3d
    env_dict['MET_BDY_3D'] = cfg.met_bdy_3d
    env_dict['LAYER_FILE'] = cfg.layerfile
    env_dict['XJ_DATA'] = cfg.xj_data
    env_dict['CTM_CONC_1'] = cfg.conc_file + ' -v'
    env_dict['A_CONC_1'] = cfg.avg_conc_file + ' -v'
    env_dict['S_CGRID'] = cfg.last_grid_file + ' -v'
    env_dict['CTM_DRY_DEP_1'] = cfg.drydep_file + ' -v'
    env_dict['CTM_WET_DEP_1'] = cfg.wetdep1_file + ' -v'
    env_dict['CTM_WET_DEP_2'] = cfg.wetdep2_file + ' -v'
    env_dict['CTM_SSEMIS_1'] = cfg.ssemis_file + ' -v'
    env_dict['CTM_VIS_1'] = cfg.aerovis_file + ' -v'
    env_dict['CTM_DIAM_1'] = cfg.aerodiam_file + ' -v'
    env_dict['CTM_IPR_1'] = cfg.ipr1_file + ' -v'
    env_dict['CTM_IPR_2'] = cfg.ipr2_file + ' -v'
    env_dict['CTM_IPR_3'] = cfg.ipr3_file + ' -v'
    env_dict['CTM_IRR_1'] = cfg.irr1_file + ' -v'
    env_dict['CTM_IRR_2'] = cfg.irr2_file + ' -v'
    env_dict['CTM_IRR_3'] = cfg.irr3_file + ' -v'
    env_dict['CTM_RJ_1'] = cfg.rj1_file + ' -v'
    env_dict['CTM_RJ_2'] = cfg.rj2_file + ' -v'
    return env_dict

def run_fwd_single( date, is_first ):
    """
    extension: run cmaq fwd for a single day
    input: dt.date, Boolean (is this day the first of the model)
    output: None
    """
    
    env_dict = setup_run()

    env_dict['PERTCOLS'] = cfg.pertcols
    env_dict['PERTROWS'] = cfg.pertrows
    env_dict['PERTLEVS'] = cfg.pertlevs
    env_dict['PERTSPCS'] = cfg.pertspcs
    env_dict['PERTDELT'] = cfg.pertdelt
    env_dict['CTM_APPL'] = cfg.fwd_appl
    env_dict['CTM_XFIRST_OUT'] = cfg.fwd_xfirst_file
    env_dict['LOGFILE'] = cfg.fwd_logfile
    env_dict['FLOOR_FILE'] = cfg.floor_file
    env_dict['CTM_PROGNAME'] = cfg.fwd_prog

    if is_first is True:
        env_dict['INIT_GASC_1'] = cfg.icon_file
        env_dict['INIT_AERO_1'] = cfg.icon_file
        env_dict['INIT_NONR_1'] = cfg.icon_file
        env_dict['INIT_TRAC_1'] = cfg.icon_file
        env_dict['CTM_XFIRST_IN'] = ''
    else:
        prev_grid = dt.move_tag( cfg.last_grid_file, -1 )
        prev_xfirst = dt.move_tag( cfg.fwd_xfirst_file, -1 )
        env_dict['INIT_GASC_1'] = prev_grid
        env_dict['INIT_AERO_1'] = prev_grid
        env_dict['INIT_NONR_1'] = prev_grid
        env_dict['INIT_TRAC_1'] = prev_grid
        env_dict['CTM_XFIRST_IN'] = prev_xfirst
    
    env_dict = parse_env_dict( env_dict, date )
    load_env( env_dict )
    
    run_cmd = cfg.cmd_preamble
    #print("hello")
    #print(run_cmd)
    if int(cfg.npcol) != 1 or int(cfg.nprow) != 1:
        #use mpi
        run_cmd += 'mpirun -np {:} '.format( int( cfg.npcol ) * int( cfg.nprow ) )
    #print(run_cmd)
    run_cmd += cfg.fwd_prog
    #print(run_cmd)
    stdout_fname = dt.replace_date( cfg.fwd_stdout_log, date )
    print(stdout_fname)
    fh.ensure_path( stdout_fname, inc_file=True )
    with open( stdout_fname, 'w' ) as stdout_file:
        msg = 'calling external process:\n{:}> {:}'.format( cfg.cmd_shell, run_cmd )
        logger.debug( msg )
        statcode = subprocess.call( run_cmd, stdout=stdout_file,
                                    stderr=subprocess.STDOUT,
                                    shell=True, executable=cfg.cmd_shell )
        logger.debug( 'external process finished.' )
    if statcode != 0:
        msg = 'cmaq fwd failed on {}.'.format( date.strftime('%Y%m%d') )
        logger.error( msg )
        raise AssertionError( msg )
    
    clean_env( env_dict )
    return None

def run_bwd_single( date, is_first ):
    """
    extension: run cmaq bwd for a single day
    input: dt.date, Boolean (is this the first time called)
    output: None
    """
    
    env_dict = setup_run()
    
    env_dict['CTM_APPL'] = cfg.bwd_appl
    env_dict['CTM_XFIRST_OUT'] = cfg.bwd_xfirst_file
    env_dict['CTM_XFIRST_IN'] = cfg.fwd_xfirst_file
    env_dict['LOGFILE'] = cfg.bwd_logfile
    env_dict['CTM_PROGNAME'] = cfg.bwd_prog
    env_dict['CHK_PATH'] = cfg.chk_path
    env_dict['INIT_GASC_1'] = cfg.last_grid_file + ' -v'
    env_dict['INIT_AERO_1'] = cfg.last_grid_file + ' -v'
    env_dict['INIT_NONR_1'] = cfg.last_grid_file + ' -v'
    env_dict['INIT_TRAC_1'] = cfg.last_grid_file + ' -v'
    env_dict['CTM_CONC_FWD'] = cfg.conc_file + ' -v'
    env_dict['CTM_CGRID_FWD'] = cfg.last_grid_file + ' -v'
    env_dict['ADJ_LGRID'] = cfg.conc_sense_file + ' -v'
    env_dict['ADJ_LGRID_EM'] = cfg.emis_sense_file + ' -v'
    env_dict['ADJ_LGRID_EM_SF'] = cfg.emis_scale_sense_file + ' -v'
    env_dict['ADJ_FORCE'] = cfg.force_file

    if cfg.sense_sync is True:
        env_dict['ADJ_LGRID_FREQ'] = 'SYNC_STEP'
    else:
        env_dict['ADJ_LGRID_FREQ'] = 'OUTPUT_STEP'
    
    if str( cfg.force_lays ).strip().lower() == 'template':
        frclays = int( ncf.get_attr( template.force, 'NLAYS' ) )
        env_dict['NLAYS_FRC'] = str( frclays )
    else:
        env_dict['NLAYS_FRC'] = str( cfg.force_lays )
    
    if str( cfg.sense_emis_lays ).strip().lower() == 'template':
        emsensl = int( ncf.get_attr( template.sense_emis, 'NLAYS' ) )
        env_dict['CTM_EMSENSL'] = str( emsensl )
    else:
        env_dict['CTM_EMSENSL'] = str( cfg.sense_emis_lays )
    
    if is_first is not True:
        prev_conc = dt.move_tag( cfg.conc_sense_file, 1 )
        prev_emis = dt.move_tag( cfg.emis_sense_file, 1 )
        prev_scale = dt.move_tag( cfg.emis_scale_sense_file, 1 )
        env_dict['INIT_LGRID_1'] = prev_conc
        env_dict['INIT_EM_1'] = prev_emis
        env_dict['INIT_EM_SF_1'] = prev_scale
    
    env_dict = parse_env_dict( env_dict, date )
    load_env( env_dict )
    
    run_cmd = cfg.cmd_preamble
    if int(cfg.npcol) != 1 or int(cfg.nprow) != 1:
        #use mpi
        run_cmd += 'mpirun -np {:} '.format( int( cfg.npcol ) * int( cfg.nprow ) )
    run_cmd += cfg.bwd_prog
    stdout_fname = dt.replace_date( cfg.bwd_stdout_log, date )
    fh.ensure_path( stdout_fname, inc_file=True )
    with open( stdout_fname, 'w' ) as stdout_file:
        msg = 'calling external process:\n{:}> {:}'.format( cfg.cmd_shell, run_cmd )
        logger.debug( msg )
        statcode = subprocess.call( run_cmd, stdout=stdout_file,
                                    stderr=subprocess.STDOUT,
                                    shell=True, executable=cfg.cmd_shell )
        logger.debug( 'external process finished.' )
    if statcode != 0:
        msg = 'cmaq bwd failed on {}.'.format( date.strftime('%Y%m%d') )
        logger.error( msg )
        raise AssertionError( msg )
        
    clean_env( env_dict )
    return None

def clear_local_logs():
    """
    extension: delete logfiles CMAQ puts in cwd
    input: None
    output: None
    """
    #delete every file that matches a pattern in cfg.cwd_logs
    for file_pattern in cfg.cwd_logs:
        file_list = glob.glob( file_pattern )
        for file_name in file_list:
            full_file_name = os.path.realpath( file_name )
            if os.path.isfile( full_file_name ):
                os.remove( full_file_name )
    return None

def run_fwd():
    """
    extension: run cmaq fwd from current config
    input: None
    output: None
    """
    isfirst = True
    for cur_date in dt.get_datelist():
        run_fwd_single(cur_date, isfirst)
        isfirst = False
        clear_local_logs()
    return None

def run_bwd():
    """
    extension: run cmaq bwd from current config
    input: None
    output: None
    """
    isfirst = True
    for cur_date in dt.get_datelist()[::-1]:
        run_bwd_single(cur_date, isfirst)
        isfirst = False
        clear_local_logs()
    return None

def wipeout_bwd():
    """
    extension: delete all files created by a bwd run of cmaq
    input: None
    output: None
    """
    clear_local_logs()
    #delete every file in wipeout_bwd_list
    all_tags = dt.tag_map.keys()
    for pat_name in cfg.wipeout_bwd_list:
        for t in all_tags:
            pat_name = pat_name.replace( t, '*' )
        for fname in glob.glob( pat_name ):
            if os.path.isfile( fname ):
                os.remove( fname )
    return None

def wipeout_fwd():
    """
    extension: delete all files created by a run of cmaq
    input: None
    output: None
    """
    clear_local_logs()
    #cleanup fwd bwd as well
    wipeout_bwd()
    #delete every file in wipeout_fwd_list
    all_tags = dt.tag_map.keys()
    for pat_name in cfg.wipeout_fwd_list:
        for t in all_tags:
            pat_name = pat_name.replace( t, '*' )
        for fname in glob.glob( pat_name ):
            if os.path.isfile( fname ):
                os.remove( fname )
    return None
