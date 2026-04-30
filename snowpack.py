import argparse
import datetime
import json
import os
import sys

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv
from rasterio.io import MemoryFile
from sentinelhub.api.process import SentinelHubRequest
from sentinelhub.config import SHConfig
from sentinelhub.constants import CRS, MimeType
from sentinelhub.data_collections import DataCollection
from sentinelhub.download.sentinelhub_client import SentinelHubDownloadClient
from sentinelhub.geo_utils import bbox_to_dimensions
from sentinelhub.geometry import BBox, Geometry


EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B03", "B11", "B04", "B02", "dataMask"],
    output: [
      { id: "true_color", bands: 4 },
      { id: "ndsi", bands: 4 }
    ]
  };
}

function evaluatePixel(samples) {
    let val = index(samples.B03, samples.B11);

    true_color = [2.5*samples.B04, 2.5*samples.B03, 2.5*samples.B02, samples.dataMask];

    if (val > 0.42)
      ndsi = [0, 0.2, 1, samples.dataMask];  // highlight snow
    else
      ndsi = true_color;

    return {
      true_color: true_color,
      ndsi: ndsi,
    };
}
"""


def _date_range(start: datetime.date, end: datetime.date) -> list[str]:
    assert end > start
    return [
        (start + datetime.timedelta(days=x)).strftime("%Y-%m-%d")
        for x in range((end - start).days + 1)
    ]


def _watershed_bbox(geojson_path: str) -> tuple[BBox, gpd.GeoDataFrame]:
    river_gdf = gpd.read_file(geojson_path).to_crs("WGS84")
    with open(geojson_path) as f:
        coords = json.load(f)["features"][0]["geometry"]["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    bbox = BBox(
        bbox=[(min(lons), max(lats)), (max(lons), min(lats))],
        crs=CRS.WGS84,
    )
    return bbox, river_gdf


class Snowpack:
    def __init__(
        self,
        geojson_filename: str,
        start_date: datetime.date,
        end_date: datetime.date,
        config: SHConfig,
    ):
        self.config = config
        self.bbox, self.river_gdf = _watershed_bbox(geojson_filename)
        self.size = bbox_to_dimensions(self.bbox, resolution=10)

        dates = _date_range(start_date, end_date)
        requests = [self._build_request(date).download_list[0] for date in dates]
        self.fetched_data = SentinelHubDownloadClient(config=self.config).download(
            requests, max_threads=5
        )

    def _build_request(self, time_range: str) -> SentinelHubRequest:
        return SentinelHubRequest(
            evalscript=EVALSCRIPT,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L2A,
                    time_interval=time_range,
                    mosaicking_order="leastCC",
                    maxcc=0.5,
                )
            ],
            responses=[
                SentinelHubRequest.output_response("true_color", MimeType.TIFF),
                SentinelHubRequest.output_response("ndsi", MimeType.TIFF),
            ],
            geometry=Geometry(self.river_gdf.geometry.values[0], crs=self.river_gdf.crs),
            bbox=self.bbox,
            size=self.size,
            config=self.config,
        )

    def gen(self, output_dir: str) -> None:
        os.makedirs(output_dir, exist_ok=True)
        for idx, responses in enumerate(self.fetched_data):
            image = responses["ndsi.tif"]
            height, width, band_count = image.shape

            metadata = {
                "driver": "GTiff",
                "dtype": "uint8",
                "width": width,
                "height": height,
                "count": band_count,
            }

            with MemoryFile() as memfile:
                with memfile.open(**metadata) as raster:
                    raster.write(image.transpose(2, 0, 1))
                    rgb_bands = raster.read([1, 2, 3])
                    datamask = raster.read(4)

                if not np.any(datamask != 0):
                    continue

                rgb_img = np.moveaxis(rgb_bands, 0, -1)
                rgb_img = rgb_img / np.percentile(rgb_img, 99)
                plt.imsave(os.path.join(output_dir, f"array_image-{idx}.png"), rgb_img)


def _parse_date(s: str) -> datetime.date:
    return datetime.datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate snow-cover images for a watershed from Sentinel-2 imagery."
    )
    parser.add_argument("geojson", help="Path to watershed GeoJSON file")
    parser.add_argument(
        "--start",
        type=_parse_date,
        default=datetime.date(2024, 5, 1),
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=_parse_date,
        default=datetime.date(2024, 5, 22),
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument("--output", default="output", help="Output directory for PNGs")
    args = parser.parse_args()

    load_dotenv()
    client_id = os.environ.get("SH_CLIENT_ID")
    client_secret = os.environ.get("SH_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("error: SH_CLIENT_ID and SH_CLIENT_SECRET environment variables required")

    config = SHConfig()
    config.sh_client_id = client_id
    config.sh_client_secret = client_secret

    snow = Snowpack(args.geojson, args.start, args.end, config)
    snow.gen(args.output)


if __name__ == "__main__":
    main()
