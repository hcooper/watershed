# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Watershed is a Python web application that calculates watershed catchments from geographic coordinates using USGS DEM data. It provides both KML and GeoJSON outputs for integration with mapping tools like CalTopo.

## Commands

### Running the Application
```bash
python sheed.py
```
Starts the web server on port 8080. Requires OT_API_KEY environment variable (OpenTopography API key).

### Dependencies
```bash
pip install -r requirements.txt
```

### Docker Deployment
```bash
docker build -t watershed .
docker run -p 8080:8080 -e OT_API_KEY=your_key watershed
```

### Fly.io Deployment
```bash
fly deploy
```
App is configured for the 'sea' region with 1GB memory.

## Architecture

### Core Components

- **sheed.py**: Main application file containing the complete web server and watershed calculation logic
- **Watershed class**: Handles DEM fetching, watershed calculation, and output generation
- **Web interface**: aiohttp-based server with WebSocket support for real-time logging
- **Frontend**: Static HTML/CSS/JS in `/static/` directory

### Key Dependencies

- **pysheds**: Primary watershed calculation engine using flow direction algorithms
- **aiohttp**: Async web framework for the server
- **simplekml**: KML file generation
- **geojson**: GeoJSON output format
- **shapely**: Geometry operations for clipping detection

### Data Flow

1. User submits coordinates via web form
2. System fetches DEM data from OpenTopography API
3. pysheds processes DEM for flow direction and accumulation
4. Watershed catchment is calculated using flow algorithms
5. Clipping detection checks if watershed extends beyond DEM bounds
6. If clipped, automatically retries with larger expand_factor
7. Outputs generated as both KML and GeoJSON files
8. Files served via static file endpoints

### Configuration

- OT_API_KEY environment variable required for OpenTopography API access
- Output files stored in `/output/` directory
- WebSocket client management for real-time progress updates
- Snap-to-river functionality moves calculation point to nearest high-accumulation cell