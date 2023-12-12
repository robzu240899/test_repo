from fascard.api import *
from roommanager.models import LaundryRoom, MaintainxZipCodeRoom


class MaintainxZipCodeSyncing():
    """
    Associated maintainx locations with a corresponding parent zip-code-based location
    """

    def __init__(self):
        self.api = FascardApi()

    def run(self, rooms):
        for room in rooms:
            room_data = self.api.get_room(room.fascard_code)
            zip_code = room_data['ZipCode']
            maintainx_zipcode_room, created = MaintainxZipCodeRoom.objects.get_or_create(
                display_name=zip_code)
            if not maintainx_zipcode_room:
                print (f"Failed to get a zip-code location for zip code {zip_code}")
                continue
            maintainx_zipcode_room.refresh_from_db()
            if created: print (f"Created Zip Code location {maintainx_zipcode_room} (id {maintainx_zipcode_room.maintainx_id}) for room {room}")
            room.room_zip_code = zip_code
            room.address = room_data['Address']
            room.latitude = room_data['Latitude']
            room.longitude = room_data['Longitude']
            room.maintainx_zipcode_location_parent = maintainx_zipcode_room
            room.save()