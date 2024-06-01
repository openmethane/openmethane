#!/usr/bin/env python

print("load libraries")
# Plot netCDF data on a Map
# First we need to import netCDF-Pyton, Numpy, Matplotlib for plotting, and Basemap for the map
import numpy as np
import seaborn as sns
from netCDF4 import Dataset as NetCDFFile

sns.set()
print("read data")

##put your month identfiers if you wish to loop the code for different months
##months=['Jan','Feb','Mar','Apr', 'May','Jun','July','Aug','Sep', 'Oct', 'Nov', 'Dec']
months = ["May"]
## define the region of interest
lonlim = [95.0, 180.0]
latlim = [-55.0, 10.0]
##population data netcdf files (this is drived from tiff data)
ncp = NetCDFFile(
    "/scratch/q90/sa6589/test_Sougol/shared_Sougol/gpw_2020_30_sec.nc"
)  ##path to the GPW data
ncp2 = NetCDFFile(
    "/scratch/q90/sa6589/test_Sougol/shared_Sougol/gpw_2015_30_sec.nc"
)  ##path to the GPW data

# reading lat & lon from population data
latp = ncp.variables["lat"][:]
lonp = ncp.variables["lon"][:]

## define the region of interest
lonlim = [95.0, 180.0]
latlim = [-55.0, 10.0]
## figure out which grid-points of population data are in the region of interest
ilonp = np.where(np.logical_and(lonlim[0] <= lonp, lonp <= lonlim[1]))[0]
ilatp = np.where(np.logical_and(latlim[0] <= latp, latp <= latlim[1]))[0]
ilonp0 = ilonp[0]
ilonp1 = ilonp[-1] + 1
ilatp0 = ilatp[0]
ilatp1 = ilatp[-1] + 1
population1 = ncp.variables["Band1"][ilatp0:ilatp1, ilonp0:ilonp1]
population2 = ncp2.variables["Band1"][ilatp0:ilatp1, ilonp0:ilonp1]
##set a factor for averaging population data to be consistent with EDGAR year
fac = 0.6  ###this factor is used for averaging 2015 and 2020 data for 2018
population = fac * (population1 + population2)
for imonth, month in enumerate(months):
    ##define the merged monthly emission files
    nc = NetCDFFile(
        "/scratch/q90/sa6589/test_Sougol/shared_Sougol/v7.0_FT2021_CH4_2019_TOTALS.0.1x0.1.nc".format(
            )
    )

    # reading lat & lon from emission data
    lat = nc.variables["lat"][:]
    lon = nc.variables["lon"][:]
    ilon = np.where(np.logical_and(lonlim[0] <= lon, lon <= lonlim[1]))[0]
    ilat = np.where(np.logical_and(latlim[0] <= lat, lat <= latlim[1]))[0]
    ilon0 = ilon[0]
    ilon1 = ilon[-1] + 1
    ilat0 = ilat[0]
    ilat1 = ilat[-1] + 1
    emission = nc.variables["emi_ch4"][ilat0:ilat1, ilon0:ilon1]
    # -----------------Downscaling----------------
    print("start to rescale emission data based on population data")
    ## Creat a factor for extrapolating the EDGAR emissions
    ###NOTE: for Ch4 the proxies are equal to 1.0, as both emissions and populations are for the same year (2018)
    shape0 = population1.shape
    proxy_matrix = np.ones(shape0, dtype=float)

    ## Creat the array for region of interest with emission data resolution
    shape1 = emission.shape
    emi_matrix = np.zeros(shape1, dtype=float)
    for i1 in range(0, shape1[0]):
        for j1 in range(0, shape1[1]):
            emi_matrix[i1, j1] = (
                emission[i1, j1] * 123.21 * 1e6
            )  # this factor is used to convert the kg/s/m2 to kg/s
            # emi_matrix[i1,j1] = (emission[i1,j1])

    ## Creat the array for region of interest with population data resolution
    shape2 = population1.shape
    pop_matrix = np.zeros(shape2, dtype=float)
    for i2 in range(0, shape2[0]):
        for j2 in range(0, shape2[1]):
            if population[i2, j2]:
                pop_matrix[i2, j2] = population[i2, j2]

            else:
                pop_matrix[i2, j2] = 1.0
    ## Downscaling Calculation
    ## Downscaling based on Population
    # Sougol
    empty_matrix_p = np.full(shape2, 0, dtype=float)
    pointer1 = 0
    pointer2 = 0
    p1 = 0
    p2 = 0
    for i in range(0, shape2[0]):
        if p1 == 12:
            pointer1 = pointer1 + 1
            p1 = 0
        p1 = p1 + 1
        # print(pointer1,pointer2,j,i)
        for j in range(0, shape2[1]):
            empty_matrix_p[i, j] = emi_matrix[pointer1, pointer2] / 144
            p2 = p2 + 1
            if p2 == 12:
                pointer2 = pointer2 + 1
                p2 = 0
        pointer2 = 0
    # Sougol
    print("Start to making netCDF4 file of Emission data on Aus Domain")
    from netCDF4 import Dataset

    emission_Aus = Dataset(
        f"/scratch/q90/sa6589/test_Sougol/shared_Sougol/downscaling_out/emission_{month}.nc",
        "w",
        format="NETCDF4_CLASSIC",
    )
    print(emission_Aus.file_format)

    lat = emission_Aus.createDimension("lat", shape1[0])
    lon = emission_Aus.createDimension("lon", shape1[1])
    for dimname in emission_Aus.dimensions.keys():
        dim = emission_Aus.dimensions[dimname]

    # Create coordinate variables for 2-dimensions
    latitudes = emission_Aus.createVariable("latitude", np.float32, ("lat",))
    longitudes = emission_Aus.createVariable("longitude", np.float32, ("lon",))

    # Create the actual 2-d variable
    CH4_Aus = emission_Aus.createVariable("CH4_Aus", np.float32, ("lat", "lon"))
    # print 'CH4_Aus variable:', emission_Aus.variables['CH4_Aus']
    for varname in emission_Aus.variables.keys():
        var = emission_Aus.variables[varname]

    # Variable Attributes
    latitudes.units = "degree_north"
    longitudes.units = "degree_east"
    CH4_Aus.units = "kg s-1"

    lats = np.arange(latlim[0], latlim[1], (latlim[1] - latlim[0]) / shape1[0])
    lons = np.arange(lonlim[0], lonlim[1], (lonlim[1] - lonlim[0]) / shape1[1])

    latitudes[:] = lats
    longitudes[:] = lons

    nlats = len(emission_Aus.dimensions["lat"])
    nlons = len(emission_Aus.dimensions["lon"])
    CH4_Aus[:, :] = emi_matrix
    print("CH4_Aus shape after adding data = ", CH4_Aus.shape)
    emission_Aus.close()
    # --------------------Start making NetCDF File of Down-scaled Data (Emission based on population)------------------------

    print("Start to making netCDF4 file of Down-sacaled data based on population")
    from netCDF4 import Dataset

    emission_population = Dataset(
        f"/scratch/q90/sa6589/test_Sougol/shared_Sougol/downscaling_out/emission_downscaled_{month}.nc",
        "w",
        format="NETCDF4_CLASSIC",
    )
    print(emission_population.file_format)

    lat = emission_population.createDimension("lat", population[:, 0].size)
    lon = emission_population.createDimension("lon", population[0, :].size)

    for dimname in emission_population.dimensions.keys():
        dim = emission_population.dimensions[dimname]

    # Create coordinate variables for 2-dimensions
    latitudes = emission_population.createVariable("latitude", np.float32, ("lat",))
    longitudes = emission_population.createVariable("longitude", np.float32, ("lon",))

    # Create the actual 2-d variable
    CH4_pop = emission_population.createVariable("CH4_pop", np.float32, ("lat", "lon"))
    # print 'CH4_pop variable:', emission_population.variables['CH4_pop']
    for varname in emission_population.variables.keys():
        var = emission_population.variables[varname]

    # Variable Attributes
    latitudes.units = "degree_north"
    longitudes.units = "degree_east"
    CH4_pop.units = "kg s-1"

    lats = np.arange(latlim[0], latlim[1], (latlim[1] - latlim[0]) / shape2[0])
    lons = np.arange(lonlim[0], lonlim[1], (lonlim[1] - lonlim[0]) / shape2[1])

    latitudes[:] = lats
    longitudes[:] = lons

    nlats = len(emission_population.dimensions["lat"])
    nlons = len(emission_population.dimensions["lon"])
    CH4_pop[:, :] = empty_matrix_p
    # print 'CH4_population shape after adding data = ', CH4_pop.shape
    emission_population.close()
