import csv
from roommanager.models import LaundryRoom
from upkeep.manager import UpkeepManager

with open("locsmap.csv") as csvfile:
    csv_reader = csv.DictReader(csvfile)
    for row in csv_reader:
        try:
            room = LaundryRoom.objects.get(fascard_code=row['fascard'])
        except:
            print ("Couldnt find room with fascard code: {}".format(row['fascard']))
            continue
        room.upkeep_code = row['upkeep']
        room.save()

with open('tocreatemap.csv') as csvfile2:
    csv_reader = csv.DictReader(csvfile2)
    for row in csv_reader:
        try:
            room = LaundryRoom.objects.get(fascard_code=row['fascard'])
        except:
            print ("Couldnt find room with fascard code: {}".format(row['fascard']))
            continue
        
        try:
            UpkeepManager().create_location(room)
        except Exception as e:
            print ("Failed creating location in Upkeep with e: {}".format(e))