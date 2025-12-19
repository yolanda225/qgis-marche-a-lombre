# -*- coding: utf-8 -*-
from qgis.core import (QgsCoordinateTransform, QgsPointXY, QgsGeometry, 
                       QgsRectangle, QgsCoordinateReferenceSystem, QgsProject)

class Trail:
    def __init__(self, max_sep, speed, source_crs, target_crs, transform_context):
        self.speed = speed
        self.max_sep = max_sep
        self.src = source_crs
        if not self.src.isValid():
            self.src = QgsCoordinateReferenceSystem("EPSG:4326")
        self.dest = QgsCoordinateReferenceSystem(target_crs)
        self.transform = QgsCoordinateTransform(self.src, self.dest, transform_context)

        # Manually define Lambert-93 if missing grids on Linux by using its raw Proj4 string
        if not self.transform.isValid():
            print("WARNING: Standard EPSG:2154 failed. Switching to Manual Definition (Bypass Mode).")
            
            # Raw mathematical definition of Lambert-93
            lambert_93_manual = "+proj=lcc +lat_1=44 +lat_2=49 +lat_0=46.5 +lon_0=3 +x_0=700000 +y_0=6600000 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs"
            
            self.dest = QgsCoordinateReferenceSystem.fromProj4(lambert_93_manual)
            self.transform = QgsCoordinateTransform(self.src, self.dest, QgsProject.instance())
            self.transform.setBallparkTransformsAreAppropriate(True)

        if not self.transform.isValid():
             raise Exception("CRITICAL: Lambert-93 could not be initialized even with manual definition.")

        self.trail_points = []
        self.extent = QgsRectangle()

    def process_trail(self, source_tracks):
        self.trail_points = []
        
        for feature in source_tracks.getFeatures():
            geom = feature.geometry()
            if geom.isEmpty():
                continue

            # Standardize geometry to list of lines
            if geom.isMultipart():
                lines = geom.asMultiPolyline()
            else:
                lines = [geom.asPolyline()]

            for line in lines:
                transformed_vertices = []
                for pt in line:
                    try:
                        # Transform point
                        trans_pt = self.transform.transform(QgsPointXY(pt))
                        transformed_vertices.append(trans_pt)
                    except:
                        continue
                
                if not transformed_vertices:
                    continue

                # Rebuild geometry in Lambert-93
                new_geom = QgsGeometry.fromPolylineXY(transformed_vertices)
                
                # Densify 
                densified_geom = new_geom.densifyByDistance(self.max_sep)
                
                for v in densified_geom.vertices():
                    self.trail_points.append(QgsPointXY(v.x(), v.y()))

        if self.trail_points:
            multipoint = QgsGeometry.fromMultiPointXY(self.trail_points)
            self.extent = multipoint.boundingBox()
            # Buffer around extent
            self.extent.grow(500.0)
            
            print(f"Success! Trail Extent: {self.extent.toString()}")
        else:
            raise Exception("No trail points could be processed.")