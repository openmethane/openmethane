import rasterio
import csv
import numpy as np

## Constants
LAND_USE_MAP_PATH = "NLUM_ALUMV8_250m_2015_16_alb.tif"
SECTOR_MAP_PATH = "landuse-sector-map.csv"
SECTORAL_EMISSIONS_MAP_PATH = "methane-inventory-by-sector.csv"
OUTPUT_PATH = "baseline-methane.tif"

## Load land use data
landuseData = rasterio.open(LAND_USE_MAP_PATH)
meta = landuseData.meta

## Import a map of land use type numbers to emissions sectors
landuseSectorMap = {}
with open(SECTOR_MAP_PATH, 'r', newline='') as f:
    reader = csv.reader(f)
    next(reader) # toss headers

    for value, sector in reader:
        landuseSectorMap[int(value)] = sector

## Import a map of emissions per sector, store it to hash table
methaneInventoryBySector = {}
seenHeaders = False
with open(SECTORAL_EMISSIONS_MAP_PATH, 'r', newline='') as f:
    reader = csv.reader(f)

    for year, ag, mining, manufacturing, energy, construction, commercial, transport, residential in reader:
        if not seenHeaders:
            yearLabel, agLabel, miningLabel, manufacturingLabel, energyLabel, constructionLabel, commercialLabel, transportLabel, residentialLabel = [year, ag, mining, manufacturing, energy, construction, commercial, transport, residential]
            seenHeaders = True
        if year == "2020":
            methaneInventoryBySector[agLabel] = float(ag)
            methaneInventoryBySector[miningLabel] = float(mining)
            methaneInventoryBySector[manufacturingLabel] = float(manufacturing)
            methaneInventoryBySector[energyLabel] = float(energy)
            methaneInventoryBySector[constructionLabel] = float(construction)
            methaneInventoryBySector[commercialLabel] = float(commercial)
            methaneInventoryBySector[transportLabel] = float(transport)
            methaneInventoryBySector[residentialLabel] = float(residential)

## Create a dict to count all of the instances of each sector in the land use data
sectorCounts = dict.fromkeys(methaneInventoryBySector, 0)

## Read the land use type data band
dataBand = landuseData.read(1)

## Count all the unique land-use types
unique, counts = np.unique(dataBand, return_counts=True)
usageCounts = dict(zip(unique, counts))

## Sum the land-use counts into sector counts
for usageType, count in usageCounts.items():
    sector = landuseSectorMap[int(usageType)]
    if (sector):
        sectorCounts[sector] += count

## Calculate out a per grid-square value for each sector
sectorEmissionsPerGridSquare = dict.fromkeys(methaneInventoryBySector, 0)
for sector, numGridSquares in sectorCounts.items():
    if numGridSquares != 0:
        sectorEmissionsPerGridSquare[sector] = methaneInventoryBySector[sector] / numGridSquares

## For each land use type, assign the per-pixel emissions (in tonnes) to every pixel of that type
for landUseType, _ in usageCounts.items():
    sector = landuseSectorMap[landUseType]
    emission = sectorEmissionsPerGridSquare[sector] if sector else 0
    dataBand[dataBand == landUseType] = emission * 1000000 # convert to tonnes

## Write the data band to a new output image
with rasterio.open(OUTPUT_PATH, 'w', **meta, compress = 'lzw') as dst:
    dst.write(dataBand, indexes = 1)