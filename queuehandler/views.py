'''
Created on Apr 23, 2017

@author: Thomas
'''
import boto3
import logging
from uuid import uuid1

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import  csrf_exempt
from django.views import View
from django.http import HttpResponse

from rest_framework.response import Response
from rest_framework import permissions, authentication, views, status 

from main import settings
from .nightly_run import NightlyRun, NightlyMetricsRun, TiedRunManager
from.job_creator import EmployeeScansAnalysisEnqueuer, MaintainxMeterUpdateEnqueuer
from .queue import InboundMessageManager

logger = logging.getLogger(__name__)

class QueueView(View):
    
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        if not settings.IS_BACKEND == True:
            exception_string = "Forbidden to access InboundMessageView unless on the backend environment"
            logger.error(exception_string) 
            raise Exception(exception_string)
        return super(QueueView, self).dispatch(request, *args, **kwargs)

         
class TestView(views.APIView):
    
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.BasicAuthentication]
    
    def post(self, request):
        return Response(status=status.HTTP_201_CREATED)

class NightlyRunEnqueue(views.APIView):
    
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.BasicAuthentication]

    @classmethod
    def _enqueue(cls, **received_kwargs):
        assert 'jobname' in received_kwargs
        sqs = boto3.resource('sqs')
        queue = sqs.get_queue_by_name(QueueName=settings.QUEUE_CREDENTIALS['NIGHTLY_RUN_QUEUE_NAME'])
        #input_parameters = {'jobname': kwargs.get('job_name')}
        input_parameters = received_kwargs
        formatted_params = {
            parameter_name: {
            'StringValue':str(parameter_value),'DataType': 'String'} for parameter_name,parameter_value in input_parameters.items()
        }
        entry = {   
                    'Id': str(uuid1()).replace("-",""),
                    'MessageBody': 'Insider Backend Message',
                    'MessageAttributes': formatted_params
                 }
        print (queue.send_messages(Entries=[entry]))
        return Response(status=status.HTTP_201_CREATED)

    def post(self, request, *args, **kwargs):
        return self._enqueue(**kwargs)


class EmployeeScansAnalysisEnqueuerView(views.APIView):

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.BasicAuthentication]

    def post(self, request, *args, **kwargs):
        EmployeeScansAnalysisEnqueuer.enqueue_job()
        logging.info("Successfully enqueued EmployeeScansAnalysis job")
        return Response(status=status.HTTP_201_CREATED)

class MaintainxMeterUpdateEnqueuerView(views.APIView):

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.BasicAuthentication]

    def post(self, request, *args, **kwargs):
        MaintainxMeterUpdateEnqueuer.enqueue_job()
        logging.info("Successfully enqueued Maintainx Meter Update job")
        return Response(status=status.HTTP_201_CREATED)


from django.core.mail import send_mail
class NightlyRunProcess(QueueView):

    @classmethod
    def extract_parameters(cls, request):
        dirty_attribute_keys = [x for x in request.__dict__['META'].keys() if x.startswith('HTTP_X_AWS_SQSD_ATTR')]
        parameters = {}
        for key in dirty_attribute_keys:
            parameters[key.split("HTTP_X_AWS_SQSD_ATTR_")[1].lower().strip()] = request.__dict__['META'][key]
        return parameters
    
    def post(self, request):
        raw_parameters = self.extract_parameters(request)
        job_type = raw_parameters.pop('jobname')
        try:
            steps_to_run = raw_parameters.pop('stepstorun')
        except KeyError:
            #if None were specified, run all
            steps_to_run = None
        notify_email = raw_parameters.get('notify')
        if job_type == 'nightlyrun':
            NightlyRun().run(steps_to_run=steps_to_run, notify_email=notify_email)
        elif job_type == 'nightlymetricsrun':
            NightlyMetricsRun().run()
        elif job_type == 'tiedrun':
            TiedRunManager.run(steps=steps_to_run)
        return HttpResponse("success")


# class TiedStepsNightlyRunView(views.APIView):
#     """
#     A nightly run based on tied-runs. It does not go through the Master environment.
#     It enqueues jobs directly 
#     """
#     permission_classes = [permissions.IsAuthenticated]
#     authentication_classes = [authentication.BasicAuthentication]

#     def post(self, request, *args, **kwargs):
#         TiedStepsNightlyRun.run(**kwargs)
#         return HttpResponse("Success")