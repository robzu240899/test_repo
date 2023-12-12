import csv
from roommanager.models import LaundryRoom
from reporting.models import Client

with open("clientsmap.csv") as csvfile:
    csv_reader = csv.DictReader(csvfile)
    for row in csv_reader:
        try:
            client_name = row['client_name']
            try:
                client_object, created = Client.objects.get_or_create(name=client_name)
                print ("Client: {}".format(client_object))
            except Exception as e:
                raise (e)

            room = LaundryRoom.objects.get(display_name=row['location'])
            extension = room.laundryroomextension_set.first()
            bg = extension.billing_group

            print ("Extension: {}".format(extension))
            print ("BG: {}".format(extension.billing_group))
            if not bg.client:
                bg.client = client_object
                bg.save()
            else:
                print ("Already added client")
        except:
            print ("Couldnt find room with name: {}".format(row['location']))
            continue