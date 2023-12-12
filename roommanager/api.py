from datetime import datetime
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView
from roommanager.models import LaundryRoom, Machine, Slot
from roommanager.serializers import (
    LaundryRoomSerializer,
    MachineSerializer,
    SlotSerializer)


class LaundryRoomList(generics.ListAPIView):
    queryset = LaundryRoom.objects.all()
    serializer_class = LaundryRoomSerializer


class MachineList(generics.ListAPIView):
    queryset = Machine.objects.all()
    serializer_class = MachineSerializer


class SlotList(generics.ListAPIView):
    queryset = Slot.objects.all().prefetch_related('laundry_room')
    serializer_class = SlotSerializer
