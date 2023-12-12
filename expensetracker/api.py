from datetime import datetime
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.views import APIView
from expensetracker.serializers import (
    JobSerializer,
    LineItemSerializer,
    TechnicianSerializer)
from expensetracker.enums import JobStatus, JobType, LineItemType, LineItemStatus
from expensetracker.models import Job, Technician, LineItem


class TechnicianList(generics.ListAPIView):
    queryset = Technician.objects.all()
    serializer_class = TechnicianSerializer


class JobList(APIView):
    authentication_classes = ()

    def post(self, request, format=None):
        queryset = Job.objects.all()
        if request.data.get('laundry_room', None):
            queryset = queryset.filter(laundry_room=request.data.get('laundry_room')['id'])
        if request.data.get('machine', None):
            queryset = queryset.filter(machine=request.data.get('machine')['id'])
        if request.data.get('status', None):
            queryset = queryset.filter(status=request.data.get('status'))
        if request.data.get('start_date', None):
            queryset = queryset.filter(start_date__gte=request.data.get('start_date'))
        if request.data.get('final_date', None):
            queryset = queryset.filter(start_date__lte=request.data.get('final_date'))
        serializer = JobSerializer(queryset, many=True)
        return Response(serializer.data)


class JobDetail(APIView):
    authentication_classes = ()

    def post(self, request, format=None):
        serializer = JobSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk, format=None):
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = JobSerializer(job, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LineItemDetail(APIView):
    authentication_classes = ()

    def post(self, request, format=None):
        serializer = LineItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk, format=None):
        try:
            line_item = LineItem.objects.get(pk=pk)
        except LineItem.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = LineItemSerializer(line_item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def job_status_list(request):
    """
    List all job statuses.
    """
    if request.method == 'GET':
        statuses = [status[0] for status in JobStatus.CHOICES]
        return Response(statuses)

@api_view(['GET'])
def job_type_list(request):
    """
    List all job types.
    """
    if request.method == 'GET':
        types = [t[0] for t in JobType.CHOICES]
        return Response(types)

@api_view(['GET'])
def line_item_type_list(request):
    """
    List all line_item types.
    """
    if request.method == 'GET':
        types = [t[0] for t in LineItemType.CHOICES]
        return Response(types)

@api_view(['GET'])
def line_item_status_list(request):
    """
    List all line_item statuses.
    """
    if request.method == 'GET':
        statuses = [t[0] for t in LineItemStatus.CHOICES]
        return Response(statuses)
