# -*- coding: utf-8 -*-
"""
Part of MarcheALOmbre QGIS Plugin
Copyright (C) 2025 Yolanda Seifert
Licensed under GPL v2+
"""
import os
import time
import math
import tempfile
import shutil
import xml.etree.ElementTree as ET

from qgis.core import (
    QgsNetworkAccessManager, 
    QgsRectangle, 
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform
)
from qgis.PyQt.QtCore import QUrl, QCoreApplication, QEventLoop
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from osgeo import gdal, osr

from .geo_definitions import MANUAL_DEFS

class MNSDownloader:

    BASE_URL = "https://data.geopf.fr/wms-r"
    CAPABILITIES_URL = f"{BASE_URL}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities"
    TILE_SIZE_PX = 4000 

    def __init__(self, crs, transform_context, feedback=None):
        """
        Initializes the downloader

        Args:
            crs (str): The epsg string of the target CRS
            transform_context (QgsCoordinateTransformContext): Context for coordinate transforms
            feedback (QgsProcessingFeedback, optional): Feedback object for logging
        """
        self.manager = QgsNetworkAccessManager.instance()
        self.crs = crs
        self.transform_context = transform_context
        self.feedback = feedback
        self._capabilities_xml_cache = None

    def log(self, message):
        if self.feedback:
            self.feedback.pushInfo(message)
        else:
            print(message)

    def _fetch_capabilities(self):
        """
        Fetches WMS Capabilities to find layers dynamically

        Returns:
            xml.etree.ElementTree.Element: root element of the parsed XML

        Raises:
            Exception: If the network request fails
        """
        if self._capabilities_xml_cache is not None:
            return self._capabilities_xml_cache

        self.log("Fetching WMS Capabilities...")
        request = QNetworkRequest(QUrl(self.CAPABILITIES_URL))
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        
        reply = self.manager.get(request)
        
        loop = QEventLoop()
        reply.finished.connect(loop.quit)
        loop.exec_()
        
        if reply.error() != QNetworkReply.NoError:
            raise Exception(f"Capabilities failed: {reply.errorString()}")

        content = reply.readAll()
        self._capabilities_xml_cache = ET.fromstring(content)
        return self._capabilities_xml_cache

    def get_layer_candidates(self, wgs84_point, is_mns=True):
        """
        Parses capabilities to find the best layer for the location

        Args:
            wgs84_point (QgsPointXY): point to query in WGS84 coordinates
            is_mns (bool, optional): True -> searches for Surface Models (MNS) 
                                     False -> searches for Terrain Models (MNT)

        Returns:
            list[dict]: A list of layer candidates containing 'name' and 'score'.
        """
        try:
            root = self._fetch_capabilities()
        except Exception as e:
            self.log(f"Error fetching capabilities: {e}")
            return []

        ns = {'wms': 'http://www.opengis.net/wms'}
        candidates = []
        
        if is_mns:
            search_type = "MNS"
            fallback_lidar_global = "IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.WGS84G"
            fallback_highres = "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES.MNS"
        else:
            search_type = "MNT"
            fallback_lidar_global = "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.WGS84G"
            fallback_highres = "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES"

        for layer in root.findall('.//wms:Layer', ns):
            name_elem = layer.find('wms:Name', ns)
            if name_elem is None: continue
            name = name_elem.text
            
            if "SHADOW" in name: continue

            geo_bbox = layer.find('wms:EX_GeographicBoundingBox', ns)
            if geo_bbox is None: continue

            try:
                w = float(geo_bbox.find('wms:westBoundLongitude', ns).text)
                e = float(geo_bbox.find('wms:eastBoundLongitude', ns).text)
                s = float(geo_bbox.find('wms:southBoundLatitude', ns).text)
                n = float(geo_bbox.find('wms:northBoundLatitude', ns).text)
                
                # Check if point is inside the layer
                px, py = wgs84_point.x(), wgs84_point.y()
                if not (w <= px <= e and s <= py <= n):
                    continue
                    
                score = 0
                if search_type in name and "LIDAR-HD" in name and "WGS84G" not in name:
                    score = 1000 
                elif name == fallback_lidar_global:
                    score = 500
                elif name == fallback_highres:
                    score = 100

                if score == 0: continue
                
                candidates.append({'name': name, 'score': score})
            except:
                continue

        return sorted(candidates, key=lambda x: x['score'], reverse=True)

    def validate_raster_content(self, file_path):
        """
        Validates the downloaded file by reading it

        Args:
            file_path (str): Path to the file to check

        Returns:
            tuple[bool, str]: (isValid, statusMessage)
        """
        try:
            if os.path.getsize(file_path) < 1000:
                return False, "File too small (< 1KB)"

            with open(file_path, 'rb') as f:
                header = f.read(512)
                if b"ServiceException" in header or b"<?xml" in header:
                    return False, "Contains WMS XML Error"

            gdal.PushErrorHandler('CPLQuietErrorHandler') 
            ds = gdal.Open(file_path)
            
            if not ds:
                gdal.PopErrorHandler()
                return False, "GDAL could not open file"
            
            band = ds.GetRasterBand(1)
            try:
                data = band.ReadAsArray()
            except Exception as e:
                ds = None
                gdal.PopErrorHandler()
                return False, f"File Truncated/Corrupt: {str(e)}"
            
            if data is None:
                ds = None
                gdal.PopErrorHandler()
                return False, "ReadAsArray returned None"

            mn = data.min()
            mx = data.max()
            ds = None 
            gdal.PopErrorHandler()

            if mn <= -9000 and mx <= -9000:
                return False, f"All NoData (Min:{mn} Max:{mx})"
            
            if mn == mx:
                 return False, f"Flat Data (Val:{mn})"

            return True, "Valid"

        except Exception as e:
            return False, f"Validation Exception: {str(e)}"
        
    def download_dual_quality_mns(self, trail_extent, high_res_path, low_res_path, trail_lat, input_crs, high_res=0.5, low_res=15.0):
        """Download two MNS, one high quality around the trail and one low resolution with a greater extent for longer shadows

        Args:
            trail_extent (QgsRectangle): Extent around the hiking trail
            high_res_path (str): Path to High-Res MNS
            low_res_path (str): Path to Low-Res MNS
            trail_lat (float): latitude of trail_extent center
            input_crs (str): Coordinate Reference System
            high_res (float, optional): High resolution. Defaults to 0.5.
            low_res (float, optional): Low resolution. Defaults to 30.0.

        Returns:
            bool: True if download successful
        """
        # High-Res
        self.read_tif(trail_extent, high_res, high_res_path, input_crs=input_crs)

        # Low-Res (greater extent)
        self.log("Downloading large Low Resolution MNS for obstacles at greater distance (e.g. mountains)")
        buffer_dist = 22000.0 # altitude difference of 2000m with solar elevation of 5° casts 22km shadow
        buffer_n = buffer_dist
        buffer_s = buffer_dist
        if trail_lat > 23.4: # north/south buffer not necessary for high/low lat
            buffer_n = 0
        if trail_lat < -23.4:
            buffer_s = 0

        horizon_extent = QgsRectangle(
            trail_extent.xMinimum() - buffer_dist,
            trail_extent.yMinimum() - buffer_s,
            trail_extent.xMaximum() + buffer_dist,
            trail_extent.yMaximum() + buffer_n
        )
        return self.read_tif(horizon_extent, low_res, low_res_path, input_crs=input_crs)

    def read_tif(self, extent, resolution, output_path, input_crs, is_mns=True):
        """
        Dowloads the MNS/MNT data for a specific extent and resolution

        Args:
            extent (QgsRectangle): The area to download
            resolution (float): Pixel resolution in meters
            output_path (str): File path to save the GeoTIFF
            input_crs (str): epsg code of the CRS
            is_mns (bool, optional): True -> MNS (Surface), False -> MNT (Terrain). Defaults to True.

        Returns:
            bool: True if successful, False otherwise
        """
        source_ref = QgsCoordinateReferenceSystem(input_crs)
        wgs84_ref = QgsCoordinateReferenceSystem("EPSG:4326")
        
        tr_to_wgs84 = QgsCoordinateTransform(source_ref, wgs84_ref, self.transform_context)
        tr_to_wgs84.setBallparkTransformsAreAppropriate(True)

        center_input = extent.center()
        center_wgs84 = tr_to_wgs84.transform(center_input)

        auth_id = source_ref.authid()
        is_identity = (abs(center_input.x() - center_wgs84.x()) < 0.1) and (auth_id != wgs84_ref.authid())
        
        if is_identity: # transformation failed
            if auth_id in MANUAL_DEFS:
                self.log(f"Switching to Manual Definition for Coordinate Transformation.")
                # CRS from manual definition
                source_ref = QgsCoordinateReferenceSystem.fromProj4(MANUAL_DEFS[auth_id])
                # Redo transform
                tr_to_wgs84 = QgsCoordinateTransform(source_ref, wgs84_ref, self.transform_context)
                tr_to_wgs84.setBallparkTransformsAreAppropriate(True)
                center_wgs84 = tr_to_wgs84.transform(center_input)
            else:
                self.log("Warning: Transform returned identity and no manual definition available.")

        # Search available layers using WGS84 center
        candidates = self.get_layer_candidates(center_wgs84, is_mns)

        if not candidates:
            # Default based on detected CRS to avoid "Metropole" layer in DOM-TOM
            if "2154" in self.crs:
                default = "IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
            else:
                # Use the generic WGS84G layer for DOM-TOM if specific one isn't found
                default = "IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.WGS84G"
            
            self.log(f"No candidates found. Using default: {default}")
            candidates = [{'name': default}]

        # Calculate size in pixels based on the projected extent
        width = int(extent.width() / resolution)
        height = int(extent.height() / resolution)
        
        for i, cand in enumerate(candidates):
            layer_name = cand['name']
            self.log(f"Attempting layer {layer_name}...")

            success = False
            # Check if the request is small enough for a single download
            if width <= self.TILE_SIZE_PX and height <= self.TILE_SIZE_PX:
                success = self._download_single_tile(extent, width, height, output_path, layer_name)
            else:
                # If too big switch to tiled download
                self.log(f"Large request ({width}x{height}). Switching to tiled download...")
                success = self._download_tiled(extent, resolution, width, height, output_path, layer_name)

            if success:
                is_valid, msg = self.validate_raster_content(output_path)
                if is_valid:
                    self.log(f"Success: {msg}")
                    return True
                else:
                    self.log(f"Layer {layer_name} INVALID: {msg}")
        
        return False

    def _download_tiled(self, extent, resolution, total_w, total_h, output_path, layer_name):
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
                        tile_extent, col_width_px, row_height_px, tile_path, layer_name
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

    def _download_single_tile(self, extent, width, height, output_path, layer_name):
        """
        Requests a single tile from IGN Wep Map Service
        """    
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
            
            # Validation Step
            is_valid, status_msg = self.validate_raster_content(output_path)
            if not is_valid:
                self.log(f"Downloaded file validation failed: {status_msg}")
                return False
            
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
        
        nodata_val = -9999.0
        band = ds.GetRasterBand(1)
        data = band.ReadAsArray()
        data[data < -1000] = nodata_val
        band.WriteArray(data) 
        if band:
            band.SetNoDataValue(nodata_val)

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
        band.FlushCache()
        ds = None