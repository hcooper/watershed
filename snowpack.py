from sentinelhub.geometry import BBox, Geometry
from sentinelhub.constants import CRS, MimeType
from sentinelhub.download.sentinelhub_client import SentinelHubDownloadClient
from sentinelhub.data_collections import DataCollection
from sentinelhub.geo_utils import bbox_to_dimensions
from sentinelhub.api.process import SentinelHubRequest
from sentinelhub.config import SHConfig

import numpy as np

import matplotlib.pyplot as plt
import numpy as np
import json
from rasterio.io import MemoryFile
import datetime
import geopandas as gpd
from ipyleaflet import Map, GeoJSON, basemaps
import json

config = SHConfig()
config.sh_client_id = "1c6b2a51-a178-4af8-be16-76fa354a0d7c"
config.sh_client_secret = "sL0AOI7JKaY3CvNqMcXktXk3tHE67pb1"

evalscript = """
//VERSION=3
function setup() {
  return {
    input: ["B03", "B11","B04","B02","dataMask"],
     output: [
       { id: "true_color", bands: 4 },
       { id: "ndsi", bands: 4 }
     ]
  };
}

function evaluatePixel(samples) {
    let val = index(samples.B03, samples.B11);
  	let imgVals = null;
    // The library for tiffs works well only if there is only one channel returned.
    // So we encode the "no data" as NaN here and ignore NaNs on frontend.
    const indexVal = samples.dataMask === 1 ? val : NaN;

    true_color = [2.5*samples.B04, 2.5*samples.B03, 2.5*samples.B02, samples.dataMask];

    if (val>0.42)
      ndsi = [0, 0.2, 1, samples.dataMask];  // highlight snow
    else
      ndsi = true_color;

  	return {
      true_color: true_color,
      ndsi: ndsi,
    };
}
"""


class Snowpack:
    def __init__(self, geojson_filename):

        # Create the date range
        start_date = datetime.date(2024, 5, 1)
        end_date = datetime.date(2024, 5, 22)
        assert end_date > start_date  # stuff goes wrong if not

        dates = [
            date.strftime("%Y-%m-%d")
            for date in [
                start_date + datetime.timedelta(days=x)
                for x in range((end_date - start_date).days + 1)
            ]
        ]

        river_gdf = gpd.read_file(geojson_filename)
        self.river_gdf = river_gdf.to_crs("WGS84")
        data = json.load(open(geojson_filename, "r"))

        geo_json = GeoJSON(data=data)

        min_lon, min_lat, max_lon, max_lat = (
            min(
                coord[0]
                for coord in geo_json.data["features"][0]["geometry"]["coordinates"][0]
            ),
            min(
                coord[1]
                for coord in geo_json.data["features"][0]["geometry"]["coordinates"][0]
            ),
            max(
                coord[0]
                for coord in geo_json.data["features"][0]["geometry"]["coordinates"][0]
            ),
            max(
                coord[1]
                for coord in geo_json.data["features"][0]["geometry"]["coordinates"][0]
            ),
        )

        self.bbox = BBox(bbox=[(min_lon, max_lat), (max_lon, min_lat)], crs=CRS.WGS84)
        self.size = bbox_to_dimensions(self.bbox, resolution=10)

        # Build & fetch Sentinel API requests
        requests = [self._build_request(date) for date in dates]
        requests = [request.download_list[0] for request in requests]

        self.fetched_data = SentinelHubDownloadClient(config=config).download(
            requests, max_threads=5
        )

        self.gen()

        # center = [min_lat + ((max_lat - min_lat) / 2), min_lon + ((max_lon - min_lon) / 2)]
        # zoom = 13
        # m = Map(basemap=basemaps.OpenTopoMap, center=center, zoom=zoom)
        # m.add_layer(geo_json)
        # m

    def _build_request(self, time_range):
        return SentinelHubRequest(
            evalscript=evalscript,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L2A,
                    time_interval=time_range,
                    mosaicking_order="leastCC",
                    maxcc=0.5,  # fuck clouds
                )
            ],
            responses=[
                SentinelHubRequest.output_response("true_color", MimeType.TIFF),
                SentinelHubRequest.output_response("ndsi", MimeType.TIFF),
            ],
            # Apply the watershed mask
            geometry=Geometry(
                self.river_gdf.geometry.values[0], crs=self.river_gdf.crs
            ),
            bbox=self.bbox,
            size=self.size,
            config=config,
        )

    def gen(self):
        # Process each returned image
        for idx, responses in enumerate(self.fetched_data):
            image = responses["ndsi.tif"]
            height, width, band_count = image.shape

            # Define the metadata
            metadata = {
                "driver": "GTiff",
                "dtype": "uint8",
                "width": width,
                "height": height,
                "count": band_count,
            }

            # Read the image into a rasterio object
            with MemoryFile() as memfile:
                with memfile.open(**metadata) as raster:

                    # rasterio expects the array to be in the order `(bands, height, width)`
                    raster.write(image.transpose(2, 0, 1))

                    rgb_bands = raster.read([1, 2, 3])  # Read RGB bands
                    datamask = raster.read(4)  # Read the datamask band

                # Check the datamask to see if there's actually any data returned
                if not np.any(datamask != 0):
                    continue

                # Normalize true color image for display
                rgb_img = np.moveaxis(rgb_bands, 0, -1)
                rgb_img = rgb_img / np.percentile(rgb_img, 99)

                plt.imsave(f"output/array_image-{idx}.png", rgb_img)


Snowpack("output/watershed - mineral.geojson")
