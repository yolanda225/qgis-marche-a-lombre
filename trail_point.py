# -*- coding: utf-8 -*-

class TrailPoint:

    def __init__(self, lon, lat, x, y, z, datetime):
        self.lon = lon
        self.lat = lat
        self.x = x
        self.y = y
        self.z = z
        self.datetime = datetime
        self.solar_pos = self.get_solar_pos()

    def get_solar_pos(self):
        return (0,0)