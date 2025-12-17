# -*- coding: utf-8 -*-
from qgis.core import (
    QgsBlockingNetworkRequest,
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

class MNSDownloader:

    BASE_URL = "https://data.geopf.fr/wms-r"
    
    def __init__(self, feedback=None):
        self.feedback = feedback

    def log(self, message):
        if self.feedback:
            self.feedback.pushInfo(message)
        else:
            print(message)

    def read_tif(self, extent, width, height, output_path):
        """
        Downloads MNS data using QgsBlockingNetworkRequest
        """
        
        params = [
            f"SERVICE=WMS",
            f"VERSION=1.3.0",
            f"REQUEST=GetMap",
            f"LAYERS=IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93",
            f"STYLES=normal",
            f"FORMAT=image/tiff",
            f"CRS=EPSG:2154",
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
        blocker = QgsBlockingNetworkRequest()
   
        err_code = blocker.get(request)

        if err_code != QgsBlockingNetworkRequest.NoError:
            if self.feedback:
                self.feedback.reportError(f"Network Request Failed: {blocker.reply().errorString()}")
            return False

        # Check HTTP Status
        reply = blocker.reply()
        if reply.error() != QNetworkReply.NoError:
            if self.feedback:
                self.feedback.reportError(f"HTTP Error: {reply.errorString()}")
            return False

        # Write Content to Disk
        content = reply.content()
        if not content or len(content) < 100:
            if self.feedback:
                self.feedback.reportError(f"Download failed (File too small). Server returned: {bytes(content)}")
            return False

        try:
            with open(output_path, 'wb') as f:
                f.write(content)
            self.log(f"Saved to {output_path}")
            return True
        except Exception as e:
            if self.feedback:
                self.feedback.reportError(f"File Write Error: {e}")
            return False