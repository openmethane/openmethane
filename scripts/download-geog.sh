#!/usr/bin/env bash
# Downloads the required WRF Geog data
#
# The output will be stored in `data/geog`
# with the geog data required by WRF being stored in `data/geog/WPS_GEOG`.
#
# Required datasets: Defaults + USGS

set -Eeuo pipefail

parse_params() {
  # default values of variables set from params
  low_res=0
  force=0
  verbose=0

  while :; do
    case "${1-}" in
#    -h | --help) usage ;;
    -v | --verbose) verbose=1 ;;
    -l | --low-res) low_res=1 ;; # Download low res data
    -f | --force) force=1 ;; # Delete existing data if present
    -?*) die "Unknown option: $1" ;;
    *) break ;;
    esac
    shift
  done

  args=("$@")

  return 0
}

parse_params "$@"

output_dir="data/geog"

wget_args="-nv"
tar_args=""
if ((verbose)); then
  set -x
  wget_args="-v"
  tar_args="-v"
fi

if ((force)); then
  echo "Deleting existing data"
  rm -rf $output_dir
fi

mkdir -p $output_dir

if ((low_res)); then
  echo "Downloading low resolution data"
  wget -N ${wget_args} https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_low_res_mandatory.tar.gz -P $output_dir
  wget -N ${wget_args} https://www2.mmm.ucar.edu/wrf/src/wps_files/landuse_10m.tar.bz2 -P $output_dir
  tar ${tar_args} -xf $output_dir/geog_low_res_mandatory.tar.gz -C $output_dir
	echo "Extracting data to $output_dir/WPS_GEOG..."
  tar ${tar_args} -xf $output_dir/landuse_10m.tar.bz2 -C $output_dir/WPS_GEOG_LOW_RES
  if [[ -d $output_dir/WPS_GEOG ]]; then
    cp -r $output_dir/WPS_GEOG_LOW_RES/* $output_dir/WPS_GEOG/
    rm -r $output_dir/WPS_GEOG_LOW_RES
  else
    mv $output_dir/WPS_GEOG_LOW_RES $output_dir/WPS_GEOG
  fi
else
  echo "Downloading high resolution data"
  wget -N ${wget_args} https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_high_res_mandatory.tar.gz -P $output_dir
	wget -N ${wget_args} https://www2.mmm.ucar.edu/wrf/src/wps_files/landuse_30s.tar.bz2 -P $output_dir
	echo "Extracting data to $output_dir/WPS_GEOG..."
	echo "  This may take a few minutes"
	tar ${tar_args} -xzf $output_dir/geog_high_res_mandatory.tar.gz -C $output_dir
	echo "  geog_high_res_mandatory.tar.gz extracted"
	bunzip2 $output_dir/landuse_30s.tar.bz2
	tar ${tar_args} -xf $output_dir/landuse_30s.tar -C $output_dir/WPS_GEOG
fi

echo "Completed downloading and extracting WRF geog data."
