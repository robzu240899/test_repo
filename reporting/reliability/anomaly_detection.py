import base64
import logging
import pandas as pd
import plotly
import numpy as np
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from scipy.stats import lognorm
from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from main.threads import EmailThread
from reporting.enums import LocationLevel, DurationType, MetricType
from reporting.metric.calculate import RevenueEarned, RevenueFundsCash
from reporting.models import AnomalyDetectionJobInfo
from revenue.enums import TransactionType
from revenue.models import LaundryTransaction
from revenue.threads import FetchMachineRevenue
from roommanager.models import *
from scipy.stats import lognorm
import matplotlib.pyplot as plt
import plotly.express as px 
import plotly.figure_factory as ff





logger = logging.getLogger()


class BaseAnomalyDetection():
    def _fix_totally_gratis_machines(self, machine, machine_df_rolling, start_date, end_date):
        if machine.equipment_type is None:
            return machine_df_rolling  #guearantee that the machine is not None and then continue
        if 'gratis' in machine.equipment_type.machine_text.lower():
            if not machine.is_active: return machine_df_rolling
            msm = machine.machineslotmap_set.filter(is_active=True).last()
            if not msm: return machine_df_rolling
            if not end_date: end_date = date.today()
            days_left = (end_date - start_date).days
            next_start_date = start_date
            starts_dict = {}
            for day in range(days_left):
                result = LaundryTransaction.objects.filter(
                    machine=machine,
                    local_transaction_date=next_start_date,
                    transaction_type=TransactionType.VEND
                ).count()
                starts_dict[next_start_date] = result
                next_start_date = next_start_date + relativedelta(days=1)
            timeseries = pd.Series(starts_dict)    
            machine_df = timeseries.to_frame()
            machine_df_rolling = machine_df.rolling(self.rolling_days).sum()
            machine_df_rolling = machine_df_rolling.dropna()
        return machine_df_rolling


class VolatilityAnomalyDetector(BaseAnomalyDetection):
    template_name = "anomaly_detection_email.html"

    def __init__(self, room_id):
        self.room_id = room_id
        self.room = LaundryRoom.objects.get(id=room_id)

    # def fetch_machine_timeseries(self, machine, start_from, is_kiosk=False):
    #     metrics_client = RevenueEarned
    #     if is_kiosk: metrics_client = RevenueFundsCash
    #     end_date = date.today()
    #     days_left = (end_date - start_from).days
    #     next_start_date = start_from
    #     revenue_dict = {}
    #     for day in range(days_left):
    #         payload = {
    #             "location_type" : LocationLevel.MACHINE,
    #             "location_id" : machine,
    #             "duration" : DurationType.DAY,
    #             "start_date" : next_start_date
    #         }
    #         result = metrics_client(**payload).process()
    #         if result: result = float(result)
    #         else: result = 0.01
    #         revenue_dict[next_start_date] = result
    #         next_start_date = next_start_date + relativedelta(days=1)
    #     return pd.Series(revenue_dict)

    def fetch_machine_timeseries(self, machine, start_from, end_date=None, is_kiosk=False):
        skip_machine = False
        metrics_client = RevenueEarned
        if is_kiosk: metrics_client = RevenueFundsCash
        if not end_date: end_date = date.today()
        days_left = (end_date - start_from).days
        next_start_date = end_date
        revenue_dict = {}
        for day in range(days_left):
            payload = {
                "location_type" : LocationLevel.MACHINE,
                "location_id" : machine,
                "duration" : DurationType.DAY,
                "start_date" : next_start_date
            }
            result = metrics_client(**payload).process()
            if result: result = float(result)
            else: result = 0.01
            revenue_dict[next_start_date] = result
            next_start_date = next_start_date - relativedelta(days=1)
            if day == 2 and sum([v for k,v in revenue_dict.items()]) > 15:
                skip_machine = True
                revenue_dict = {}
                break
        timeseries = pd.Series(revenue_dict)
        timeseries = timeseries[::-1]
        return skip_machine, timeseries

    def check_anomalies(self, timeseries, rolling_days = 7):
        df = timeseries.to_frame()
        log_returns = np.log(df).diff().dropna()
        difference_sqr = (log_returns - log_returns.rolling(rolling_days).mean())**2
        difference_sqr = difference_sqr.dropna()
        final = ((difference_sqr.rolling(rolling_days).sum() / rolling_days) * np.sqrt(252))
        final = final.dropna()
        final = final[0]
        anomalies = final[final < 0.5]
        if anomalies.values.any():
            logger.info(f"Detected anomalies in room: {self.room_id}. Dates: {anomalies.index}")
        anomalies_dict = {}
        for i in anomalies.index: anomalies_dict[i] =  final.loc[i]
        return anomalies_dict

    def report_anomalies(self, anomalies):
        rendered_response = render_to_string(self.template_name,{'anomalies': anomalies})
        email_payload = {
                'subject' : f'[ALERT] Revenue Anomalies detected in room {self.room}',
                'body' : rendered_response,
                'to' : settings.REVENUE_ANOMALY_MAILING_LIST
            }
        email_thread = EmailThread(**email_payload)
        email_thread.content_type = "html"
        email_thread.start()
        return True

    def run_analysis(self, start_from, email_anomalies=True):
        slots = self.room.slot_set.filter(is_active=True)
        room_anomalies = {}
        for slot in slots:
            curr_machine = slot.get_current_machine(slot)
            is_kiosk = False
            if 'kiosk' in slot.equipment_type.machine_text.lower(): is_kiosk = True
            skip_machine, machine_timeseries = self.fetch_machine_timeseries(
                curr_machine,
                start_from,
                is_kiosk=is_kiosk
            )
            if skip_machine: continue
            anomalies = self.check_anomalies(machine_timeseries)
            if not anomalies: continue
            room_anomalies[slot.id] = {
                'slot_name' : str(slot),
                'machine': curr_machine,
                'anomalies' : machine_timeseries.to_dict(),
                'location': self.room
            }
        if room_anomalies and email_anomalies: self.report_anomalies(room_anomalies)
        return room_anomalies

    @classmethod
    def report_anomalies_centralized(cls, anomalies):
        rendered_response = render_to_string(cls.template_name,{'anomalies': anomalies})
        email_payload = {
                'subject' : f'[ALERT] Revenue Anomalies Detected',
                'body' : rendered_response,
                'to' : settings.IT_EMAIL_LIST
            }
        email_thread = EmailThread(**email_payload)
        email_thread.content_type = "html"
        email_thread.start()
        return True

    @classmethod
    def run_as_job(cls, room_id, email_anomalies=True):
        logger.info(f"Processing room with id: {room_id}")
        ins = VolatilityAnomalyDetector(room_id)
        start_from = date.today() - relativedelta(days=14)
        result = ins.run_analysis(start_from, email_anomalies=email_anomalies)
        return result

    @classmethod
    def run_as_single_job(cls):
        all_anomalies = {}
        for room in LaundryRoom.objects.filter(is_active=True, test_location=False):
            anomalies = cls.run_as_job(room.id, email_anomalies=False)
            all_anomalies.update(anomalies)
        if all_anomalies: cls.report_anomalies_centralized(all_anomalies)


class AnomalyDetection(BaseAnomalyDetection):
    """
    Anomaly detection based on a probability distribution
    """
    sample_size = 25
    rolling_days = 7

    def __init__(self, report_job_info, jobs_tracker, end_date=None):
        self.report_job_info = AnomalyDetectionJobInfo.objects.get(id=report_job_info)
        self.machine = self.report_job_info.machine
        self.jobs_tracker = jobs_tracker
        self.end_date = end_date
        if not self.end_date: self.end_date = date.today() - relativedelta(days=1)

    def get_revenue_df(self, machine, start_date, end_date):
        machine_time_series = FetchMachineRevenue.fetch_revenue_timeseries(machine,start_date,end_date)
        machine_df = machine_time_series.to_frame()
        machine_df_rolling = machine_df.rolling(self.rolling_days).sum()
        machine_df_rolling = machine_df_rolling.dropna()
        return machine_df_rolling
    
    def save_graphs_as_html(self, data, latest_epoch): #make the function to store the graphs for linechart and histogram
        df = data
        x = df[0].values.tolist()
        group_labels = ['']
        fig_hist= ff.create_distplot([x], group_labels, bin_size=3.5, show_rug=False)
        png_hist = plotly.io.to_image(fig_hist)
        hist_png_base64 = base64.b64encode(png_hist).decode('ascii')
        # Line chart (aca falta hacer el filtro de las fechas)
        fig_line  = px.line(df, y=0, title= f'Line chart from anomaly {latest_epoch}')
        png_line = plotly.io.to_image(fig_line)
        line_png_base64 = base64.b64encode(png_line).decode('ascii')
        html_content = f"""
            <img src="data:image/png;base64,{hist_png_base64}" />
            <img src="data:image/png;base64,{line_png_base64}" />
        """
        html_content = html_content.encode() 
        # Save the combined HTML to the report_file_graphs field
        self.report_job_info.report_file_graphs.save(f'report_graphs_{datetime.now()}_{self.machine.id}.html', ContentFile(html_content))

    def create(self):
        machine = Machine.objects.get(id=self.machine.id)
        end_date = self.end_date
        start_date = end_date - relativedelta(days=(self.sample_size * self.rolling_days) + self.rolling_days) 
        self.machine_df_rolling = self.get_revenue_df(machine, start_date, end_date)
        counter = 0
        enought_data = True
        while True:
            self.machine_df_rolling = self._fix_totally_gratis_machines(machine, self.machine_df_rolling, start_date, end_date)
            rows_to_drop = self.machine_df_rolling[self.machine_df_rolling[0] < 1].index
            if len(rows_to_drop) == 0: break
            if len(rows_to_drop) == len(self.machine_df_rolling):
                self.report_job_info.msg = f"All zeros for machine {machine}"
                self.report_job_info.save()
                enought_data = False
                break
            if counter == 2: break
            self.machine_df_rolling = self.machine_df_rolling.drop(rows_to_drop)
            enought_data = len(self.machine_df_rolling[self.machine_df_rolling[0] > 0]) >= self.sample_size * self.rolling_days
            if enought_data:
                break
            else:
                start_date = start_date - relativedelta(days=self.rolling_days * len(rows_to_drop))
                self.machine_df_rolling = self.get_revenue_df(machine, start_date, end_date)
                counter +=1
        if enought_data:
            shape, loc, scale = lognorm.fit(self.machine_df_rolling[:-1])
            latest_epoch = self.machine_df_rolling.iloc[-1].values[0]
            if lognorm.cdf(latest_epoch, shape, loc, scale) <= 0.01:
                latest_epoch_date = self.machine_df_rolling.index[-1]
                cumulative_prob_percent = lognorm.cdf(latest_epoch, shape, loc, scale) * 100
                self.report_job_info.anomaly_detected = True
                self.report_job_info.msg = f"Anomaly on {machine}. Probability of observing ${latest_epoch} is: {round(cumulative_prob_percent, 4)}%"
                self.report_job_info.days_window = f'{self.rolling_days}' #corregir... 
                self.report_job_info.date_range = f'Start date: {latest_epoch_date - relativedelta(days=self.rolling_days)} - End date: {latest_epoch_date}'
                self.save_graphs_as_html(self.machine_df_rolling, latest_epoch) #here we call the function of the graphs
                self.report_job_info.save()
                logger.info(f"Anomaly on {machine}. Probability of observing ${latest_epoch} is: {round(cumulative_prob_percent, 4)}%")
        else:
            logger.info(f"The machine {machine} does not have enough data to train a prob. distribution.")
            if not self.report_job_info.msg:
                self.report_job_info.msg = f"The machine {machine} does not have enough data to train a prob. distribution."
        self.report_job_info.processed = True
        self.report_job_info.save()
        return "Success"