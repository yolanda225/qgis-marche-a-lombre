# -*- coding: utf-8 -*-
import numpy as np
import math

class ShadowCalculator:
    
    def __init__(self, mns_data, geo_transform, resolution=0.5):
        self.mns_data = mns_data
        self.geo_transform = geo_transform
        self.resolution = resolution
        self.rows, self.cols = mns_data.shape

    def draw_bresenham_line(self, x0, y0, max_dist_pixels, azimuth):
        """Draw bresenham line on a raster with given starting point

        Args:
            x0 (int): x value
            y0 (int): y value
            max_dist_pixels (float): maximum distance in pixels
            azimuth (float): direction angle of line in radians

        Returns:
            (int,int)[]: list of indices of resulting line
        """
        delta_x = max_dist_pixels * np.sin(azimuth)
        delta_y = max_dist_pixels * np.cos(azimuth)
        x1 = int(x0 + delta_x)
        y1 = int(y0 - delta_y)

        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        
        D = dx - dy
        
        line = []
        while True:
            # Boundary check
            if not (0 <= x0 < self.cols and 0 <= y0 < self.rows):
                break

            line.append((x0, y0))

            if x0 == x1 and y0 == y1:
                break
                
            D2 = 2 * D

            # Adjust x
            if D2 > -dy:
                D = D - dy
                x0 = x0 + sx

            # Adjust y  
            if D2 < dx:
                D = D + dx
                y0 = y0 + sy
                
        return line

    def calc_angle(self, trail_point, index_list):
        """
        Calculates angles for all points in bresenham line at once using numpy

        Args:
            trail_point: trail point from where angles are calculated
            index_list (int,int)[]: index list from bresenham line

        Returns:
            float[]: list of angles
        """
        if not index_list:
            return np.array([])

        path = np.array(index_list)
        path_x = path[:, 0]
        path_y = path[:, 1]

        # Access attributes directly from TrailPoint object
        start_x, start_y = trail_point.col, trail_point.row
        h_viewer = trail_point.z + 1.7

        h_obstacles = self.mns_data[path_y, path_x]

        # Filter only obstacles higher than viewer
        mask = h_obstacles > h_viewer
        
        if not np.any(mask):
            return np.array([]) 

        rel_x = path_x[mask]
        rel_y = path_y[mask]
        rel_h = h_obstacles[mask]

        # Calculate Euclidean Distances
        dist_sq = (rel_x - start_x)**2 + (rel_y - start_y)**2
        
        dist_mask = dist_sq > 0
        dist_pixels = np.sqrt(dist_sq[dist_mask])
        rel_h = rel_h[dist_mask]
        
        if len(dist_pixels) == 0:
            return np.array([])

        dist_m = dist_pixels * self.resolution

        # Calculate angles
        height_diffs = rel_h - h_viewer
        angles_rad = np.arctan(height_diffs / dist_m)
        
        return angles_rad
    
    def calculate_shadows(self, trail_points, max_dist_m=500):
        """Calculate if trail points are in shadow or sun along a trail

        Args:
            trail_points [TrailPoint]: trail points 
            max_dist_m (int, optional): maximum distance in which an obstacle which could cause shadow is searched

        Returns:
            int[]: list of shadows (0=sunny,1=shady)
        """
        results = []
        
        origin_x = self.geo_transform[0]
        pixel_width = self.geo_transform[1]
        origin_y = self.geo_transform[3]
        pixel_height = self.geo_transform[5]
        
        max_dist_px = int(max_dist_m / self.resolution)

        for tp in trail_points:
            # Attach temporary pixel coordinates to object for calc_angle
            tp.col = int((tp.x - origin_x) / pixel_width)
            tp.row = int((tp.y - origin_y) / pixel_height)
            
            # Boundary check
            if not (0 <= tp.col < self.cols and 0 <= tp.row < self.rows):
                results.append(0)
                continue
            
            # Night check
            sun_elevation_rad = tp.solar_pos[0]
            if sun_elevation_rad < 0:
                results.append(1) # It is night/shady
                continue

            # Draw line in azimuth direction
            indices = self.draw_bresenham_line(tp.col, tp.row, max_dist_px, tp.solar_pos[1])
            
            # Calculate angles of line
            angles_rad = self.calc_angle(tp, indices)
            
            # Check shadow
            if len(angles_rad) == 0:
                results.append(0) # No obstacles -> sunny
            else:
                # Compare max angle with sun elevation
                max_obstacle_angle = np.max(angles_rad)
                if max_obstacle_angle > sun_elevation_rad:
                    results.append(1) # Shady
                else:
                    results.append(0) # Sunny
            
        return results