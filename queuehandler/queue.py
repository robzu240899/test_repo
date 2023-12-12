import boto3
import json
import logging
import time
from collections import namedtuple
from datetime import date, datetime
from uuid import uuid1
from django.http import HttpResponse
from django.core.mail import send_mail
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import  csrf_exempt
from django.views import View
from django.db import transaction
from main import settings, utils
from reports.jobs import EventRuleProcessor
from .config import JobInstructions, QueueConfig
from .enums import ParameterType
from .models import NightlyRunTracker
from .utils import Aurora


logger = logging.getLogger(__name__)

class StepManager():
    """
    Receives a nightly run step, enqueues it and checks whether it ran successfuly or not.

    params: all fields in required_fields list declared as a class attribute
    """
    required_fields = (
        'step_name',
        'env_type',
        'enqueue_function',
        'wait_time',
        'number_retries',
        'retry_pause',
        'max_errors',
    )


    def __init__(self, **kwargs):
        for k,v in kwargs.items():
            setattr(self,k,v)
        assert all([hasattr(self, field) for field in self.required_fields])

    @classmethod
    @transaction.atomic
    def create_nightly_run_model(cls):
        nrt = NightlyRunTracker.objects.select_for_update().all().order_by('-start_time').first()
        if not nrt:
            nrt = NightlyRunTracker.objects.create()
        elif (datetime.now() - nrt.start_time).total_seconds() < 300:
            nrt = None
        else:
            nrt.start_time = datetime.utcnow()
            nrt.save()
        return nrt

    def handle_not_finished(self):
        exception = Exception("Early Termination- Taking Too Long")
        body = "Step %s did not finish inside the \
            specified window in environment %s" % (self.step_name, self.env_type)
        if hasattr(self, 'fail_tolerant') and getattr(self, 'fail_tolerant'):
            #the step is fail_tolerant
            utils.custom_capture_exception(exception)
            send_mail(body, body, settings.DEFAULT_FROM_EMAIL, settings.IT_EMAIL_LIST, fail_silently=False)
            return
        else:
            logging.info(f"The step {self.step_name} is not fault tolerant and is taking too long. Raising Exception")
            send_mail(body, body, settings.DEFAULT_FROM_EMAIL, settings.IT_EMAIL_LIST,
                        fail_silently=False)
            Aurora().modify_aurora_cluster_min_capacity(1)
            raise exception

    def handle_errored_out(self, queue_inspector):
        exception = Exception("Early Termination- Too Many Errors")
        body = "Step %s finished with too many errors in environment %s " % (self.step_name, self.env_type)
        if hasattr(self, 'fail_tolerant') and getattr(self, 'fail_tolerant'):
            #the step is fail_tolerant. Allows the manager to move onto the next step
            utils.custom_capture_exception(exception)
            send_mail(body, body, settings.DEFAULT_FROM_EMAIL, settings.IT_EMAIL_LIST,fail_silently=False)
            #if we are fail tolerant and we got any messages into the dead letter queue
            #we need to clean them up so the next step in the nightly run does not fail because of those messges
            #when the has_too_many_errors function is invoked.
            #TODO Clean sqs queue
            try:
                queue_inspector.sqs_client.purge_queue(QueueUrl=queue_inspector.dead_letter_queue.queue_url)
            except:
                logger.error("Failed cleaning deadletterqueue after fail-tolerant exception raised", exc_info=True)
            return
        else:
            send_mail(body, body, settings.DEFAULT_FROM_EMAIL, settings.IT_EMAIL_LIST,fail_silently=False)
            Aurora().modify_aurora_cluster_min_capacity(1)
            raise exception


    def run_step(self):
        start_msg = 'Starting step %s on %s' % (self.step_name,self.env_type)
        logger.info(start_msg)
        #send_mail(start_msg, start_msg, settings.DEFAULT_FROM_EMAIL, settings.IT_EMAIL_LIST,
        #              fail_silently=False)
        if hasattr(self, 'queue') and hasattr(self, 'deadqueue'):
            inspector = QueueInspector(queue_name=self.queue, dead_letter_queue_name=self.deadqueue)
        else:
            inspector = QueueInspector()
        logger.info("Inspector for step %s was initialized" % self.step_name)
        self.max_errors += inspector.get_number_messages_in_dead_letter_queue()
        if hasattr(self, 'enqueue_kwargs'):
            enqueue_kwargs = self.enqueue_kwargs
        else:
            enqueue_kwargs = None
        enqueue_function = getattr(self,'enqueue_function')
        if hasattr(self, 'queue'):
            enqueue_function(enqueue_kwargs, queue=self.queue)
        else:
            enqueue_function(enqueue_kwargs)
        logger.info("Starting inspector on step %s " % self.step_name)
        is_finished = inspector.is_finished(self.wait_time, self.number_retries, self.retry_pause)
        logger.info("Finished inspector on step %s " % self.step_name)
        if not is_finished:
            self.handle_not_finished()
        errored_out = inspector.has_too_many_errors(self.max_errors)
        if errored_out:
            self.handle_errored_out(inspector)
        end_msg = 'Finished step %s on %s' % (self.step_name,self.env_type)
        logger.info(end_msg)
        #msg = 'Step %s finished' % step_name
        #send_mail(msg, msg, settings.DEFAULT_FROM_EMAIL, settings.IT_EMAIL_LIST,
        #              fail_silently=False)

class QueueInspector():

    Queue = namedtuple('Queue', ['queue_name','queue_url'])

    def __init__(self,queue_name=QueueConfig.PRODUCTION_QUEUE_NAME,dead_letter_queue_name=QueueConfig.PRODUCTION_DEADLETTER_QUEUE_NAME):
        self.sqs_resource = boto3.resource('sqs')
        self.sqs_client = boto3.client('sqs')

        self.main_queue = QueueInspector.Queue(
                               queue_name=queue_name,
                               queue_url=self.sqs_client.get_queue_url(QueueName=queue_name)['QueueUrl']
                           )

        self.dead_letter_queue = QueueInspector.Queue(
                       queue_name=dead_letter_queue_name,
                       queue_url=self.sqs_client.get_queue_url(QueueName=dead_letter_queue_name)['QueueUrl']
                   )

    def get_number_messages_in_queue(self):
        return self._get_number_messages(self.main_queue.queue_url)

    def get_number_messages_in_dead_letter_queue(self):
        return self._get_number_messages(self.dead_letter_queue.queue_url)


    def is_finished(self,initial_pause=10,number_retries=10,retry_pause=1):
        time.sleep(initial_pause*60)
        for _ in range(number_retries+1):
            number_in_queue = self.get_number_messages_in_queue()
            if number_in_queue == 0:
                return True
            else:
                time.sleep(retry_pause*60)
        return False

    def has_too_many_errors(self,max_dead_letter_size):
        logger.info("Executing has too many errors checker")
        num_errors = self.get_number_messages_in_dead_letter_queue()
        logger.info(
            f"Current number of errors in deadletter queue({self.dead_letter_queue.queue_url}): {num_errors}"
        )
        if num_errors > max_dead_letter_size:
            return True
        else:
            return False

    def _get_number_messages(self,queue_url):
        attrs = self.sqs_client.get_queue_attributes(
            QueueUrl=queue_url,AttributeNames=['ApproximateNumberOfMessages','ApproximateNumberOfMessagesNotVisible'])
        x = int(attrs['Attributes']['ApproximateNumberOfMessages'])
        y = int(attrs['Attributes']['ApproximateNumberOfMessagesNotVisible'])
        return x + y


class Enqueuer():
    """
    Enqueues a given message to the given SQS queue
    """

    def __init__(self,batch_size=10,queue_name=QueueConfig.PRODUCTION_QUEUE_NAME):
        self.batch_size = batch_size
        self.queue_name = queue_name
        self.sqs = boto3.resource('sqs')
        self.queue = self.sqs.get_queue_by_name(QueueName=queue_name)
        self.entries = []

    def add_message(self,job_name,input_parameters):
        logger.info(f"Sending message to Queue. Job: {job_name}. Params: {input_parameters}")
        job_instruction = JobInstructions.INSTRUCTIONS[job_name]
        self.__check_parameter_validity(input_parameters,job_instruction.parameter_instructions)
        entry = self.__format_entry(input_parameters,job_instruction.parameter_instructions,job_name)
        self.entries.append(entry)
        if len(self.entries) == self.batch_size:
            response = self.queue.send_messages(Entries=self.entries)
            if 'Failed' in response.keys():
                exception_string = "Failed to enqueue messages"
                logger.error(exception_string)
                raise Exception(exception_string)
            self.entries = []

    def close(self):
        if len(self.entries) > 0:
            self.queue.send_messages(Entries=self.entries)

    def __check_parameter_validity(self,input_parameters,parameter_instructions):
        #check no missing instructions:
        for parameter_instruction_name in parameter_instructions.keys():
            if parameter_instruction_name not in input_parameters.keys():
                exception_string = "Missing %s from parameters in Enqueuer.enque" % parameter_instruction_name
                logger.error(exception_string)
                raise Exception(exception_string)
        #check no extra instructions
        for input_parameter_name in input_parameters.keys():
            if input_parameter_name not in parameter_instructions.keys():
                exception_string = "Unknown parameter %s in parameters in Enqueuer.enque" % input_parameter_name 
                logger.error(exception_string)
                raise Exception(exception_string)
        #check parameter types
        for input_parameter_name,input_parameter_value in input_parameters.items():
            instruction = parameter_instructions[input_parameter_name]
            if instruction.parameter_type == ParameterType.STRING:
                obj_class = str
            elif instruction.parameter_type == ParameterType.INTEGER:
                obj_class = int
            elif instruction.parameter_type == ParameterType.DATE:
                obj_class = date
                assert(not isinstance(input_parameter_value, datetime))
            else:
                exception_string = "Unknown/Not Implemented Paramter Type in __check_parameter_validity"
                logger.error(exception_string)
                raise Exception(exception_string)
            assert(isinstance(input_parameter_value, obj_class))

    def __format_entry(self,input_parameters,parameter_instructions,job_name):
        input_parameters['jobname'] = job_name
        formatted_params = {parameter_name: {'StringValue':str(parameter_value),'DataType': 'String'} for parameter_name,parameter_value in input_parameters.items()}
        entry = {
                    'Id': str(uuid1()).replace("-",""),
                    'MessageBody': 'Insider Backend Message',
                    'MessageAttributes': formatted_params
                 }
        return entry


class InboundMessageView(View):

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        if not settings.IS_BACKEND == True:
            exception_string = "Forbidden to access InboundMessageView unless on the backend environment"
            logger.error(exception_string)
            raise Exception(exception_string)
        return super(InboundMessageView, self).dispatch(request, *args, **kwargs)

    @csrf_exempt
    def post(self,request):
        InboundMessageManager.process_message(request)
        return HttpResponse("success")

class InboundMessageManager():

    @classmethod
    def process_message(cls,request):
        job_type = 'unknown'
        try:
            try:
                parsed_body = json.loads(request.body)
            except:
                parsed_body = None
            if parsed_body:
                if 'detail-type' in parsed_body and 'source' in parsed_body:
                    logger.info("Processing EventRule job")
                    return cls._event_rule_manager(parsed_body)
            raw_parameters = cls.__extract_parameters(request)
            job_type = raw_parameters.pop('jobname')
            job_instruction = JobInstructions.INSTRUCTIONS[job_type]
            parameters = cls.__clean_parameters(raw_parameters,job_instruction) 
            start = time.time()
            job_instruction.processing_function(**parameters)
            end = time.time()
        except Exception as e:
            err_str = "The Job: {} failed with Exception: {}".format(job_type, e)
            logger.error(err_str, exc_info=True)
            raise Exception(err_str)

    @classmethod
    def __extract_parameters(cls,request):
        dirty_attribute_keys = [x for x in request.__dict__['META'].keys() if x.startswith('HTTP_X_AWS_SQSD_ATTR')]
        parameters = {}
        for key in dirty_attribute_keys:
            parameters[key.split("HTTP_X_AWS_SQSD_ATTR_")[1].lower().strip()] = request.__dict__['META'][key]
        return parameters

    @classmethod
    def _event_rule_manager(cls, parsed_body):
        if parsed_body.get('source') == 'aws.events':
            result = EventRuleProcessor(parsed_body).process()
            return result
        return False

    @classmethod
    def __clean_parameters(cls,raw_parameters,job_instruction):
        parameters = {}
        for parameter_name,raw_value in raw_parameters.items():
            parameter_instruction = job_instruction.parameter_instructions[parameter_name]
            argument_name = parameter_instruction.argument_name
            if parameter_instruction.parameter_type == ParameterType.STRING:
                parameters[argument_name] = raw_value
            elif parameter_instruction.parameter_type == ParameterType.INTEGER:
                parameters[argument_name] = int(raw_value)
            elif parameter_instruction.parameter_type == ParameterType.DATE:
                parameters[argument_name] = datetime.strptime(raw_value,'%Y-%m-%d').date()
            else:
                exception_string = "Unknown/Not Implemented Paramter Type in __check_parameter_validity"
                logger.error(exception_string)
                raise Exception(exception_string)
        return parameters