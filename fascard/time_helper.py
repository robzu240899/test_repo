'''
Created on Feb 28, 2015

@author: Tom
'''

'''
Created on May 2, 2014

@author: Tom
'''
from datetime import datetime
from pytz import timezone,utc

import scraperconfig
 

def convert_to_local(utc_dt,tz):
    if utc_dt is None:
        return None
    tz = timezone(tz)
    utc_dt = utc.localize(utc_dt)
    dt = tz.normalize(utc_dt.astimezone(tz))
    return datetime(dt.year,dt.month,dt.day,dt.hour,dt.minute,dt.second)

def duration_in_seconds(txt):
    txt = txt.lower().strip()
    if txt.find('d') != -1:
        days = int(txt.split('d ')[0].strip())
        txt = txt.split('d ')[1].strip()
    else:
        days = 0
    hms = txt.split(':')
    hr = int(hms[0].strip())
    minute = int(hms[1].strip())
    sec = int(hms[2].strip())
    return 24*3600*days + 3600*hr + 60*minute + sec
    
def format_time(txt):
    return datetime.strptime(txt,scraperconfig.FascardScrapeConfig.TIME_INPUT_FORMAT)