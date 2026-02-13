# -*- coding: utf-8 -*-
"""
Part of MarcheALOmbre QGIS Plugin
Copyright (C) 2025 Yolanda Seifert
Licensed under GPL v2+
"""
import math
from qgis.core import (QgsCoordinateTransform, QgsPointXY, QgsGeometry, 
                       QgsRectangle, QgsCoordinateReferenceSystem,
                       QgsRasterLayer, QgsWkbTypes)
from .trail_point import TrailPoint
from .geo_definitions import REGIONS, MANUAL_DEFS

class Trail:
    def __init__(self, max_sep, speed, source_crs, transform_context, feedback=None):
        """
        Initializes the Trail

        Args:
            max_sep (float): Maximum separation distance (in meters) between points after densification
            speed (float): Average hiking speed in km/h
            source_crs (QgsCoordinateReferenceSystem): The CRS of the input vector layer
            transform_context (QgsCoordinateTransformContext): Context for coordinate transformations
            feedback (QgsProcessingFeedback, optional): Feedback object for reporting logs
        """
        self.speed = (5/18) * speed # km/h to m/s
        self.max_sep = max_sep
        self.src = source_crs
        if not self.src.isValid():
            self.src = QgsCoordinateReferenceSystem("EPSG:4326")
        self.transform_context = transform_context
        self.wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        self.trail_points = []
        self.extent = QgsRectangle()
        self.feedback = feedback
        self.center_lat = 0.0
        self.break_index = -1
        self.break_duration = 0

    def log(self, message):
        """
        Logs a message to the feedback object

        Args:
            message (str): The message to log
        """
        if self.feedback:
            self.feedback.pushInfo(message)
        else:
            print(message)

    def _determine_best_crs(self, wgs84_extent):
        """
        Check which region contains the center of the trail extent

        Args:
            wgs84_extent (QgsRectangle): The extent of the layer in WGS84.

        Returns:
            tuple: A tuple containing (epsg_code (str), region_name (str)).
        """
        center = wgs84_extent.center()
        lon = center.x()
        lat = center.y()

        for name, data in REGIONS.items():
            b = data['bbox']
            # Bounding box check
            if b[0] <= lon <= b[2] and b[1] <= lat <= b[3]:
                return data['epsg'], name
        
        # Default to France
        return "EPSG:2154", "France_Metropole (Default)"

    def reverse_trail(self, geometry):
        """
        Reverses the order of the linestring

        Args:
            geometry (QgsGeometry): The input linestring geometry

        Returns:
            QgsGeometry: New linestring with reversed vertices
        """
        nodes = geometry.asPolyline()
        if nodes:
            nodes.reverse()
            return QgsGeometry.fromPolylineXY(nodes)
        return geometry
    
    def calc_meridian_convergence(self, source_center):
        """Calculates Meridian Convergence correction

        Args:
            source_center (QgsPointXY): Center point of trail extent

        Returns:
            float: Convergence value
        """
        convergence = 0.0
        try:
            center_l93 = self.transform.transform(source_center)
            center_geo = self.to_wgs84.transform(center_l93)
            # Create point slightly North (True North)
            north_geo = QgsPointXY(center_geo.x(), center_geo.y() + 0.1) 
            north_l93 = self.to_wgs84.transform(north_geo, QgsCoordinateTransform.ReverseTransform)
            
            # Calculate angle of the "True North" vector relative to Grid North (Y-axis)
            dx = north_l93.x() - center_l93.x()
            dy = north_l93.y() - center_l93.y()
            convergence = math.atan2(dx, dy)
            self.log(f"Meridian Convergence at trail center: {math.degrees(convergence):.4f} deg")

        except Exception as e:
            self.log(f"Warning: Could not calculate convergence: {e}. Defaulting to 0.")
        return convergence

    def process_trail(self, source_tracks, start_time, break_point, picnic_duration=0, reverse=False, buffer=False, project_crs=None, adjust_for_slope=False):
        """Processes input GPX source tracks into a list of TrailPoint objects

        Args:
            source_tracks (QgsProcessingFeatureSource]): Tracks from the gpx trail
            start_time (QDateTime): Hikers time of departure
            break_point ( QgsPointXY): Coordinates of an optional picnic point
            picnic_duration (float): Duration of the hikers picnic break (minutes)
            reverse (bool, optional): Optional reversing of the trails direction. Defaults to False.
            buffer (bool, optional): Optional buffering so that 10m left and right of the trail buffer trails are formed. Defaults to False.
            project_crs (QgsCoordinateReferenceSystem, optional): The CRS for transforming break_point. Defaults to None.
            adjust_for_slope (bool): If to adjust speed based on terrain slope. Defaults to False.

        Raises:
            Exception: If coordinate transformation fails or no valid trail points are generated
        """
        # Validate user input
        if QgsWkbTypes.geometryType(source_tracks.wkbType()) != QgsWkbTypes.LineGeometry:
            raise Exception("Input layer must be a Line layer (LineString or MultiLineString).")

        if source_tracks.featureCount() == 0:
            raise Exception("Input layer contains no features. If using a GPX file, ensure you selected 'tracks' and not 'routes'.")
        
        wgs84_extent = source_tracks.sourceExtent()
        self.center_lat = wgs84_extent.center().y()
        self.adjust_for_slope = adjust_for_slope

        self.target_crs, region_name = self._determine_best_crs(source_tracks.sourceExtent())
        self.log(f"Detected Region: {region_name}. Switching to CRS: {self.target_crs}")
        dest_crs = QgsCoordinateReferenceSystem(self.target_crs)
        self.transform = QgsCoordinateTransform(self.src, dest_crs, self.transform_context)
        self.to_wgs84 = QgsCoordinateTransform(dest_crs, self.wgs84, self.transform_context)

        # Check if standard transformation failed if missing grids on machine
        auth_id = dest_crs.authid()
        if not self.transform.isValid() and auth_id in MANUAL_DEFS:
            print(f"WARNING: Standard {auth_id} failed. Switching to Manual Definition.")
            # Create CRS from raw Proj4 string
            dest_crs = QgsCoordinateReferenceSystem.fromProj4(MANUAL_DEFS[auth_id])
            # Redo tranformations
            self.transform = QgsCoordinateTransform(self.src, dest_crs, self.transform_context)
            self.transform.setBallparkTransformsAreAppropriate(True)
            self.to_wgs84 = QgsCoordinateTransform(dest_crs, self.wgs84, self.transform_context)
            self.to_wgs84.setBallparkTransformsAreAppropriate(True)

        if not self.transform.isValid():
             raise Exception(f"CRITICAL: Transformation to {dest_crs.authid()} could not be initialized.")
        
        # Transform break_point from project CRS to target CRS if provided
        transformed_break_point = None
        if break_point and project_crs:
            # Create transformation from project CRS to target CRS
            project_to_target = QgsCoordinateTransform(project_crs, dest_crs, self.transform_context)
            
            # Try manual fallback if standard transformation fails
            if not project_to_target.isValid():
                project_auth = project_crs.authid()
                if project_auth in MANUAL_DEFS and auth_id in MANUAL_DEFS:
                    print(f"WARNING: Standard transformation {project_auth} -> {auth_id} failed. Using manual fallback.")
                    project_to_target = QgsCoordinateTransform(project_crs, dest_crs, self.transform_context)
                    project_to_target.setBallparkTransformsAreAppropriate(True)
            
            try:
                transformed_break_point = project_to_target.transform(break_point)
                self.log(f"Transformed break point from {project_crs.authid()} to {dest_crs.authid()}")
                print(f"Break point: {break_point.x():.2f}, {break_point.y():.2f} ({project_crs.authid()}) -> {transformed_break_point.x():.2f}, {transformed_break_point.y():.2f} ({dest_crs.authid()})")
            except Exception as e:
                print(f"ERROR: Failed to transform break point: {e}")
                transformed_break_point = None

        meridian_convergence = self.calc_meridian_convergence(source_tracks.sourceExtent().center())
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
                try:
                    lines = [geom.asPolyline()]
                except Exception as e:
                    raise Exception(f"{e}. Input layer must be tracks.")
            

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

                    if adjust_for_slope:
                        current_time = start_time  # Placeholder, will recalculate
                    else:
                        seconds_elapsed = total_dist / self.speed
                        current_time = start_time.addSecs(int(seconds_elapsed))
                    
                    # Create TrailPoint object
                    tp = TrailPoint(
                        x=pt_l93.x(),
                        y=pt_l93.y(),
                        z = 0, # implement with MNT
                        lat=geo_pt.y(), # Latitude
                        lon=geo_pt.x(), # Longitude
                        datetime=current_time,
                        convergence=meridian_convergence
                    )
                    
                    center_points.append(tp)
                    prev_pt = pt_l93

        if not center_points:
            raise Exception("No trail points could be processed. Input layer must be tracks.")
        
        if total_dist > 45000:
            self.log(f"WARNING: Trail length is {total_dist/1000:.1f} km, Processing may be slow.")
        
        if transformed_break_point:
            # Find the closest point to break location
            closest_idx = 0
            min_dist = float('inf')
            
            for i, tp in enumerate(center_points):
                # Calculate distance
                dist = math.sqrt((tp.x - transformed_break_point.x())**2 + (tp.y - transformed_break_point.y())**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = i
            
            # Add 1 hour to all points after the break
            if min_dist < 5000: # only apply if the point is somewhat near the trail
                print(f"Applying 1h break at point {closest_idx} (Dist: {min_dist:.1f}m)")
                self.break_index = closest_idx
                self.break_duration = int(60 * picnic_duration)
                for i in range(closest_idx, len(center_points)):
                    tp = center_points[i]
                    tp.datetime = tp.datetime.addSecs(int(60*picnic_duration))
                    
                    # Recalculate solar position for the new time
                    tp.solar_pos = tp.calc_solar_pos(tp.datetime)
            else:
                 self.log(f"Break point too far from trail ({min_dist:.1f}m). Ignored.")
        
        # Add center points to main list
        self.trail_points.extend(center_points)

        # Generate Buffer trails
        if buffer:
            left_points = []
            right_points = []
            
            offset_dist = 5.0 # meters
            
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
                        datetime=current_tp.datetime,
                        convergence=meridian_convergence
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
                        datetime=current_tp.datetime,
                        convergence=meridian_convergence
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
        
    def calculate_times_with_slope(self, start_time, buffered):
        """
        Recalculate arrival times for all trail points accounting for slope
        Must be called after sample_elevation() has populated z values
        
        Uses Tobler's hiking function:
        - Flat terrain: base speed
        - Uphill: speed decreases
        - Downhill: speed increases

        Args:
            start_time (QDateTime): Start time for recalculating arrival times
            buffer (bool): If True, only calculate for center trail and copy times to left/right
        """
        if not self.trail_points:
            return
        
        self.log(f"Recalculating times with slope adjustment using Tobler's hiking function...")
        
        # Determine which points to calculate
        if buffered:
            num_points = len(self.trail_points)
            center_count = num_points // 3
            points_to_calculate = self.trail_points[:center_count]
        else:
            points_to_calculate = self.trail_points
        
        # Calculate times
        total_time = 0.0  # seconds
        points_to_calculate[0].datetime = start_time
        
        for i in range(1, len(points_to_calculate)):
            prev_tp = points_to_calculate[i-1]
            curr_tp = points_to_calculate[i]
            
            # Horizontal distance
            dist_horizontal = math.sqrt(
                (curr_tp.x - prev_tp.x)**2 + 
                (curr_tp.y - prev_tp.y)**2
            )
            
            if self.adjust_for_slope and dist_horizontal > 0:
                # Calculate slope
                delta_z = curr_tp.z - prev_tp.z
                slope = delta_z / dist_horizontal
                
                # Tobler's hiking function
                speed_factor = math.exp(-3.5 * abs(slope + 0.05))

                # Limit speed between 30% and 150% of base speed
                speed_factor = max(0.3, min(speed_factor, 1.5))
                
                adjusted_speed = self.speed * speed_factor
            else:
                adjusted_speed = self.speed
            
            # Update time
            segment_time = dist_horizontal / adjusted_speed
            total_time += segment_time
            if i == self.break_index:
                total_time += self.break_duration
            curr_tp.datetime = start_time.addSecs(int(total_time))
            # Recalculate solar position since the time changed
            curr_tp.solar_pos = curr_tp.calc_solar_pos(curr_tp.datetime)
        
        # If buffered, copy times from center to left and right trails
        if buffered:
            left_points = self.trail_points[center_count:2*center_count]
            right_points = self.trail_points[2*center_count:]
            
            for i in range(len(points_to_calculate)):
                if i < len(left_points):
                    left_points[i].datetime = points_to_calculate[i].datetime
                    left_points[i].solar_pos = points_to_calculate[i].solar_pos
                if i < len(right_points):
                    right_points[i].datetime = points_to_calculate[i].datetime
                    right_points[i].solar_pos = points_to_calculate[i].solar_pos
        
        self.log(f"Time calculation complete. Total hiking time: {total_time/3600:.2f} hours")
        
    def sample_elevation(self, mnt_path, start_time, buffered):
        """
        Loads the MNT raster from the given path and updates the z-value of all trail points

        Args:
            mnt_path (str): File path to the MNT raster
            start_time (QDateTime): Start time for recalculating arrival times
            buffer (bool): For time recalculation in calculate_times_with_slope
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
        
        # Recalculate times with slope adjustment if enabled
        if self.adjust_for_slope:
            self.calculate_times_with_slope(start_time, buffered)
        else:
            self.log("Slope adjustment disabled - using constant speed")