import os
import logging
from io import BytesIO
from zipfile import ZipFile
from datetime import date, datetime
from django.conf import settings
from django.core.mail import EmailMessage
from reporting.finance.clientreport.report import ClientRevenueReport
from reporting.models import BillingGroup, ExpenseType, BillingGroupExpenseTypeMap, ClientRevenueFullReportJobInfo, ClientRevenueFullJobsTracker
from reporting.helpers import S3Upload
from django.template.defaultfilters import slugify
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

class BillingGroupReports():
    years = [x for x in range(datetime.now().year-5, datetime.now().year+1)]
    months = [x for x in range(1,13)]
    #years = [2019]
    #months = [6,7]

    def __init__(self):
        self.s = BytesIO()
        self.zf = ZipFile(self.s, "w")

    def get_expenses(self, billing_group):
        try:
            expenses_types = ExpenseType.objects.all().order_by('display_name')
            initial = []
            for expense_type in expenses_types:
                try:
                    expense_amount =  BillingGroupExpenseTypeMap.objects.get(
                        billing_group=billing_group,
                        expense_type=expense_type).default_amount
                except:
                    expense_amount = 0.0
                initial.append({'expense_amount':expense_amount,'expense_type':expense_type})
            return initial
        except Exception as e:
            print ("Failed getting expenses for billing group: {}".format(billing_group))
            raise (e) 

    def process_month(self, year, month, billing_group, bg_expenses):
        dt = date(year,month,1)
        report = ClientRevenueReport(billing_group=billing_group,
                                            raw_expenses=bg_expenses, #TODO, remove aces collects cash everywhere
                                            start_date=dt
                                            )
        report_data, errored = report.process()
        txt = render_to_string("client_revenue_report.html",report_data)
        txt = txt.encode(encoding='UTF-8')
        dt = datetime.now().strftime('%y_%m_%d_%H_%M_%S')
        file_name = slugify("Client_Revenue_Report_%s_%s" % (billing_group.display_name,dt))
        file_name += '.html'

        return (txt, file_name)

    def upload_file(self):
        file_name = 'Client-Revenue-Historical-Report.zip'
        for file in self.zf.filelist:
            file.create_system = 0
        self.zf.close()

        file_content = self.s.getvalue()
        bucket_name = 'client-revenue-historical-reports'
        s3_handler = S3Upload(file_content, bucket_name , file_name)
        file_uploaded = s3_handler.upload()
        if file_uploaded:
            print('Succesfully uploaded zip file to S3')
            message = EmailMessage(
                subject = 'Client Revenue Historical Report Attached',
                body = 'Find attached the historical client revenue report you solicited. Or, \
                find it in S3 under the bucket: {} with the filename: {}'.format(
                    bucket_name,
                    file_name
                ),
                to = settings.IT_EMAIL_LIST
            )
            try:
                message.attach('{}.zip'.format(file_name), file_content)
                message.send(fail_silently=False)
            except Exception as e:
                print('Email send failed: {}'.format(e))
                logger.info('Failed sending email')
                raise (e)


    def process(self):
        for billing_group in BillingGroup.objects.all():
            bg_expenses = self.get_expenses(billing_group)
            for year in self.years:
                for month in self.months:
                    try:
                        report_data,fname = self.process_month(year, month, billing_group, bg_expenses)
                    except Exception as e:
                        logger.info('Failed generating report for BG: {} in Date: {}/{}'.format(
                            billing_group,
                            year,
                            month)
                        )
                        continue
                    zip_path = os.path.join(billing_group.display_name, str(year), str(month), fname)
                    self.zf.writestr(zip_path, report_data)
        self.upload_file()
        


        