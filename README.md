# Marche à l'ombre - QGIS Plugin

Calculate shady and sunny portions of a given hiking trail using time of departure, the calculated solar positions per trail point and terrain/surface elevation data

## Description

This plugin analyzes hiking trails to determine which parts will be in shadow or sunlight at specific times of day. It uses:
- IGN LiDAR HD elevation data (MNS/MNT)
- Sun position calculations based on datetime and location

## Features

- Dynamic layer retrieval from IGNs Web Map Service (https://data.geopf.fr/wms-r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities)
- Adjustable hiking speed and picnic break
- Reversal of trail
- Buffered calculation (calculation also 10m to the right and left of the trail to )
- Vector output with color-coded trail segments
- Statistics output (percentage sunny, etc.)

## Requirements

- QGIS 3.0 or later
- Internet connection (to download elevation data from IGN)
- Python dependencies (included in QGIS):
  - numpy
  - gdal
- not included in QGIS (optional).
  - pvlib (If not installed, a manual solar position calculation is used)

## Usage

1. Dowload a GPX hiking trail (e.g. from Visorando)
2. Load the GPX layer in QGIS
3. Run the plugin from the Processing Toolbox: `Marche à l'ombre`
3. Input the track layer and set departure date/time and hiking parameters
4. Run the Plugin

## Installation

1. Download repository
2. Compress to ZIP-file
3. Open QGIS and go to Plugins → Manage and Install Plugins
4. Select Install from ZIP

## Coverage

Works for trails in:
- France Métropole
- La Réunion
- Guadeloupe
- Support for possible future IGN elevation data 

## License

GPL v2 or later

## Issues

Report bugs at: https://github.com/yolanda225/qgis-marche-a-lombre/issues