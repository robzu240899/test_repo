import csv
from roommanager.models import MachineMeter
from datetime import datetime


class FixMeter:

    @classmethod
    def run(cls):
        with open('meters.csv') as f:
            reader = csv.reader(f)
            for row in reader:
                upkeep_id = row[0]
                current_count = int(row[1])
                if not upkeep_id:
                    continue
                try:
                    current_meter = MachineMeter.objects.get(
                        upkeep_id = upkeep_id
                    )
                except:
                    continue
                machine = current_meter.machine
                q = machine.laundrytransaction_set.filter(
                    transaction_type='100',
                    assigned_local_transaction_time__gte=datetime(2020,8,15,0,0,0)
                )
                new_count = current_count + q.count()
                current_meter.transactions_counter = new_count
                current_meter.save()