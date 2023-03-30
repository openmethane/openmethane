import rasterio
from matplotlib import pyplot

emissions = rasterio.open('baseline-methane.tif')
dataBand = emissions.read(1)

pyplot.imshow(dataBand, cmap='pink')
pyplot.show()