# -*- coding: utf-8 -*-
REGIONS = {
        'Guadeloupe_Martinique': {
            'bbox': [-63.5, 14.0, -60.0, 18.5], 
            'epsg': 'EPSG:5490' # RGAF09 / UTM zone 20N
        },
        'Guyane': {
            'bbox': [-55.0, 2.0, -51.0, 6.0], 
            'epsg': 'EPSG:2972' # RGFG95 / UTM zone 22N
        },
        'Reunion': {
            'bbox': [55.0, -22.0, 56.0, -20.5], 
            'epsg': 'EPSG:2975' # RGR92 / UTM zone 40S
        },
        'Mayotte': {
            'bbox': [44.5, -13.5, 45.5, -12.0], 
            'epsg': 'EPSG:4471' # RGM04 / UTM zone 38S
        },
        'Saint_Pierre_et_Miquelon': {
            'bbox': [-57.0, 46.5, -56.0, 47.5], 
            'epsg': 'EPSG:4467' # RGSPM06 / UTM zone 21N
        },
        'France_Metropole': {
            'bbox': [-6.0, 41.0, 10.0, 52.0], 
            'epsg': 'EPSG:2154' # Lambert-93 (including Corsica)
        }
    }

# Manual definitions for regions to bypass missing grids/defs on Linux
MANUAL_DEFS = {
    "EPSG:2154": "+proj=lcc +lat_1=44 +lat_2=49 +lat_0=46.5 +lon_0=3 +x_0=700000 +y_0=6600000 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs", # France
    "EPSG:5490": "+proj=utm +zone=20 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs", # Guadeloupe/Martinique
    "EPSG:2972": "+proj=utm +zone=22 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs", # Guyane
    "EPSG:2975": "+proj=utm +zone=40 +south +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs", # Reunion
    "EPSG:4471": "+proj=utm +zone=38 +south +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs", # Mayotte
    "EPSG:4467": "+proj=utm +zone=21 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs"  # St Pierre et Miquelon
}