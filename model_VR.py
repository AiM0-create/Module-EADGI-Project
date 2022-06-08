"""
Required python packages:
    - numpy
    - matplotlib
    - requests
    - netCDF4
    - dateutil

Download the landmask (lsmask.nc) from
    https://www.esrl.noaa.gov/psd/data/gridded/data.noaa.oisst.v2.html 

More info on the earthquake catalog:
    https://earthquake.usgs.gov/fdsnws/event/1/
"""

import os
import numpy as np
import shutil
import netCDF4
import requests
import pickle

from math import cos, sin, pi
from matplotlib import cm
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Parameters
ENDPOINT  = "https://earthquake.usgs.gov/fdsnws/event/1/"
LANDMASK  = "netcdf_data/lsmask.nc"
DB_FILE   = "earthquakes.pickle"
PLY_FILE  = "earthquakes.ply"
MAG_RANGE = [2.5, 7]
START     = datetime.strptime("2019-01-01","%Y-%m-%d")
END       = datetime.strptime("2019-07-01","%Y-%m-%d")


class PointCloud:
    """Helper class for point cloud writing"""
    
    def __init__(self):
        self.coords = []
        self.colors = []
        pass
    
    def write(self, path):
        with open(path, "w") as f:
            
            # Do we write the colours?
            write_colors = len(self.colors) == len(self.coords)
            
            # Write the header
            f.write("ply\nformat ascii 1.0\n")
            f.write("element vertex %d\n" % len(self.coords))
            f.write("property float x\n")
            f.write("property float y\n")
            f.write("property float z\n")
            if write_colors:
                f.write("property uchar red\n")
                f.write("property uchar green\n")
                f.write("property uchar blue\n")
            f.write("end_header\n")
            
            # Write the elements
            if write_colors:
                for coord, color in zip(self.coords, self.colors):
                    f.write("%f %f %f %d %d %d\n" % (
                        coord[0],
                        coord[1],
                        coord[2],
                        color[0],
                        color[1],
                        color[2]
                    ))
            else:
                for coord in self.coords:
                    f.write("%f %f %f\n" % (
                        coord[0],
                        coord[1],
                        coord[2]
                    ))

def polar_to_xyz(lon, lat, depth):
    """Convert lat lon and depth to polar coordinates"""
    
    C = (0, 0, 0) # Center
    S = 0.01      # Scale factor
    D = 3         # Depth exageration
    R = 6400      # Earth radius

    # Conversion to radians then cartesian coordinates
    rad_lat, rad_lon = lat * pi / 180, lon * pi / 180
    x = C[0] + S * (R-D*depth) * cos(rad_lat) * cos(rad_lon)
    y = C[1] + S * (R-D*depth) * cos(rad_lat) * sin(rad_lon)
    z = C[2] + S * (R-D*depth) * sin(rad_lat)
    
    return (x, y, z)

def colormap(x, mini, maxi, cmap=cm.inferno):
    """Apply a colormap to a value according to a min/max range"""
    
    fac = (x-mini)/(maxi-mini) # From 0 to 1
    c = cmap( int(255*fac) )
    
    return (int(255*c[0]), int(255*c[1]), int(255*c[2]))

def get_landmask():
    """Return a landmask from a netcdf file"""
    data = netCDF4.Dataset(LANDMASK)
    
    LATS, LONS       = np.meshgrid(data.variables["lon"], data.variables["lat"])
    LATS, LONS       = LATS.ravel(), LONS.ravel()
    MASKS            = data.variables["mask"][0].ravel()
    MASKS[LONS<=-84] = 1 # Remove the bottom of Antarctica (mask=1)
    lats, lons       = LATS[MASKS==0], LONS[MASKS==0]
        
    data.close()

    return lons, lats
     
def make_request(method, t_range, m_range):
    
    # Create the get request parameters
    request_params = {
        "minmagnitude" : m_range[0],
        "maxmagnitude" : m_range[1],
        "starttime"    : t_range[0],
        "endtime"      : t_range[1],
        "format"       : "csv",
        "orderby"      : "time",
    }

    # Do the request
    r = requests.get(
        ENDPOINT + method,
        params = request_params
    )

    # Check for failure
    if r.status_code != requests.codes.ok:
        print("Bad request")
        return None
    
    # Count the number of earthquakes on the period
    if method == "count":
        return int(r.text)
    
    # Get the earthquakes on the period
    elif method == "query":
        earthquakes = []
        lines = r.text.split("\n")[1:-1]
        for l in lines:
            splitted = l.split(",")
            obj = {
                "time" : datetime.strptime(splitted[0], '%Y-%m-%dT%H:%M:%S.%fZ'),
                "lat"  : float(splitted[1]),
                "lon"  : float(splitted[2]),
                "depth": float(splitted[3]),
                "mag"  : float(splitted[4]),
            }
            earthquakes.append(obj)
        return earthquakes

def get_earthquakes(_start, _end, _mag_range):
    
    earthquakes = []
    
    while _start < datetime.now():
            
        # Format the start and end dates
        _stop  = (_start + relativedelta(weeks=2)).strftime("%Y-%m-%d")
        
        # Get the number of quakes on the period
        nQuakes = make_request(
            method  = "count",
            t_range = [_start, _stop],
            m_range = _mag_range
        )

        # Give some info
        print("Collecting %d earthquakes from %s to %s" % (nQuakes, _start, _stop))
        
        # Get the earthquakes
        try:
            earthquakes.extend(
                make_request(
                    method = "query",
                    t_range = [_start, _stop],
                    m_range = _mag_range
                )
            )
        except:
            pass
        
        # Increment the starting date
        _start = _start + relativedelta(weeks=2)
        
    return earthquakes


if __name__ == "__main__":
    
    # Make the API requests to get the data (comment if already done)
    earthquakes = get_earthquakes(START, END, MAG_RANGE)
    with open(DB_FILE, "wb") as f:
        pickle.dump(earthquakes, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    # Read the data from a file (uncomment to avoid repeting the requests)
    # earthquakes = []
    # with open(DB_FILE, 'rb') as f:
    #     earthquakes = pickle.load(f)
    
    # Create the point cloud
    PC = PointCloud()
    # Add the land mask as white points
    lons, lats = get_landmask()
    PC.coords.extend([ polar_to_xyz(lat, lon, 0) for lon, lat in zip(lons, lats) ])
    PC.colors.extend([ (255,255,255) for x in lats ])
    # Add the earthquake as colored data
    PC.coords.extend([ polar_to_xyz(x["lon"], x["lat"], x["depth"]) for x in earthquakes ])
    PC.colors.extend([ colormap(x["mag"], MAG_RANGE[0], MAG_RANGE[1]) for x in earthquakes ])
    # Write the .ply file
    PC.write(PLY_FILE)
    
    # Zip the point cloud
    # shutil.make_archive("earthquakes", "zip", "./", "earthquakes.ply")