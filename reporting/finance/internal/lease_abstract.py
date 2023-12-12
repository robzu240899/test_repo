import operator
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from itertools import groupby
from copy import copy
from reporting.models import BillingGroup, MeterRaise, PricingPeriod
from collections import OrderedDict
from tablib import Dataset
from reporting.finance.mixins import PricingChangesDataMixin


class LeaseAbstractReport(PricingChangesDataMixin):
    revenue_fields = (
        ('revenue_split_formula', 'Revenue Split Formula'),
        ('base_rent', 'Base Rent'),
        ('landloard_split_percent', 'Landlord Split Percent'),
        ('breakpoint', 'Breakpoint'),
        ('start_gross_revenue', 'Start Gross Revenue (Effectuation)'),
        ('end_gross_revenue', 'End Gross Revenue (Termination)'),
        ('min_comp_per_day', 'Min. Compensation per day'),
        ('start_date', 'Revenue Split Start Date (Effectuation)'),
        ('end_date', 'Revenue Split End Date (Termination)')
    )
    billing_group_fields = (
        ('display_name', 'Name'),
        ('client', 'Client'),
        ('additional_insureds', "Additional Insureds"),
        ('schedule_type', 'Schedule Type'),
        ('vendor_code', 'Vendor Code'),
        ('is_active', 'Active'),
        ('max_meter_raises', 'Max. Meter Raises'),
        ('lease_term_auto_renew', 'Auto Renew'),
        ('lease_term_auto_renew_length', 'Auto Renew Length'),
        ('lease_term_start', 'Lease Term Start'),
        ('lease_term_end', 'Lease Term End')
    )

    extra_fields = (
        ('lease_term','Lease Term'),
        ('autorenewals_history', 'Auto Renewals History (Start-End-Original)'),
        ('next_meter_raise', 'Next Meter Raise'),
        ('scheduled_meter_raises', 'Scheduled Meter Raises'),
        ('pricing_changes', 'Pricing Changes')
    )

    autorenew_fields = (
        'lease_start_date',
        'lease_end_date',
        'original'
    )


    order = billing_group_fields + revenue_fields + extra_fields

    def __init__(self, q=None):
        self.q = [q] if q else BillingGroup.objects.all()
        self.dataset = Dataset()
        self.dataset.title = "Lease Abstract Report"
        self.dataset.headers = self.revenue_fields + self.billing_group_fields

    def clean_data(self, data):
        data['landloard_split_percent'] = data['landloard_split_percent'] * 100
        return data

    def add_meter_raises(self, billing_group, row):
        today = date.today()
        meter_raises = MeterRaise.objects.filter(billing_group=billing_group)
        next_meter_raises = meter_raises.filter(scheduled_date__gte=today)

        if next_meter_raises:
            next_meter_raise = next_meter_raises[0]
            row['next_meter_raise'] = next_meter_raise.scheduled_date if next_meter_raise else None
            scheduled_meter_raises_string = [str(n.scheduled_date) for n in meter_raises.exclude(pk=next_meter_raise.id)]
            row['scheduled_meter_raises'] = scheduled_meter_raises_string \
                                            if scheduled_meter_raises_string else None
        else:
            row['next_meter_raise'] = None
            row['scheduled_meter_raises'] = None

        return row

    def add_pricing_changes(self, billing_group, row):
        """
        if any of the cycles of a given equipment type on a given room
        changed price i.e, there is at least one price_history greater
        than the first one, the ingested, then it is a pricing change
        """      
        all_changes = self.get_pricing_data(billing_group)
        if len(all_changes) > 0:
            final_str = ''
            for date, changes in all_changes.items():
                final_str += f'Date: {date} \n'
                for ch in changes: final_str += f'{ch}. \n'
                final_str += f'---------------. \n'
            #row['pricing_changes'] = '.\n'.join( list(all_changes.values()))  
            row['pricing_changes'] = final_str
        else:
            row['pricing_changes'] = None
        return row

    def add_autorenewals_history(self, billing_group, row):
        autorenew_history = billing_group.autorenew_history.all()
        if autorenew_history:
            extract_fields = lambda x: [str(getattr(x, field, None)) for field in self.autorenew_fields]
            history_list = [' | '.join(extract_fields(autorenew)) for autorenew in autorenew_history]
            parsed_history = '.\n'.join(history_list)
        else:
            parsed_history = None
        row['autorenewals_history'] = parsed_history
        return row



    #TODO: Move this to weekly report of shit happening

    # def get_missed_meter_raises(self, billing_group):
    #     print (billing_group)
    #     laundry_room_extension = billing_group.laundryroomextension_set.first()
    #     date_upper_threshold = date(2019,8,10) #This is around the date in which we started tracking pricing changes
    #     today = date.today()
    #     if laundry_room_extension:
    #         room_of_billing_group = laundry_room_extension.laundry_room
    #         last_pricing_change = PricingPeriod.objects.filter(
    #             start_date__gt=date_upper_threshold,
    #             laundry_room = room_of_billing_group
    #         ).last()

    #         if last_pricing_change:
    #             bg_meter_raises = billing_group.meterraise_set.filter(
    #                 scheduled_date__gt=last_pricing_change.start_date,
    #                 scheduled_date__lte=today,
    #             )
    #             if bg_meter_raises:
    #                 return [str(x.scheduled_date) for x in bg_meter_raises]


    def get_data(self, revenuesplit_rule):
        assert revenuesplit_rule.billing_group is not None
        revenue_rule = revenuesplit_rule
        billing_group = revenue_rule.billing_group
        current_row = {}
        #RevenuesplitRule fields
        for revenue_field, display in self.revenue_fields:
            value = getattr(revenue_rule, revenue_field, None)
            if revenue_field == 'landloard_split_percent' and hasattr(revenue_rule, revenue_field):
                value = value * 100
            current_row[revenue_field] = value
 
        #Billing Group fields
        for bg_field, display in self.billing_group_fields:
            current_row[bg_field] = getattr(billing_group, bg_field, None)
        #Extra fields
        bg_lease_start = billing_group.lease_term_start
        bg_lease_end = billing_group.lease_term_end
        lease_term_value = None
        if bg_lease_start and bg_lease_end:
            #force bg_lease_end to be +1 days
            bg_lease_end = bg_lease_end + relativedelta(days=1)
            time_delta = relativedelta(bg_lease_end, bg_lease_start)
            lease_term_value = '{} years'.format(time_delta.years)
            if time_delta.months: lease_term_value += ' and {} months'.format(time_delta.months)
            lease_term_value += '. \n {}'.format(f'{str(bg_lease_start)} - {str(bg_lease_end)}')
        else:
            if bg_lease_start and not bg_lease_end and billing_group.lease_term_duration_months == 0:
                lease_term_value = "Start: {}. Month-to-Month".format(str(bg_lease_start))
        current_row['lease_term'] = lease_term_value

        current_row = self.add_autorenewals_history(billing_group, current_row)
        current_row = self.add_meter_raises(billing_group, current_row)
        current_row = self.add_pricing_changes(billing_group, current_row)
        return (copy(current_row))


    def generate(self):
        entire_dataset = []
        for billing_group in self.q:
            for revenuesplit_rule in billing_group.revenuesplitrule_set.all():
                row = self.get_data(revenuesplit_rule)
                entire_dataset.append(row)
        df = pd.DataFrame(entire_dataset)
        #re-order dataframe
        df = df[[x[0] for x in self.order]]

        columns_dict = {}
        for k,v in (self.revenue_fields + self.billing_group_fields + self.extra_fields):
            columns_dict[k] = v
        df = df.rename(columns=columns_dict)
        return df.to_csv(encoding='utf-8')