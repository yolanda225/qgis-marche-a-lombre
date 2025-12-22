# -*- coding: utf-8 -*-
import os
import time
from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl, QCoreApplication
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from osgeo import gdal, osr

class MNSDownloader:

    BASE_URL = "https://data.geopf.fr/wms-r"
    
    def __init__(self, crs="EPSG:2154", feedback=None):
        self.manager = QgsNetworkAccessManager.instance()
        self.crs = crs
        self.feedback = feedback

    def log(self, message):
        if self.feedback:
            self.feedback.pushInfo(message)
        else:
            print(message)

    def read_tif(self, extent, width, height, output_path, mns = True):
        """
        Downloads MNS data and embeds georeferencing using GDAL
        """
        if mns:
            mn = "MNS"
        else:
            # MNT used for the altitude values of the trail
            mn = "MNT"
        params = [
            f"SERVICE=WMS",
            f"VERSION=1.3.0",
            f"REQUEST=GetMap",
            f"LAYERS=IGNF_LIDAR-HD_{mn}_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93",
            f"STYLES=normal",
            f"FORMAT=image/tiff",
            f"CRS={self.crs}",
            f"BBOX={extent.xMinimum()},{extent.yMinimum()},{extent.xMaximum()},{extent.yMaximum()}",
            f"WIDTH={width}",
            f"HEIGHT={height}",
            f"TRANSPARENT=false"
        ]
        
        full_url_str = f"{self.BASE_URL}?" + "&".join(params)
        self.log(f"Requesting URL: {full_url_str}")

        # Setup the Request
        request = QNetworkRequest(QUrl(full_url_str))
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        reply = self.manager.get(request)

        # Wait loop for cancel button
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
            self.log(f"Saved to {output_path}")
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