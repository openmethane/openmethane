
import numpy as np
import xarray as xr

def extract_bounds(corner_coords: xr.Variable):
    """
    Extract grid cell boundary coordinates for a single dimension, from a 2D
    array of size x+1,y+1 where x,y are the grid cell coordinates.
    An array describing the corners of a 2x2 grid would have 3x3 items, where
    the corners of the cell at [0][0] would be: [0][0], [1][0], [1][1], [0][1]

    See: https://cfconventions.org/Data/cf-conventions/cf-conventions-1.11/cf-conventions.html#cell-boundaries

    :param corner_coords:
    :return:
    """
    corner_shape = np.shape(corner_coords)
    if corner_shape[0] < 1 or corner_shape[1] < 1:
        raise ValueError("no corner coordinates provided")

    # create an array smaller by 1 in each dimension
    corner_values = np.empty(shape=(corner_shape[0] - 1, corner_shape[1] - 1, 4))

    it = np.nditer(corner_values, flags=["multi_index"], op_axes=[[0, 1]])
    for _ in it:
        y, x = it.multi_index
        corner_values[y][x] = [
            corner_coords[y][x],
            corner_coords[y + 1][x],
            corner_coords[y + 1][x + 1],
            corner_coords[y][x + 1],
        ]
    return corner_values
