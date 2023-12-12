from rest_framework import serializers
from expensetracker.models import Job, Technician, LineItem
from expensetracker import enums


class TechnicianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Technician
        fields = ('id', 'employment_type',)


class LineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LineItem
        fields = '__all__'

    def validate(self, data):
        if data['line_item_type'] == enums.LineItemType.LABOR:
            if not data['technician']:
                raise serializers.ValidationError({'technician': [("Technician must be filled in for type labor.")]})
        elif data['line_item_type'] == enums.LineItemType.PART:
            if data['technician'] is not None:
                raise serializers.ValidationError({'technician': [("Technician must be null for type part.")]})

        if data['status'] == enums.LineItemStatus.CLOSED:
            if not data['start_date']:
                raise serializers.ValidationError({'start_date': [("Start date must be filled in.")]})
            if not data['finish_date']:
                raise serializers.ValidationError({'finish_date': [("Finish date must be filled in.")]})
        elif data['status'] == enums.LineItemStatus.IN_PROGRESS:
            if not data['start_date']:
                raise serializers.ValidationError({'start_date': [("Start date must be filled in.")]})
        elif data['status'] == enums.LineItemStatus.CREATED:
            if data['start_date'] is not None:
                raise serializers.ValidationError({'start_date': [("Start date must be null.")]})

        if data['line_item_type'] == enums.LineItemType.LABOR:
            if data['technician']:
                if data['technician'].employment_type == enums.EmploymentType.EMPLOYEE:
                    if not data['time']:
                        raise serializers.ValidationError({'time': [("Time must be filled in.")]})
                else:
                    if data['time']:
                        raise serializers.ValidationError({'time': [("Time must be null.")]})
                    if not data['cost']:
                        raise serializers.ValidationError({'cost': [("Cost must be filled in.")]})
            else:
                if data['time']:
                    raise serializers.ValidationError({'time': [("Time must be null.")]})
                if not data['cost']:
                    raise serializers.ValidationError({'cost': [("Cost must be filled in.")]})
        else:
            if data['time']:
                raise serializers.ValidationError({'time': [("Time must be null.")]})
            if not data['cost']:
                raise serializers.ValidationError({'cost': [("Cost must be filled in.")]})

        return data


class JobSerializer(serializers.ModelSerializer):
    line_items = LineItemSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = '__all__'

    def validate(self, data):
        if not data['laundry_room'] and not data['machine']:
            raise serializers.ValidationError(("At least one machine or laundry room must be filled in."))

        if data['status'] == enums.JobStatus.CLOSED:
            if not data['final_date']:
                raise serializers.ValidationError({'final_date': [("Final date must be filled in for status closed.")]})

        return data
