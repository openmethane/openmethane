"""Build the WPS and WRF namelists for a run window.

Both namelists are built from one `DomainSet`, so their geometry always agrees.
Everything in `namelist.input` that is neither geometry nor time comes from the
model configuration template, `model_config/namelist.input`.
"""

import copy
import importlib.resources

import f90nml

from openmethane.wrf.geometry import DomainSet
from openmethane.wrf.windows import RunWindow

WPS_DATE_FORMAT = "%Y-%m-%d_%H:%M:%S"
ANALYSIS_PREFIX = "ERA"
"""ungrib's prefix for the FNL intermediate files. setup-wrf kept ERA-Interim's name"""

MODEL_CONFIG = "openmethane.wrf.model_config"
IOFIELDS_FILE = "add_remove_var.txt"

# Settings WRF reads as one value per domain ("max_domains" in WRF 4.5.1's
# Registry). A single value in the template is repeated for every domain;
# written as a scalar, WRF would apply it to the first domain only and give the
# nests its defaults.
PER_DOMAIN = {
    "time_control": {
        *(f"start_{unit}" for unit in ("year", "month", "day", "hour", "minute", "second")),
        *(f"end_{unit}" for unit in ("year", "month", "day", "hour", "minute", "second")),
        "input_from_file",
        "history_interval",
        "frames_per_outfile",
        "history_begin_h",
        "iofields_filename",
        "auxinput4_interval",
    },
    "domains": {
        "s_we",
        "e_we",
        "s_sn",
        "e_sn",
        "s_vert",
        "e_vert",
        "dx",
        "dy",
        "grid_id",
        "parent_id",
        "i_parent_start",
        "j_parent_start",
        "parent_grid_ratio",
        "parent_time_step_ratio",
    },
    "physics": {
        "mp_physics",
        "ra_lw_physics",
        "ra_sw_physics",
        "radt",
        "sf_sfclay_physics",
        "sf_surface_physics",
        "bl_pbl_physics",
        "bldt",
        "cu_physics",
        "cudt",
        "cu_diag",
        "sf_urban_physics",
        "progn",
    },
    "dynamics": {
        "diff_opt",
        "km_opt",
        "diff_6th_opt",
        "diff_6th_factor",
        "zdamp",
        "dampcoef",
        "khdif",
        "kvdif",
        "non_hydrostatic",
        "moist_adv_opt",
        "scalar_adv_opt",
    },
    "bdy_control": {
        "specified",
        "nested",
        "periodic_x",
        "symmetric_xs",
        "symmetric_xe",
        "open_xs",
        "open_xe",
        "periodic_y",
        "symmetric_ys",
        "symmetric_ye",
        "open_ys",
        "open_ye",
    },
}

# Settings with one value for the whole run. Every setting in the template must
# be here or in PER_DOMAIN, so adding one forces a decision about which it is.
SINGLE_VALUED = {
    "time_control": {
        "run_days",
        "run_hours",
        "run_minutes",
        "run_seconds",
        "interval_seconds",
        "restart",
        "ignore_iofields_warning",
        "restart_interval",
        "io_form_history",
        "io_form_restart",
        "io_form_input",
        "io_form_boundary",
        "io_form_auxinput2",
        "auxinput1_inname",
        "auxinput4_inname",
        "io_form_auxinput4",
        "use_netcdf_classic",
        "debug_level",
    },
    "domains": {
        "time_step",
        "time_step_fract_num",
        "time_step_fract_den",
        "max_dom",
        "num_metgrid_levels",
        "num_metgrid_soil_levels",
        "feedback",
        "smooth_option",
    },
    "physics": {
        "isfflx",
        "ifsnow",
        "icloud",
        "surface_input_source",
        "num_soil_layers",
        "sst_update",
        "sst_skin",
        "num_land_cat",
    },
    "dynamics": {"w_damping", "base_temp", "damp_opt"},
    "bdy_control": {"spec_bdy_width", "spec_zone", "relax_zone"},
    "namelist_quilt": {"nio_tasks_per_group", "nio_groups"},
}


class NamelistError(ValueError):
    """The model configuration template can't be applied to a domain set."""


def model_config_file(name: str):
    """A file of the model configuration shipped with openmethane, such as add_remove_var.txt."""
    return importlib.resources.files(MODEL_CONFIG) / name


def read_model_config() -> f90nml.Namelist:
    """Read the model configuration template shipped with openmethane."""
    return f90nml.reads(model_config_file("namelist.input").read_text())


def build_wps_namelist(
    domains: DomainSet, window: RunWindow, geog_data_path: str | None = None
) -> f90nml.Namelist:
    """
    Build `namelist.wps` for ungrib and metgrid over a run window.

    Parameters
    ----------
    domains
        The domains in the run.
    window
        The run window, whose start and end bound the analyses read.
    geog_data_path
        Where geogrid's static geography data is. Only geogrid reads it, and
        geogrid doesn't run in a WRF run, so it can be left out.
    """
    count = len(domains)
    outer = domains.outer.geometry

    geogrid = {
        "parent_id": domains.per_domain("parent_index"),
        "parent_grid_ratio": domains.per_domain("parent_grid_ratio"),
        "i_parent_start": domains.per_domain("i_parent_start"),
        "j_parent_start": domains.per_domain("j_parent_start"),
        "e_we": domains.per_domain("e_we"),
        "e_sn": domains.per_domain("e_sn"),
        "geog_data_res": domains.per_domain("geog_data_res"),
        # WPS takes the outer domain's spacing and derives the nests' from
        # parent_grid_ratio.
        "dx": outer.dx,
        "dy": outer.dy,
        "map_proj": outer.map_proj,
        "ref_lat": outer.ref_lat,
        "ref_lon": outer.ref_lon,
        "truelat1": outer.truelat1,
        "truelat2": outer.truelat2,
        "stand_lon": outer.stand_lon,
    }
    if outer.ref_x is not None:
        geogrid["ref_x"] = outer.ref_x
    if outer.ref_y is not None:
        geogrid["ref_y"] = outer.ref_y
    if geog_data_path is not None:
        geogrid["geog_data_path"] = geog_data_path

    return _ordered(
        {
            "share": {
                "wrf_core": "ARW",
                "max_dom": count,
                "start_date": [window.start.strftime(WPS_DATE_FORMAT)] * count,
                "end_date": [window.end.strftime(WPS_DATE_FORMAT)] * count,
                "interval_seconds": 6 * 60 * 60,
                "io_form_geogrid": 2,
                "debug_level": 0,
            },
            "geogrid": geogrid,
            "ungrib": {"out_format": "WPS", "prefix": ANALYSIS_PREFIX},
            "metgrid": {
                # No SST intermediate files are made, and metgrid skips the
                # missing ones. Kept until #328 checks that removing it
                # leaves met_em unchanged.
                "fg_name": [ANALYSIS_PREFIX, "SST"],
                "io_form_metgrid": 2,
            },
        }
    )


def _ordered(groups: dict) -> f90nml.Namelist:
    """
    A namelist that keeps the order groups and settings were given in.

    f90nml sorts a plain dict, but WPS reads its groups in a fixed order and
    stops at the end of the file, so a group written too early is never read.
    """
    return f90nml.Namelist(
        [(name, f90nml.Namelist(list(settings.items()))) for name, settings in groups.items()]
    )


def build_wrf_namelist(
    domains: DomainSet,
    window: RunWindow,
    *,
    num_metgrid_levels: int,
    num_metgrid_soil_levels: int,
    model_config: f90nml.Namelist | None = None,
) -> f90nml.Namelist:
    """
    Build `namelist.input` for real.exe and wrf.exe over a run window.

    Parameters
    ----------
    domains
        The domains in the run.
    window
        The run window.
    num_metgrid_levels, num_metgrid_soil_levels
        Atmospheric and soil levels in the window's met_em files, which
        real.exe must be told. They depend on the analysis, so are read from
        met_em rather than configured.
    model_config
        The model configuration. Defaults to the template shipped with
        openmethane, from `read_model_config`.

    Raises
    ------
    NamelistError
        If the model configuration has a setting not classified as per-domain
        or single-valued, or a per-domain list of the wrong length.
    """
    count = len(domains)
    # A deep copy, since the groups are changed in place below
    namelist = read_model_config() if model_config is None else copy.deepcopy(model_config)
    _expand_per_domain(namelist, count)

    time_control = namelist.setdefault("time_control", f90nml.Namelist())
    for prefix, when in (("start", window.start), ("end", window.end)):
        for unit in ("year", "month", "day", "hour", "minute", "second"):
            time_control[f"{prefix}_{unit}"] = [getattr(when, unit)] * count
    # Spin-up output is never used, so WRF doesn't write it
    time_control["history_begin_h"] = [window.spin_up_hours] * count

    domain_settings = namelist.setdefault("domains", f90nml.Namelist())
    domain_settings.update(
        {
            "max_dom": count,
            "s_we": [1] * count,
            "e_we": domains.per_domain("e_we"),
            "s_sn": [1] * count,
            "e_sn": domains.per_domain("e_sn"),
            "num_metgrid_levels": num_metgrid_levels,
            "num_metgrid_soil_levels": num_metgrid_soil_levels,
            "dx": domains.per_domain("dx"),
            "dy": domains.per_domain("dy"),
            "grid_id": domains.per_domain("index"),
            "parent_id": domains.per_domain("parent_index"),
            "i_parent_start": domains.per_domain("i_parent_start"),
            "j_parent_start": domains.per_domain("j_parent_start"),
            "parent_grid_ratio": domains.per_domain("parent_grid_ratio"),
            # A nest takes as many time steps as it has cells per parent cell,
            # so its time step shrinks with its spacing.
            "parent_time_step_ratio": domains.per_domain("parent_grid_ratio"),
        }
    )

    # The outer domain's boundaries come from wrfbdy; each nest's from its parent.
    bdy_control = namelist.setdefault("bdy_control", f90nml.Namelist())
    bdy_control["specified"] = [not domain.geometry.is_nest for domain in domains]
    bdy_control["nested"] = [domain.geometry.is_nest for domain in domains]

    return namelist


def _expand_per_domain(namelist: f90nml.Namelist, count: int) -> None:
    """Repeat each per-domain setting once per domain, in place."""
    unclassified = []
    for group, settings in namelist.items():
        for key, value in settings.items():
            if key in PER_DOMAIN.get(group, ()):
                if isinstance(value, list):
                    if len(value) != count:
                        raise NamelistError(
                            f"{group}.{key} has {len(value)} values for {count} domains"
                        )
                else:
                    settings[key] = [value] * count
            elif key not in SINGLE_VALUED.get(group, ()):
                unclassified.append(f"{group}.{key}")
    if unclassified:
        raise NamelistError(
            "Settings must be classified as PER_DOMAIN or SINGLE_VALUED in"
            f" openmethane.wrf.namelists: {', '.join(unclassified)}"
        )
