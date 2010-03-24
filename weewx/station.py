#
#    Copyright (c) 2009 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
#    $Revision$
#    $Author$
#    $Date$
#
"""Defines the default station data, available for processing data."""
import time

import weewx
import weeutil.weeutil

class Station(object):
    """Static data about the station. Rarely changes."""
    def __init__(self, config_dict, unit_labels_dict, unit_groups_dict, hemispheres = ('N','S','E','W')):
        """Extracts info from the config_dict and stores it in self."""
        self.hemispheres = hemispheres
        self.latitude_f  = config_dict['Station'].as_float('latitude')
        self.latitude    = weeutil.weeutil.latlon_string(self.latitude_f, self.hemispheres[0:2])
        self.longitude_f = config_dict['Station'].as_float('longitude')
        self.longitude   = weeutil.weeutil.latlon_string(self.longitude_f, self.hemispheres[2:4])

        self.altitude_unit_label    = unit_labels_dict[unit_groups_dict['group_altitude']].strip()
        self.temperature_unit_label = unit_labels_dict[unit_groups_dict['group_temperature']].replace(r'\xb0','').strip()
        self.wind_unit_label        = unit_labels_dict[unit_groups_dict['group_speed']].strip()
        self.rain_unit_label        = unit_labels_dict[unit_groups_dict['group_rain']].strip()

        self.altitude_f             = config_dict['Station'].as_float('altitude')
        self.altitude               = "%d %s" % (self.altitude_f, self.altitude_unit_label)
        self.location        = weeutil.weeutil.utf8_to_html(config_dict['Station']['location'])
        self.rain_year_start = int(config_dict['Station'].get('rain_year_start', '1'))
        self.rain_year_str   = time.strftime("%b", (0, self.rain_year_start, 1, 0,0,0,0,0,-1))
        self.week_start      = int(config_dict['Station'].get('week_start', '6'))
        self.radar_url       = config_dict['Station'].get('radar_url','')
        self.uptime = weeutil.weeutil.secs_to_string(time.time() - weewx.launchtime_ts) if weewx.launchtime_ts else ''
        self.version = weewx.__version__
        # The following works on Linux only:
        try:
            os_uptime_secs =  float(open("/proc/uptime").read().split()[0])
            self.os_uptime = weeutil.weeutil.secs_to_string(int(os_uptime_secs + 0.5))
        except:
            self.os_uptime = ''
    
