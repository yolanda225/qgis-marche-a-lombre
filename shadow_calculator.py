# -*- coding: utf-8 -*-
import numpy as np
import math
from osgeo import gdal

class ShadowCalculator:
    
    def __init__(self, high_res_path, low_res_path):
        """
        Initialize with paths to High-Res (Trail) and Low-Res (Horizon) MNS files
        """
        self.high_ds = gdal.Open(high_res_path)
        if not self.high_ds:
            raise Exception(f"Could not open High-Res MNS: {high_res_path}")
        self.high_gt = self.high_ds.GetGeoTransform()
        self.high_res = self.high_gt[1]
        self.high_data = self.high_ds.GetRasterBand(1).ReadAsArray()
        self.high_rows, self.high_cols = self.high_data.shape

        self.low_ds = gdal.Open(low_res_path)
        if not self.low_ds:
            raise Exception(f"Could not open Low-Res MNS: {low_res_path}")
        self.low_gt = self.low_ds.GetGeoTransform()
        self.low_res = self.low_gt[1]
        self.low_data = self.low_ds.GetRasterBand(1).ReadAsArray()
        
        self.low_rows, self.low_cols = self.low_data.shape

    def _to_pixel(self, x, y, gt):
        """Convert world coords to pixel coords"""
        col = int((x - gt[0]) / gt[1])
        row = int((y - gt[3]) / gt[5])
        return col, row

    def draw_bresenham_line(self, x0, y0, max_dist_pixels, azimuth, rows, cols):
        """Draw bresenham line on a raster with given starting point

        Args:
            x0 (int): x value
            y0 (int): y value
            max_dist_pixels (float): maximum distance in pixels
            azimuth (float): direction angle of line in radians
            rows (int): number of rows in raster
            cols (int): number of columns in raster

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
            if not (0 <= x0 < cols and 0 <= y0 < rows):
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

    def calc_angle(self, trail_point, index_list, start_px, mns_data, resolution, min_dist_m=0):
        """
        Calculates angles for all points in bresenham line at once using numpy

        Args:
            trail_point: trail point from where angles are calculated
            index_list (int,int)[]: index list from bresenham line
            start_px (int, int): starting pixel (col, row)
            mns_data (array): MNS raster data
            resolution (float): resolution of the raster
            min_dist_m (float): minimum distance to check (overlap)

        Returns:
            (float[], float): list of angles, furthest distance
        """
        if not index_list:
            return np.array([]), 0.0

        start_x, start_y = start_px
        last_x, last_y = index_list[-1]
        dist_end_sq = (last_x - start_x)**2 + (last_y - start_y)**2
        max_dist = math.sqrt(dist_end_sq) * resolution

        path = np.array(index_list)
        path_x = path[:, 0]
        path_y = path[:, 1]

        h_viewer = trail_point.z + 1.7
        h_obstacles = mns_data[path_y, path_x]

        # Filter only obstacles higher than viewer
        mask = h_obstacles > h_viewer
        
        if not np.any(mask):
            return np.array([]), max_dist 

        rel_x = path_x[mask]
        rel_y = path_y[mask]
        rel_h = h_obstacles[mask]

        # Calculate Euclidean Distances
        dist_sq = (rel_x - start_x)**2 + (rel_y - start_y)**2
        
        dist_mask = dist_sq > 0
        dist_pixels = np.sqrt(dist_sq[dist_mask])
        rel_h = rel_h[dist_mask]
        
        if len(dist_pixels) == 0:
            return np.array([]), max_dist

        dist_m = dist_pixels * resolution

        # Filter min_dist_m (for Low Res)
        if min_dist_m > 0:
            dist_filter = dist_m > min_dist_m
            if not np.any(dist_filter):
                return np.array([]), max_dist
            dist_m = dist_m[dist_filter]
            rel_h = rel_h[dist_filter]

        # Calculate angles
        height_diffs = rel_h - h_viewer
        angles_rad = np.arctan(height_diffs / dist_m)
        
        return angles_rad, max_dist
    
    def calculate_shadows(self, trail_points, max_dist_m=20000):
        """Calculate if trail points are in shadow or sun along a trail

        Args:
            trail_points [TrailPoint]: trail points 
            max_dist_m (int, optional): maximum distance in which an obstacle which could cause shadow is searched

        Returns:
            int[]: list of shadows (0=sunny,1=shady)
        """
        results = []
        
        high_max_px = int(max_dist_m / self.high_res)
        low_max_px = int(max_dist_m / self.low_res)

        for tp in trail_points:
            
            # Night check
            sun_elevation_rad = tp.solar_pos[0]
            if sun_elevation_rad < 0:
                results.append(1) # It is night/shady
                continue

            max_angle = -np.inf
            covered_dist = 0.0

            # High-Res
            h_col, h_row = self._to_pixel(tp.x, tp.y, self.high_gt)
            
            # Boundary check
            if 0 <= h_col < self.high_cols and 0 <= h_row < self.high_rows:
                
                # Draw line in azimuth direction
                indices = self.draw_bresenham_line(
                    h_col, h_row, high_max_px, tp.solar_pos[1], self.high_rows, self.high_cols
                )
                
                # Calculate angles of line
                angles_rad, covered_dist = self.calc_angle(
                    tp, indices, (h_col, h_row), self.high_data, self.high_res, min_dist_m=0
                )
                
                # Check shadow
                if len(angles_rad) > 0:
                    max_obstacle_angle = np.max(angles_rad)
                    if max_obstacle_angle > sun_elevation_rad:
                        results.append(1) # Shady
                        continue # Skip check in Low-Res
                    max_angle = max_obstacle_angle

            # Low-Res
            l_col, l_row = self._to_pixel(tp.x, tp.y, self.low_gt)
            
            # Boundary check
            if 0 <= l_col < self.low_cols and 0 <= l_row < self.low_rows:
                
                # Draw line in azimuth direction
                indices = self.draw_bresenham_line(
                    l_col, l_row, low_max_px, tp.solar_pos[1], self.low_rows, self.low_cols
                )
                
                # Calculate angles of line, skipping covered_dist
                angles_rad, _ = self.calc_angle(
                    tp, indices, (l_col, l_row), self.low_data, self.low_res, min_dist_m=covered_dist
                )
                
                # Check shadow
                if len(angles_rad) > 0:
                    max_obstacle_angle = np.max(angles_rad)
                    if max_obstacle_angle > max_angle:
                        max_angle = max_obstacle_angle
            
            # Final check
            if max_angle > sun_elevation_rad:
                results.append(1) # Shady
            else:
                results.append(0) # Sunny
            
        return results