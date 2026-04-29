<p align="center">
  <img src="static/logo.webp" width=200>
  <h1>Watershed</h1>
</p>
<p>

A system for automatically calculating the watershed catchment from a set of coordinates.

Leverages digital elevation models (DEMs) accessed via [OpenTopography](https://opentopography.org/).

Outputs KML & GeoJson files, useful for importing into other tools.

Tries to integrate with [CalTopo](https://caltopo.com/) (e.g. importing initial coordinates, automatically load exported kml).

DEMs currently supported:

* [USGS10m 1/3 arc-second](https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.012021.4269.1]) (covers ~USA)
* [USGS30m 1 arc-second](https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.012021.4269.2) (covers ~North America)

Coverage maps on the respective pages linked above.
</p>

## Running as a systemd user service

A `watershed.service` unit file is included for running under systemd as a user service.

```bash
mkdir -p ~/.config/systemd/user
cp watershed.service ~/.config/systemd/user/
# edit the file to set OT_API_KEY=...
systemctl --user daemon-reload
systemctl --user enable --now watershed
```

View logs with `journalctl --user -u watershed -f`.

The unit assumes the repo is checked out at `~/watershed` with a venv at `~/watershed/venv`.
