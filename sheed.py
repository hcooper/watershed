#!/usr/bin/env python3
from pysheds.grid import Grid
import numpy as np
import simplekml
import aiohttp
import logging
import geojson
import os
import uuid
from aiohttp import web
from typing import List
import sys
import urllib.parse
from shapely.geometry import shape as shapely_shape
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)

access_log = logging.getLogger("aiohttp.access")
access_log.setLevel(logging.INFO)
handler = logging.FileHandler("access.log")
formatter = logging.Formatter("%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
access_log.addHandler(handler)
# access_log.propagate = False


def make_id() -> str:
    return str(uuid.uuid4())[:4]


class Watershed:
    def __init__(
        self, lat: float, lon: float, name: str, expand_factor: float, client_id, dem
    ):

        self.id = client_id  # if client_id else make_id()
        self.outdir = "output"
        os.makedirs(self.outdir, exist_ok=True)
        
        self.lat = lat
        self.lon = lon
        self.expand_factor = expand_factor
        self.dem = dem

        if not name:
            self._generate_default_name()
        else:
            self.name = name

        self.generate_box()

    def _generate_default_name(self):
        self.name = f"{self.lat}_{self.lon}_{self.expand_factor}"

    def generate_box(self):
        self.min_x, self.min_y, self.max_x, self.max_y = [
            round(self.lon - self.expand_factor, 5),
            round(self.lat - self.expand_factor, 5),
            round(self.lon + self.expand_factor, 5),
            round(self.lat + self.expand_factor, 5),
        ]

    async def _log(self, msg):
        log_message = f"[{self.id}] {msg}"
        logging.info(log_message)
        await broadcast_message(f"log:{log_message}", self.id)

    async def work(self):
        self.dem_filename = await self.get_dem()
        self.catchment_shapes = await self.calculate_catchment()
        self.clipped = await self.clipping_check()

        if self.clipped:
            await self._log("Clipping detected, retrying with expand_factor=0.1")
            self.expand_factor = 0.1
            self.generate_box()
            self._generate_default_name()

            self.dem_filename = await self.get_dem()
            self.catchment_shapes = await self.calculate_catchment()
            self.clipped = await self.clipping_check()

        self.geojson = await self.export_geojson()
        self.kml = await self.export_kml()
        await self._log("Done!")

    async def get_dem(self) -> str:
        dataset = self.dem

        dem_filename = f"{self.outdir}/dem_{dataset}_{self.name}.tif"

        # Use cached DEM if possible
        if os.path.isfile(dem_filename):
            await self._log(f"Using cached DEM {dem_filename}")
            return dem_filename

        params = {
            "datasetName": dataset,
            "west": self.min_x,
            "south": self.min_y,
            "east": self.max_x,
            "north": self.max_y,
            "outputFormat": "GTiff",
            "API_Key": OT_API_KEY,
        }

        dem_filename = f"{self.outdir}/dem_{dataset}_{self.name}.tif"

        # Construct the API URL
        base_url = "https://portal.opentopography.org/API/usgsdem"

        await self._log(
            f"Fetching {dataset} DEM centered on {self.lat},{self.lon} from opentopography.org..."
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(dem_filename, "wb") as file:
                        file.write(content)
                    await self._log(f"{dem_filename} downloaded successfully.")
                else:
                    await self._log(f"Error: {response.status}. Request was {params}")
                    await self._log(await response.text())
                    raise
        return dem_filename

    async def calculate_catchment(self) -> List:
        if not self.dem_filename:
            raise

        await self._log("Preparing DEM")
        grid = Grid.from_raster(self.dem_filename)
        dem = grid.read_raster(self.dem_filename)

        pit_filled_dem = grid.fill_pits(dem)
        flooded_dem = grid.fill_depressions(pit_filled_dem)
        inflated_dem = grid.resolve_flats(flooded_dem)

        dirmap = (64, 128, 1, 2, 4, 8, 16, 32)

        await self._log("Calculating catchment")
        fdir = grid.flowdir(inflated_dem, dirmap=dirmap)
        acc = grid.accumulation(fdir, dirmap=dirmap)

        # Snap pour point to high accumulation cell
        x_snap, y_snap = grid.snap_to_mask(acc > 1000, (self.lon, self.lat))

        # Delineate the catchment
        catch = grid.catchment(
            x=x_snap, y=y_snap, fdir=fdir, dirmap=dirmap, xytype="coordinate"
        )

        grid.clip_to(catch)
        catch_view = grid.view(catch, dtype=np.uint8)

        shapes = [shape for shape in grid.polygonize(catch_view)]
        # assert len(shapes) == 1  # Can't have multiple watersheds

        return shapes

    async def clipping_check(self) -> bool:
        """
        Detect if the catchment polygon comes close to the edge of the DEM. If so,
        it's likely the catchment has been clipped and the DEM should be enlarged.
        """

        shape = self.catchment_shapes[0][0]

        catchment_polygon = shapely_shape(shape)

        for x, y in catchment_polygon.exterior.coords:
            d = min(
                [
                    abs(self.max_x - x),
                    abs(self.min_x - x),
                    abs(self.max_y - y),
                    abs(self.min_y - y),
                ]
            )
            if d < 0.0002:  # the magic number
                await self._log(f"Clipping detected: {y},{x} {d}")
                return True
        return False

    async def export_geojson(self) -> str:
        if not self.catchment_shapes:
            raise

        features = []

        for shape in self.catchment_shapes:
            geo_polygon = geojson.Polygon([(shape[0]["coordinates"][0])])
            geo_polygon_feature = geojson.Feature(
                geometry=geo_polygon, properties={"name": "Example Polygon"}
            )
            features.append(geo_polygon_feature)

        filename = f"{self.outdir}/watershed - {self.name}.geojson"
        with open(f"{filename}", "w") as f:
            geojson.dump(geojson.FeatureCollection(features), f)
        await self._log(f'GeoJSON generated: "{filename}"')
        return filename

    async def export_kml(self) -> str:
        if not self.catchment_shapes:
            raise

        filename = f"{self.outdir}/watershed_-_{self.name}.kml"

        kml = simplekml.Kml()
        kml.newpoint(
            name=f"Watershed Calculation Point - {self.name}",
            coords=[(self.lon, self.lat)],
        )

        for shape in self.catchment_shapes:
            poly = kml.newpolygon(name=f"Watershed - {self.name}")
            poly.outerboundaryis = shape[0]["coordinates"][0]
            poly.style.linestyle.color = simplekml.Color.blue
            poly.style.linestyle.width = 1
            poly.style.polystyle.color = simplekml.Color.changealphaint(
                20, simplekml.Color.blue
            )

        kml.save(filename)
        await self._log(f'KML generated: "{filename}"')
        return filename


async def handle_index(request):
    with open("static/index.html") as f:
        index = f.read()
        return web.Response(text=index, content_type="text/html")


async def handle_submit(request):
    if request.content_type == "application/json":
        data = await request.json()
    elif request.content_type == "application/x-www-form-urlencoded":
        data = await request.post()
    else:
        return web.Response(text="Unsupported content type", status=400)

    try:
        coordinates = data["coordinates"]
        lat, lon = map(float, coordinates.split(","))
        name = data["name"]
        expand_factor = float(data["expand_factor"])
        client_id = data["client_id"]
        dem = data["dem"]

    except (KeyError, ValueError):
        return web.Response(text="Invalid input", status=400)

    watershed = Watershed(lat, lon, name, expand_factor, client_id, dem)
    await watershed.work()

    response_content = {}

    response_content['clipped'] = watershed.clipped
    response_content['dem'] = watershed.dem
    response_content['expand_factor'] = watershed.expand_factor
    response_content['geojson'] = watershed.geojson
    response_content['kml'] = watershed.kml
    response_content['lat'] = watershed.lat
    response_content['lon'] = watershed.lon
    response_content['name'] = watershed.name

    # if watershed.clipped:python
        # response_content += "<div class='warning'>Warning: clipping was detected!</div>"

    # Caltopo badly handles spaces in the kml url, even when they're encoded as %20. Instead
    # you have to double-encode the "%" as "%25".
    # kml_url = urllib.parse.quote(
    #     f"https://watershed.attack-kitten.com/{watershed.kml}", safe=""
    # ).replace("%20", "%2520")
    # caltopo_url = f"http://caltopo.com/map.html#ll={lat},{lon}&z=13&kml={kml_url}"
    # response_content += (
    #     f"<a href='{caltopo_url}' class='button-link' target='_new'>Open in Caltopo</a>"
    # )

    return web.Response(text=json.dumps(response_content), content_type="text/json")


async def broadcast_message(message, client_id=None) -> None:
    if client_id:
        ws = clients[client_id]
        await ws.send_str(message)
    else:
        for ws in clients.values():
            await ws.send_str(message)


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    client_id = make_id()
    clients[client_id] = ws

    await ws.send_str(f"client_id:{client_id}")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                if msg.data == "close":
                    await ws.close()
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f"WebSocket connection closed with exception {ws.exception()}")

    finally:
        clients.pop(client_id)

    return ws

OT_API_KEY = os.getenv("OT_API_KEY")
if not OT_API_KEY:
    print("Error: OT_API_KEY must be set (Opentopography.org API Key)")
    sys.exit(1)

os.makedirs("output/", exist_ok=True)
os.makedirs("static/", exist_ok=True)

print("Directories made")

app = web.Application()
app.router.add_get("/", handle_index)
app.router.add_post("/", handle_submit)
app.router.add_static(prefix="/output", path="output/", show_index=True)
app.router.add_static(prefix="/static", path="static/", show_index=False)
app.router.add_get("/ws", websocket_handler)

clients = {}

if __name__ == "__main__":
    print("Starting web...")
    web.run_app(app, host="0.0.0.0", port=8080, access_log=access_log)
