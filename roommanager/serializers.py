from rest_framework import serializers
from roommanager.models import LaundryRoom, Machine, Slot


class LaundryRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = LaundryRoom
        fields = ('id', 'display_name', 'laundry_group')


class MachineSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Machine
        fields = ('id', 'machine_text')


class SlotSerializer(serializers.ModelSerializer):
    long_name = serializers.SerializerMethodField()

    def get_long_name(self, slot):
        return str(slot)
    
    class Meta:
        model = Slot
        fields = ('id', 'web_display_name', 'long_name')
