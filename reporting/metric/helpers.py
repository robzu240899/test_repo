'''
Created on Apr 20, 2017

@author: Thomas
'''
from roommanager.models import LaundryRoom, Machine

from ..enums import LocationLevel

from ..models import BillingGroup

import logging
from datetime import date, timedelta
from reporting.enums import LocationLevel
from revenue.models import LaundryTransaction


class MetricHelpers(object):

    @classmethod
    def get_all_locations(cls,location_level,active_only=False):
        if location_level == LocationLevel.BILLING_GROUP:
            qry = BillingGroup.objects.all()
            if active_only:
                qry = qry.filter(is_active=True)
        elif location_level == LocationLevel.LAUNDRY_ROOM:
            qry= LaundryRoom.objects.all()
            if active_only:
                qry = qry.filter(is_active=True)
        elif location_level == LocationLevel.MACHINE:
            qry = Machine.objects.all()
            if active_only:
                qry = qry.filter(is_active=True)
        else:
            raise Exception("Unknown/Unimplemented LocationLevel in MetricHelper.get_all_locations")
        return qry
