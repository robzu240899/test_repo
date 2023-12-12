from reporting.finance.internal_report_views import InternalReportThreadProcessor, TransactionReportView, ReportThreadProcessor
from reporting.finance.client_revenue_views import ClientRevenueReportView, ClientRevenueFullReportView
from reporting.threads import ClientNetRentReportThread


class InternalReportProcessor():

    @classmethod
    def process(cls, payload):
        InternalReportThreadProcessor(payload).start()


class ClientRevenueReportProcessor(ClientRevenueReportView):

    def process(self, payload):
        self._enqueue(
            payload.get('start_date'),
            payload.get('end_date'),
            payload.get('email'),
            payload
        )
        return True


class ClientFullRevenueReportProcessor(ClientRevenueFullReportView):

    def process(self, payload):
        self._enqueue(
            payload.get('start_date'),
            payload.get('end_date'),
            payload.get('email'),
            payload
        )
        return True


class RentPaidProcessor():

    def process(self, payload):
        thread_processor = ClientNetRentReportThread(
            email = payload.get('email'),
            billing_groups = payload.get('billing_groups'),
            start_year = payload.get('start_year'),
            start_month = payload.get('start_month'),
            end_year = payload.get('end_year'),
            end_month = payload.get('end_month'),
            metric = payload.get('metric')
        )
        thread_processor.start()


class TransactionsReportProcessor():

    def process(self, payload):
        extra_filters, custom_query = TransactionReportView()._fetch_extra_filters(
            payload.get('report_type'),
            payload.get('employees')
        )
        user_email = payload.get('email')
        report_payload = {
            'start' : payload.get('start_date'),
            'end' : payload.get('end_date'),
            'tx_type' : payload.get('report_type'),
            'extra_data' : extra_filters,
            'employees': payload.get('employees')
        }
        thread_processor = ReportThreadProcessor(user_email, report_payload).start()