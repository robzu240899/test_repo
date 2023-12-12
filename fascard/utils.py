from copy import deepcopy
from datetime import datetime, timedelta
from pytz import timezone,utc
from .config import FascardScrapeConfig

class TimeHelper():

    @classmethod
    def convert_to_local(cls,utc_dt,tz):
        if utc_dt is None:
            return None
        tz = timezone(tz)
        utc_dt = utc.localize(utc_dt)
        dt = tz.normalize(utc_dt.astimezone(tz))
        return datetime(dt.year,dt.month,dt.day,dt.hour,dt.minute,dt.second)

    @classmethod
    def duration_in_seconds(cls,txt):
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

    @classmethod
    def format_time(cls,txt,custom_format=None):
        if custom_format:
            format = custom_format
        else:
            format = FascardScrapeConfig.TIME_INPUT_FORMAT
        return datetime.strptime(txt,format)
