# -*- coding: utf-8 -*-
import numpy as np

class ShadowCalculator:

    def draw_bresenham_line(x0, y0, max_dist_pixels, azimuth):
        """Draw bresenham line on a raster with given starting point

        Args:
            x0 (int): x value
            y0 (int): y value
            max_dist_pixels (float): maximum distance in pixels
            azimuth (float): direction angle of line

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