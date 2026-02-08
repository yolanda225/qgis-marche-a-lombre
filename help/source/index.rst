.. MarcheALOmbre documentation master file, created by
   sphinx-quickstart on Sun Feb 12 17:11:03 2012.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to MarcheALOmbre's documentation!
============================================

Contents:

.. toctree::
   :maxdepth: 2

   api/modules

Overview
--------

**Marche à l'ombre** calculates the shady and sunny portions of a given hiking trail in France, using time of departure, the calculated solar positions per trail point and terrain/surface elevation data

The plugin uses:

* IGN LiDAR HD elevation data (MNS/MNT)
* Sun position calculations based on datetime and location

Features
--------

* Dynamic layer retrieval from IGNs Web Map Service (https://data.geopf.fr/wms*r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities)
* Adjustable hiking speed and picnic break
* Reversal of trail
* Buffered calculation (calculation also 5m to the right and left of the trail to visualize shadow next to trail)
* Vector output with color-coded trail segments
* Statistics output (percentage sunny, etc.)

Requirements
------------

* QGIS 3.0 or later
* Internet connection (to download elevation data from IGN)
* Python dependencies (included in QGIS):
  
  * numpy
  * gdal
* Python dependencies (optional and not included in QGIS):

  * pvlib (If not installed, a manual solar position calculation is used)

Installation
------------

From QGIS Plugin Repository
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open QGIS
2. Go to **Plugins → Manage and Install Plugins**
3. Search for "Marche à l'ombre"
4. Click **Install**

Manual Installation
~~~~~~~~~~~~~~~~~~~

1. Download repository (https://github.com/yolanda225/qgis-marche-a-lombre)
2. Compress to ZIP-file
3. Open QGIS and go to **Plugins → Manage and Install Plugins**
4. Select **Install from ZIP**

Usage
-----

Basic Workflow
~~~~~~~~~~~~~~

1. Dowload a GPX hiking trail (e.g. from Visorando)
2. Load the GPX layer in QGIS
3. Open the plugin and configure parameters
4. Click **Run**

Parameters
~~~~~~~~~~

**Input layer**
  Vector line layer representing your hiking trail (**tracks**)

**Departure Date and Time**
  The date and time when you start your hike (Local Time): used to calculate solar position throughout the trail

**Average Hiking Speed (km/h)**
  Your expected hiking speed (default: 5.0 km/h)

**Adjust hiking speed for slope**
  Adjust your hiking speed using Tobler's hiking function

**Picnic Break Location** (optional)
  Click on the map to set a break point (button to the right of the input box)

**Picnic Duration (minutes)** (optional)
  How long your break will last (default: 60 minutes)

**Reverse Trail Direction**
  Walk from finish to start instead of start to finish

**Calculate with Buffer**
  Calculate for center, left 5m, and right 5m of trail to visualize shadow next to trail

Outputs
~~~~~~~

The plugin generates:

* **MNS**: High-resolution surface model around trail
* **Low Resolution MNS**: Larger surface model for long shadows
* **Densified Trail Points**: Color-coded points showing sun/shadow status
  
  * 🟡 Gold arrows = Sun
  * 🔵 Blue arrows = Shadow

* **Statistics Table (CSV)**: Summary of time in sun vs shadow

Coverage
--------

Works for trails in:

* France Métropole
* Guadeloupe
* Réunion
* Support for possible future IGN surface elevation data of Overseas France is integrated

Troubleshooting
---------------

**Bad request /Failed to dowload data**
  Might be an issue on the servers side, try again.

**"No candidates found" error**
  The trail may be outside supported regions or no data is available (France and French territories).

License
-------

GPL v2 or later

Author
------

Yolanda Seifert

Support
-------

* GitHub Issues: https://github.com/yolanda225/qgis-marche-a-lombre/issues
* Repository: https://github.com/yolanda225/qgis-marche-a-lombre