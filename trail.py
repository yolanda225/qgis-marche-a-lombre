# -*- coding: utf-8 -*-
import math
from qgis.core import (QgsCoordinateTransform, QgsPointXY, QgsGeometry, 
                       QgsRectangle, QgsCoordinateReferenceSystem, QgsProject,
                       QgsRasterLayer)
from .trail_point import TrailPoint

class Trail:
    def __init__(self, max_sep, speed, source_crs, target_crs, transform_context):
        self.speed = (5/18) * speed # km/h to m/s
        self.max_sep = max_sep
        self.src = source_crs
        if not self.src.isValid():
            self.src = QgsCoordinateReferenceSystem("EPSG:4326")
        self.dest = QgsCoordinateReferenceSystem(target_crs)
        self.transform = QgsCoordinateTransform(self.src, self.dest, transform_context)
        self.wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        self.to_wgs84 = QgsCoordinateTransform(self.dest, self.wgs84, transform_context)

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

    def reverse_trail(self, geometry):
        """
        Reverses the direction of the linestring
        """
        nodes = geometry.asPolyline()
        if nodes:
            nodes.reverse()
            return QgsGeometry.fromPolylineXY(nodes)
        return geometry

    def process_trail(self, source_tracks, start_time, break_point, reverse=False):
        self.trail_points = []
        total_dist = 0.0
        center_points = []
        
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

                if reverse:
                    transformed_vertices.reverse()

                # Rebuild geometry in Lambert-93
                new_geom = QgsGeometry.fromPolylineXY(transformed_vertices)
                
                # Densify 
                densified_geom = new_geom.densifyByDistance(self.max_sep)

                # Extract points and calculate Lat/Lon
                verts = densified_geom.vertices()
                prev_pt = None
                
                for v in verts:
                    pt_l93 = QgsPointXY(v.x(), v.y())
                    geo_pt = self.to_wgs84.transform(pt_l93)
                    
                    # Calculate Distance for Time
                    if prev_pt:
                        dist = pt_l93.distance(prev_pt)
                        total_dist += dist

                    seconds_elapsed = total_dist / self.speed
                    current_time = start_time.addSecs(int(seconds_elapsed))
                    
                    # Create TrailPoint object
                    tp = TrailPoint(
                        x=pt_l93.x(),
                        y=pt_l93.y(),
                        z = 0, # implement with MNT
                        lat=geo_pt.y(), # Latitude
                        lon=geo_pt.x(), # Longitude
                        datetime=current_time
                    )
                    
                    center_points.append(tp)
                    prev_pt = pt_l93

        if not center_points:
            raise Exception("No trail points could be processed.")
        
        if break_point:
            # Find the closest point to break location
            closest_idx = 0
            min_dist = float('inf')
            
            for i, tp in enumerate(center_points):
                # Calculate distance
                dist = math.sqrt((tp.x - break_point.x())**2 + (tp.y - break_point.y())**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = i
            
            # Add 1 hour to all points after the break
            if min_dist < 500: # only apply if the point is somewhat near the trail
                print(f"Applying 1h break at point {closest_idx} (Dist: {min_dist:.1f}m)")
                for i in range(closest_idx, len(center_points)):
                    tp = self.center_points[i]
                    tp.datetime = tp.datetime.addSecs(3600)
                    
                    # Recalculate solar position for the new time
                    tp.solar_pos = tp.calc_solar_pos(tp.datetime)
            else:
                 print(f"Break point too far from trail ({min_dist:.1f}m). Ignored.")
        
        # Add center points to main list
        self.trail_points.extend(center_points)

        # Generate Buffer trails
        if buffer:
            left_points = []
            right_points = []
            
            offset_dist = 10.0 # meters
            
            for i in range(len(center_points)):
                current_tp = center_points[i]
                
                # Determine direction
                p1 = current_tp
                p2 = None
                
                if i < len(center_points) - 1:
                    p2 = center_points[i+1]
                elif i > 0:
                    p2 = current_tp
                    p1 = center_points[i-1]
                else:
                    continue
                
                dx = p2.x - p1.x
                dy = p2.y - p1.y
                length = math.sqrt(dx*dx + dy*dy)
                
                if length == 0:
                    ux, uy = 0, 0
                else:
                    ux, uy = dx/length, dy/length
                
                # Normal Vectors (Perpendicular to path)
                # Left Normal: (-uy, ux)
                # Right Normal: (uy, -ux)
                
                # Left point
                lx = current_tp.x + (offset_dist * (-uy))
                ly = current_tp.y + (offset_dist * (ux))
                
                # Convert to Lat/Lon
                try:
                    l_geo = self.to_wgs84.transform(QgsPointXY(lx, ly))
                    
                    tp_left = TrailPoint(
                        x=lx, y=ly, z=0,
                        lat=l_geo.y(), lon=l_geo.x(),
                        datetime=current_tp.datetime
                    )
                    tp_left.trail_type = "Left"
                    tp_left.solar_pos = current_tp.solar_pos
                    left_points.append(tp_left)
                except:
                    pass

                # Right point
                rx = current_tp.x + (offset_dist * (uy))
                ry = current_tp.y + (offset_dist * (-ux))
                
                try:
                    r_geo = self.to_wgs84.transform(QgsPointXY(rx, ry))
                    
                    tp_right = TrailPoint(
                        x=rx, y=ry, z=0,
                        lat=r_geo.y(), lon=r_geo.x(),
                        datetime=current_tp.datetime
                    )
                    tp_right.trail_type = "Right"
                    tp_right.solar_pos = current_tp.solar_pos
                    right_points.append(tp_right)
                except:
                    pass

            self.trail_points.extend(left_points)
            self.trail_points.extend(right_points)

        # Calculate extent
        if self.trail_points:
            temp_points = [QgsPointXY(tp.x, tp.y) for tp in self.trail_points]
            
            multipoint = QgsGeometry.fromMultiPointXY(temp_points)
            self.extent = multipoint.boundingBox()
            # Buffer around extent
            self.extent.grow(500.0)
            
            print(f"Success! Trail Extent: {self.extent.toString()}")
        else:
            raise Exception("No trail points could be processed.")
        
    def sample_elevation(self, mnt_path):
        """
        Loads the MNT raster from the given path and updates
        the z-value of all trail points.
        """
        # Load the MNT as a raster layer
        rlayer = QgsRasterLayer(mnt_path, "mnt_sampling")
        
        if not rlayer.isValid():
            print(f"Error: Could not load MNT from {mnt_path}")
            return

        provider = rlayer.dataProvider()
        
        # Loop through all points and sample the raster
        for tp in self.trail_points:
            val, res = provider.sample(QgsPointXY(tp.x, tp.y), 1)
            
            if res:
                tp.z = val
            else:
                tp.z = 0.0 # Default if outside raster or nodata