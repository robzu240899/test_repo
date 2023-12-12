from http import client
import boto3
import binascii
import copy
import logging
import random
import time
import os
import pandas as pd
from collections import OrderedDict
from io import BytesIO
from PyPDF2 import PdfFileMerger
from zipfile import ZipFile
from datetime import datetime
from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import F, Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from dateutil.relativedelta import relativedelta
from datetime import date
from hashlib import sha1
from main.threads import EmailThread
from main.utils import EmailExceptionClient
from reporting.finance.clientreport.report import ClientRevenueReport, ClientRevenueFullReport
from reporting.finance.internal.transactions_report import TransactionsTimeSheet
from reporting.helpers import S3Upload
from reporting.models import *
from reporting.enums import ClientReportFileType

logger = logging.getLogger(__name__)


class ClientReportJobTracker():
    """
    Parent class. Tracks execution of related jobs and zip all together when all jobs
    have been processed.
    """

    def extract_billing_group(self, stored_file_object):
        if isinstance(stored_file_object, ClientReportBasicStoredFile):
            return stored_file_object.billing_group
        elif isinstance(stored_file_object, ClientReportFullStoredFile):
            return stored_file_object.laundry_room_extension.billing_group

    def generate_zip_file(self, billing_group_pos=0):
        """
        TODO: rewrite this method so it's inherited from every single class using it
        and we can better deal with the filename structure
        """
        client_rev_reports_directories = ['Aces Owes Client', 'Client Owes Aces', 'No Money Owed']
        s = BytesIO()
        zf = ZipFile(s, "w")
        logger.info('Creating Zip File')
        for stored_file_object in self.jobs_tracker.generated_files.all():
            s3_path = stored_file_object.report_file.name.split("/")
            if any([d in s3_path for d in client_rev_reports_directories]): billing_group_pos = 1
            if 'ach' in s3_path or 'check' in s3_path: billing_group_pos = 2 #covers case for ClientRevenueReport directoy scheme
            fname = s3_path[len(s3_path)-1]
            billing_group = self.extract_billing_group(stored_file_object)
            #subdir = billing_group.__str__().replace('|', '')
            s3_path[billing_group_pos] = billing_group.__str__().replace('|', '')
            parent = billing_group.client
            if parent:
                parent_dir_name = parent.__str__().replace('|', '')
                s3_path.insert(billing_group_pos, parent_dir_name)   
#                zip_path()
                #zip_path = os.path.join(parent_dir_name, subdir, fname)
            #else:
                #zip_path = os.path.join(subdir, fname)
            zip_path = os.path.join(*s3_path)
            file_content = stored_file_object.report_file.read()
            zf.writestr(zip_path, file_content)
        logger.info('Succesfully created Zip File')
        for file in zf.filelist:
            file.create_system = 0
        zf.close()
        self.file_content = s.getvalue()

    def upload_to_s3(self):
        if getattr(self, 'file_name', None) is None:
            self.generate_file_name()
        try:
            logger.info('Uploading zip file to S3')
            s3_handler = S3Upload(self.file_content, self.bucket_name, self.file_name)
            file_uploaded = s3_handler.upload()
            if file_uploaded:
                return s3_handler.get_file_link()
            return file_uploaded
        except Exception as e:
            raise Exception(e)

    def generate_file_name(self):
        self.file_name = '{}-{}.zip'.format(
            self.report_file_name,
            sha1(str(random.random()).encode("utf-8")).hexdigest()[:5]
        )
        return self.file_name

    def get_jobs_tracker(self, tracker_id):
        try:
            jobs_tracker = self.tracker_model.objects.get(pk=tracker_id)
            return jobs_tracker
        except Exception as e:
            raise Exception("Could not find ClientReportJobsTracker model \
            with id: {}. Failed with exception: {}".format(
                tracker_id,
                e)
            )

    def _get_extra_email_body(self):
        return ''

    def send_email(self, file_link, extra_body=''):
        body = """<html><body>.Find attached the {} you solicited: {}. {}""".format(
            self.verbose_report_name,
            file_link,
            extra_body
        )
        message = EmailMessage(
            subject = self.email_subject,
            body = body,
            to = self.jobs_tracker.user_requested_email.split(',')
        )
        #try:
        #    message.attach('{}.zip'.format(self.file_name), self.file_content)
        #except Exception as e:
        #    logger.info('Email send failed: {}'.format(e))
        message.content_subtype = "html"
        message.send(fail_silently=False)

    def send_revenue_report(self, full_report_jobs_tracker, billing_group_pos=0):
        logger.info('Started executing {} JobsTracker processor.'.format(self.__class__.__name__))
        
        self.jobs_tracker = self.get_jobs_tracker(full_report_jobs_tracker) #wasted call?
        
        while True:
            self.jobs_tracker = self.get_jobs_tracker(full_report_jobs_tracker)
            time.sleep(10)
            if self.jobs_tracker.jobs_being_tracked.all().count() == self.jobs_tracker.jobs_processed:
                logger.info('All jobs wered processed succesfully. Proceding to gather files for delivery')
                break

        logger.info('Creating Zip File')
        try:
            self.generate_zip_file(billing_group_pos=billing_group_pos)
        except Exception as e:
            raise(e)

        logger.info('Uploading zip file to S3')
        file_uploaded = self.upload_to_s3()
        if file_uploaded:
            logger.info('Succesfully uploaded zip file to S3')
            logger.info("File Uploaded with no errors: {}".format(file_uploaded))  
            extra_email_body = self._get_extra_email_body()          
            self.send_email(file_link=file_uploaded, extra_body=extra_email_body)


class ClientReportProcessor():
    """
    Parent class. Processes jobs for each billing group
    """

    def generate_report(self):
        raise NotImplementedError

    def get_report_info(self, report_job_info):
        try:
            report_info = self.job_info_model.objects.get(pk=report_job_info)
        except Exception as e:
            raise Exception(
                'Could not find ReportJobInfo model with id: {}. Failed with exception: {}'.format(
                    report_job_info,
                    e)
                )
        return report_info

    def create_report(self, payload):
        report_processor = self.report_processor(**payload)
        try:
            self.report_response = report_processor.create()
        except Exception as e:
            err = 'Failed creating report for {} {} with exception {}'.format(
                self.tracked_model_name,
                getattr(self.report_info, self.tracked_model_name),
                e)
            logger.error(err, exc_info=True)
            raise Exception(e)
        return True

    def update_tracker(self):
        if self.report_response == 'Success':
            logger.info(
                '{} Job execution was successful. {} ID: {}'.format(
                    self.__class__.__name__,
                    self.tracked_model_name,
                    getattr(self.report_info, self.tracked_model_name)
                )
            )
            job_tracker = self.job_tracker_model.objects.get(pk=self.report_info.job_tracker.id)
            logger.info("Starting Jobs Processed: {}".format(job_tracker.jobs_processed))
            if job_tracker.jobs_processed < job_tracker.jobs_being_tracked.all().count():
                job_tracker.jobs_processed = F('jobs_processed') + 1
                job_tracker.save()
            logger.info("Finishing Jobs Processed: {}".format(job_tracker.jobs_processed))
        else:
            logger.info('{} response was not successful. Response: {}'.format(
                self.__class__.__name__,
                self.report_response
                )
            )
            return
            

class ClientRevenueFullReportJobProcessor(ClientReportProcessor):
    """
        The Client Revenue Full Report is a low-level report of all revenue
        generated at locations related to a billing group on a given period of time
    """
    job_info_model = ClientRevenueFullReportJobInfo
    job_tracker_model = ClientRevenueFullJobsTracker
    report_processor = ClientRevenueFullReport
    tracked_model_name = 'billing_group'

    def generate_report(self, report_job_info):
        self.report_info = self.get_report_info(report_job_info)
        dt = date(self.report_info.year, self.report_info.month, 1)
        payload = {
            "billing_group" : self.report_info.billing_group,
            "start_date" : dt,
            "jobs_tracker" : self.report_info.job_tracker
        }
        logger.info(f"Calling create_report for billing_group {self.report_info.billing_group}")
        self.create_report(payload)
        logger.info(f"Done creating report for billing_group {self.report_info.billing_group}")
        logger.info("Trying to update tracker")
        self.update_tracker()
        logger.info("Done updating tracker")
        return True
    
    @classmethod
    def run_as_job(cls, report_job_info):
        ins = ClientRevenueFullReportJobProcessor()
        logger.info(f"Calling ClientRevenueFullReportJobProcessor.generate_report for report_job_info {report_job_info}")
        try:
            ins.generate_report(report_job_info)
        except Exception as e:
            requestor_email = None
            if hasattr(ins, 'report_info'): requestor_email = ins.report_info.get_requestor_email()
            body_str = f'An exception ocurred while processing a full low-level report: {e}'
            email = EmailExceptionClient(**{'subject': 'Exception in ClientRevenueFullReportJob', 'to': requestor_email, 'body': body_str})
            email.send()            
            #instead of rising an exception we save the error as a txt file
            #raise (e)
        return True

class ClientRevenueReportJobProcessor(ClientReportProcessor):
    """
        The Client Revenue Report is a high-level revenue balance/report mainly used
        to pay rent to clients.
    """
    job_info_model = ClientRevenueReportJobInfo
    job_tracker_model = ClientRevenueJobsTracker
    report_processor = ClientRevenueReport
    tracked_model_name = 'billing_group'

    def generate_report(self, report_job_info):
        self.report_info = self.get_report_info(report_job_info)
        dt = date(self.report_info.year, self.report_info.month,1)
        payload = {
            'billing_group' : self.report_info.billing_group,
            'start_date' : dt,
            'jobs_tracker' : self.report_info.job_tracker,
            'pdf_generation' : self.report_info.pdf_generation,
            'html_generation' : self.report_info.html_generation,
            'include_zero_rows' : self.report_info.include_zero_rows,
            'report_job_info_id' : report_job_info
        }
        logger.info(f"Generating ClientRevenueReportJobProcessor report with payload: {payload}")
        try:
            self.create_report(payload)
        except Exception as e:
            logger.error(e)
            if self.report_info.job_tracker.user_requested_email:
                msg = 'The Client Revenue report for BillingGroup: {} failed with exception: {}'.format(
                    self.report_info.billing_group,
                    e
                )
                email = EmailMessage(
                    subject='Client Revenue Report Failed',
                    body=msg,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=self.report_info.job_tracker.user_requested_email.split(',')
                )
                email.send(fail_silently=False)
            raise Exception(e)
        self.update_tracker()

    @classmethod
    def run_as_job(cls, report_job_info):
        ins = ClientRevenueReportJobProcessor()
        ins.generate_report(report_job_info)


class TimeSheetsReportJobProcessor(ClientReportProcessor):
    job_info_model = TimeSheetsReportJobInfo
    job_tracker_model = TimeSheetsReportJobTracker
    tracked_model_name = 'employee'
    report_processor = TransactionsTimeSheet

    def _create_payload(self, report_info: TimeSheetsReportJobInfo) -> dict:
        employees_ids = [report_info.employee.fascard_user_account_id]
        custom_query = [
            Q(fascard_user__fascard_user_account_id__in=employees_ids) | Q(external_fascard_user_id__in=employees_ids)
        ]
        payload = {
            'employee' : report_info.employee,
            'start' : report_info.start_date,
            'end' : report_info.end_date,
            'custom_query' : custom_query,
            'tx_type' : 'employee_timesheet',
            'job_tracker' : report_info.job_tracker
        }
        return payload

    def generate_report(self, report_job_info):
        self.report_info = self.get_report_info(report_job_info)
        self.payload = self._create_payload(self.report_info)
        self.create_report(self.payload)
        self.update_tracker()

    @classmethod
    def run_as_job(cls, report_job_info):
        ins = TimeSheetsReportJobProcessor()
        ins.generate_report(report_job_info)


class ClientRevenueFullJobsTrackerProcessor(ClientReportJobTracker):
    bucket_name = 'client-revenue-full-reports'
    report_file_name = 'Client-Revenue-Full-Report'
    report = 'ClientRevenueFullReport'
    tracker_model = ClientRevenueFullJobsTracker #change for ClientRevenueFullJobsTracker
    email_subject = 'Client Revenue Full Low-Level Report Attached'
    verbose_report_name = 'full low-level client revenue report'

    @classmethod
    def run_as_job(cls, report_jobs_tracker):
        ins = ClientRevenueFullJobsTrackerProcessor()
        ins.send_revenue_report(report_jobs_tracker)


class ClientRevenueJobsTrackerProcessor(ClientReportJobTracker):
    bucket_name = 'client-revenue-reports'
    report_file_name = 'Client-Revenue-Report'
    report = 'ClientRevenueReport'
    tracker_model = ClientRevenueJobsTracker
    email_subject = 'Client Revenue Report Attached'
    verbose_report_name = 'client revenue report'
    accounts_payable_template = {
        'Company Code': 'ACESL',
        'Vendor Account': 'MISSING',
        'Invoice Amount': 'MISSING',
        'Invoice Number CRC32 Hash Input String' : '',
        'Invoice Number' : 0,
        'Invoice Date MMDDYY': 'MISSING',
        'Due Date MMDDYY': 'MISSING',
        'Invoice Description' : 'MISSING',
        'GL Account 1' : '4180',
        'GL Amount 1' : 'MISSING',
        'Image File Spec' : 'MISSING',
    }


    def _accounts_payable_report_processing(self, billing_group, stored_file_object):
        s3_path = stored_file_object.report_file.name.split("/")
        fname = s3_path[len(s3_path)-1]
        accounts_payable_dict = copy.deepcopy(self.accounts_payable_template)
        if stored_file_object.job_info and stored_file_object.job_info.fully_processed:
            #accounts_payable_dict['billing_group'] = billing_group
            year, month = s3_path[len(s3_path)-2].split('-')
            room = s3_path[len(s3_path)-3]
            str_month = date(int(year), int(month), 1).strftime("%B")
            report_start_date = date(int(year), int(month), 1)
            today = date.today()
            invoice_date = report_start_date + relativedelta(months=1)
            accounts_payable_dict['Company Code'] = 'ACESL'
            accounts_payable_dict['Vendor Account'] = billing_group.vendor_code
            accounts_payable_dict['Invoice Amount'] = stored_file_object.job_info.invoice_amount
            accounts_payable_dict['Invoice Number CRC32 Hash Input String'] = f"{billing_group.id},{report_start_date}"
            crc32_hash = binascii.crc32(f"{billing_group.id},{report_start_date}".encode("utf-8"))
            accounts_payable_dict['Invoice Number'] = '%08X' % crc32_hash
            accounts_payable_dict['Invoice Date MMDDYY'] = f"{invoice_date.month:02d}/{invoice_date.day:02d}/{str(report_start_date.year)[-2:]}"
            accounts_payable_dict['Due Date MMDDYY'] = f"{today.month:02d}/{today.day:02d}/{str(today.year)[-2:]}"
            accounts_payable_dict['Invoice Description'] = f"{billing_group.display_name.upper()} | {room} --- {str_month} {year}"
            accounts_payable_dict['GL Amount 1'] = stored_file_object.job_info.invoice_amount
            accounts_payable_dict['Image File Spec'] = fname
        else:
            if not stored_file_object.job_info: logger.info(f"ClientReportBasicStoredFile with id {stored_file_object.id} has no job info")
            logger.info()
        return accounts_payable_dict

    def _merge_files(self, files, zip_file, final_filename):
        merger = PdfFileMerger()
        temp_file_name = f"MergedPdf-{round(datetime.now().timestamp() * 1000)}.pdf"
        for f in files: merger.append(BytesIO(f))
        with open(temp_file_name, "wb") as fout: merger.write(fout)
        fout.close()
        file_content = open(temp_file_name, 'rb')
        file_path = os.path.join(final_filename)
        zip_file.writestr(file_path, file_content.read())
        file_content.close()
        os.remove(temp_file_name)
        return zip_file

    def generate_zip_file(self, billing_group_pos=0):
        """
        TODO: rewrite this method so it's inherited from every single class using it
        and we can better deal with the filename structure
        """
        client_rev_reports_directories = ['Aces Owes Client', 'Client Owes Aces', 'No Money Owed']
        s = BytesIO()
        zf = ZipFile(s, "w")
        logger.info('Creating Zip File')
        accounts_payable_dir = 'Accounts Payable Directory'
        accounts_payable_dataset = []
        aces_owes_pdfs = OrderedDict()
        client_owes_pdfs = OrderedDict()
        no_owed_pdfs = OrderedDict()
        sort_key_memory = []
        for stored_file_object in self.jobs_tracker.generated_files.all():
            s3_path = stored_file_object.report_file.name.split("/")
            if any([d in s3_path for d in client_rev_reports_directories]): billing_group_pos = 1
            if 'ach' in s3_path or 'check' in s3_path: billing_group_pos = 2 #covers case for ClientRevenueReport directoy scheme
            fname = s3_path[len(s3_path)-1]
            billing_group = self.extract_billing_group(stored_file_object)
            #subdir = billing_group.__str__().replace('|', '')
            s3_path[billing_group_pos] = billing_group.__str__().replace('|', '')
            parent = billing_group.client
            if parent:
                parent_dir_name = parent.__str__().replace('|', '')
                s3_path.insert(billing_group_pos, parent_dir_name)   
#                zip_path()
                #zip_path = os.path.join(parent_dir_name, subdir, fname)
            #else:
                #zip_path = os.path.join(subdir, fname)
            zip_path = os.path.join(*s3_path)
            ap_zip_path = os.path.join(accounts_payable_dir, fname)
            file_content = stored_file_object.report_file.read()
            #TODO: use an ordered dict on id and then iterate to create ordered list of docs
            if stored_file_object.file_type == ClientReportFileType.PDF:
                loc_id = fname.split('-')[0]
                sort_key = f'{loc_id}-{stored_file_object.job_info.year}-{stored_file_object.job_info.month}'
                if 'Aces Owes Client' in s3_path: aces_owes_pdfs[sort_key] = file_content
                if 'Client Owes Aces' in s3_path: client_owes_pdfs[sort_key] = file_content
                if 'No Money Owed' in s3_path: no_owed_pdfs[sort_key] = file_content
            zf.writestr(zip_path, file_content)
            zf.writestr(ap_zip_path, file_content)
            if stored_file_object.file_type == ClientReportFileType.PDF:
                accounts_payable_dict = self._accounts_payable_report_processing(billing_group, stored_file_object)
                accounts_payable_dataset.append(accounts_payable_dict)
        #accounts payable
        logger.info(f"Aces owes PDFs: {aces_owes_pdfs.keys()}")
        logger.info(f"Client owes PDFs: {client_owes_pdfs.keys()}")
        logger.info(f"No owed PDFs: {no_owed_pdfs.keys()}")
        accounts_payable_df = pd.DataFrame(accounts_payable_dataset)
        csv_ap_path = os.path.join(accounts_payable_dir, "Import Report.csv")
        zf.writestr(csv_ap_path, accounts_payable_df.to_csv())
        #merged_pdfs
        aces_owes_pdfs = [aces_owes_pdfs[k] for k in sorted(aces_owes_pdfs)]
        client_owes_pdfs = [client_owes_pdfs[k] for k in sorted(client_owes_pdfs)]
        no_owed_pdfs = [no_owed_pdfs[k] for k in sorted(no_owed_pdfs)]
        if aces_owes_pdfs: zf = self._merge_files(aces_owes_pdfs, zf, 'Aces Owes client --- ALL Merged.pdf')
        if client_owes_pdfs: zf = self._merge_files(client_owes_pdfs, zf, 'Client Owes Aces --- ALL Merged .pdf')
        if no_owed_pdfs: zf = self._merge_files(no_owed_pdfs, zf, 'No Money owed ---- All merged.pdf')

        logger.info('Succesfully created Zip File')
        for file in zf.filelist:
            file.create_system = 0
        zf.close()
        self.file_content = s.getvalue()

    def _get_extra_email_body(self):
        errors_queryset = self.jobs_tracker.jobs_being_tracked.filter(errored=True)
        if errors_queryset:
            errors = "Reports with errors: "
            errors += ''.join([f"<li><p> {error.error} </p></li>" for error in errors_queryset])
        else:
            errors = ''
        return errors

    @classmethod
    def run_as_job(cls, report_jobs_tracker):
        ins = ClientRevenueJobsTrackerProcessor()
        ins.send_revenue_report(report_jobs_tracker, billing_group_pos=1)


class TimeSheetsJobsTrackerProcessor(ClientReportJobTracker):
    bucket_name = 'timesheets-reports'
    report_file_name = 'Timesheets-Report'
    report = 'TimeSheetsReport'
    tracker_model = TimeSheetsReportJobTracker
    email_subject = 'Timesheets report attached.'
    verbose_report_name = 'timesheets report'

    def generate_zip_file(self):
        s = BytesIO()
        zf = ZipFile(s, "w")
        for stored_file_object in self.jobs_tracker.generated_files.all():
            s3_path = stored_file_object.report_file.name.split("/") #splitting into directory and file
            zip_path = os.path.join(*s3_path)
            zf.writestr(zip_path, stored_file_object.report_file.read())
        logger.info('Succesfully created Zip File')
        for file in zf.filelist:
            file.create_system = 0
        zf.close()
        self.file_content = s.getvalue()

    @classmethod
    def run_as_job(cls, report_jobs_tracker: int) -> bool:
        ins = TimeSheetsJobsTrackerProcessor()
        ins.send_revenue_report(report_jobs_tracker)
        return True