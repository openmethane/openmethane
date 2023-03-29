# Baseline methane emissions map
This folder contains scripts to generate a baseline methane emissions map. 

The method will distribute methane inventories by sector based on land-use data. Over time we will re-visit this process to improve the estimation.

### Input data
Paths to these files should be updated in the *constants* section at the top of the `baseline.py` file.

* NLUM_ALUMV8_250m_2015_16_alb.tif: map of land use data taken from the *Land use of Australia 2010–11 to 2015–16, 250m* data package, found here: https://www.agriculture.gov.au/sites/default/files/documents/nlum_alumv8_250m_2015_16_alb.zip
* methane-inventory-by-sector.csv: methane emissions inventories by sector from https://greenhouseaccounts.climatechange.gov.au/
* landuse-sector-map.csv: a mapping of the land-use categories to the emissions sectors

A zip archive of the above files can be found here: https://drive.google.com/file/d/1UmABgLvGU5U_sJJSsJGCdlZcI7t6EL6W/view?usp=share_link

### Installation
```console 
pip install -r requirements.txt
```

### Running the process
```console
python baseline.py
```

### Preview output

For convenience, the following script allows a preview of the output image in `pyplot`  
```console
python display.py
```


By default the output will be written to `baseline-methane.tif`