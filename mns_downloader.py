# -*- coding: utf-8 -*-
import os
import time
import math
import tempfile
import shutil
from qgis.core import QgsNetworkAccessManager, QgsRectangle
from qgis.PyQt.QtCore import QUrl, QCoreApplication
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from osgeo import gdal, osr

class MNSDownloader:

    BASE_URL = "https://data.geopf.fr/wms-r"
    TILE_SIZE_PX = 4000 

    def __init__(self, crs="EPSG:2154", feedback=None):
        self.manager = QgsNetworkAccessManager.instance()
        self.crs = crs
        self.feedback = feedback

    def log(self, message):
        if self.feedback:
            self.feedback.pushInfo(message)
        else:
            print(message)

    def read_tif(self, extent, resolution, output_path, is_mns=True):
        """
        Downloads MNS/MNT data. 
        Automatically handles tiling if the requested width/height exceeds 4000px and can't be downloaded at once
        """
        width = int(extent.width() / resolution)
        height = int(extent.height() / resolution)
        # Check if the request is small enough for a single download
        if width <= self.TILE_SIZE_PX and height <= self.TILE_SIZE_PX:
            return self._download_single_tile(extent, width, height, output_path, is_mns)

        # If too big switch to tiled download
        self.log(f"Request size ({width}x{height}) exceeds limit. Switching to tiled download...")

        return self._download_tiled(extent, resolution, width, height, output_path, is_mns)

    def _download_tiled(self, extent, resolution, total_w, total_h, output_path, is_mns):
        """
        Splits the extent into chunks of max 4000px, downloads them, and merges them
        """
        cols = math.ceil(total_w / self.TILE_SIZE_PX)
        rows = math.ceil(total_h / self.TILE_SIZE_PX)
        
        temp_dir = tempfile.mkdtemp()
        tile_files = []
        
        current_y = extent.yMaximum()
        
        try:
            for i in range(rows):
                current_x = extent.xMinimum()
                
                # Calculate height of this row (last row might be smaller)
                row_height_px = min(self.TILE_SIZE_PX, total_h - (i * self.TILE_SIZE_PX))
                row_height_m = row_height_px * resolution
                
                for j in range(cols):
                    if self.feedback and self.feedback.isCanceled():
                        return False

                    # Calculate width of this col
                    col_width_px = min(self.TILE_SIZE_PX, total_w - (j * self.TILE_SIZE_PX))
                    col_width_m = col_width_px * resolution

                    # Define tile extent
                    tile_extent = QgsRectangle(
                        current_x, 
                        current_y - row_height_m, 
                        current_x + col_width_m, 
                        current_y
                    )
                    
                    tile_path = os.path.join(temp_dir, f"tile_{i}_{j}.tif")
                    
                    self.log(f"Downloading tile {i+1},{j+1} / {rows},{cols} ({col_width_px}x{row_height_px})...")

                    success = self._download_single_tile(
                        tile_extent, col_width_px, row_height_px, tile_path, is_mns
                    )
                    
                    if not success:
                        raise Exception("Tile download failed")
                    
                    tile_files.append(tile_path)
                    current_x += col_width_m
                
                current_y -= row_height_m

            # Merge tiles using GDAL VRT
            self.log("Merging tiles...")
            vrt_options = gdal.BuildVRTOptions(resampleAlg='nearest')
            vrt_path = os.path.join(temp_dir, "merged.vrt")
            vrt = gdal.BuildVRT(vrt_path, tile_files, options=vrt_options)
            vrt = None # Flush to disk
            
            # Translate VRT to final TIFF
            translate_options = gdal.TranslateOptions(format='GTiff', creationOptions=['COMPRESS=DEFLATE', 'TILED=YES'])
            gdal.Translate(output_path, vrt_path, options=translate_options)
            
            return True

        except Exception as e:
            self.log(f"Error during tiled download: {e}")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _download_single_tile(self, extent, width, height, output_path, is_mns=True):
        """
        Requests a single tile from IGN Wep Map Service
        """
        if is_mns:
            layer_name = "IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
        else:
            layer_name = "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
            
        params = [
            f"SERVICE=WMS",
            f"VERSION=1.3.0",
            f"REQUEST=GetMap",
            f"LAYERS={layer_name}",
            f"STYLES=normal",
            f"FORMAT=image/tiff",
            f"CRS={self.crs}",
            f"BBOX={extent.xMinimum()},{extent.yMinimum()},{extent.xMaximum()},{extent.yMaximum()}",
            f"WIDTH={int(width)}",
            f"HEIGHT={int(height)}",
            f"TRANSPARENT=false"
        ]
        
        full_url_str = f"{self.BASE_URL}?" + "&".join(params)
        # self.log(f"Requesting URL: {full_url_str}") 

        request = QNetworkRequest(QUrl(full_url_str))
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        reply = self.manager.get(request)

        while reply.isRunning():
            if self.feedback and self.feedback.isCanceled():
                reply.abort()
                if self.feedback:
                    self.feedback.reportError("Download canceled by user.")
                return False
            QCoreApplication.processEvents()
            time.sleep(0.05)

        # Check HTTP Status
        if reply.error() != QNetworkReply.NoError:
            if self.feedback:
                if reply.error() != QNetworkReply.OperationCanceledError:
                    self.feedback.reportError(f"HTTP Error: {reply.errorString()}")
            self.log(f"QNetworkReply Error: {reply.errorString()}")
            return False

        content = reply.readAll()

        # Write Content to Disk
        if not content or len(content) < 100:
            if self.feedback:
                self.feedback.reportError(f"Download failed (File too small). Server returned: {bytes(content)}")
            return False

        try:
            with open(output_path, 'wb') as f:
                f.write(content)
            
            self._embed_georeferencing(output_path, extent, width, height)
            # self.log(f"Saved to {output_path}")
            return True

        except Exception as e:
            if self.feedback:
                self.feedback.reportError(f"GDAL Error: {e}")
            return False

    def _embed_georeferencing(self, tif_path, extent, width, height):
        """
        Opens the existing TIFF using GDAL and injects spatial metadata (GeoTransform and Projection)
        """
        ds = gdal.Open(tif_path, 1)
        if ds is None:
            raise Exception("Could not open file with GDAL.")

        x_res = (extent.xMaximum() - extent.xMinimum()) / width
        y_res = (extent.yMaximum() - extent.yMinimum()) / height
        
        # GeoTransform list format:
        # [0] Top-Left X Coordinate
        # [1] W-E Pixel Resolution
        # [2] Rotation
        # [3] Top-Left Y Coordinate
        # [4] Rotation
        # [5] N-S Pixel Resolution (negative for north-up)
        geotransform = [
            extent.xMinimum(), x_res, 0,
            extent.yMaximum(), 0, -y_res
        ]
        ds.SetGeoTransform(geotransform)

        srs = osr.SpatialReference()
        srs.SetFromUserInput(self.crs) 
        
        ds.SetProjection(srs.ExportToWkt())
        # Close the file
        ds = None