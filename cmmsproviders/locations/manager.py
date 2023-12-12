from cmmsproviders.base import AbstractLocationManagerClass
from roommanager.models import LaundryRoom
from main.decorators import ProductionCheck


class BaseLocationManager(AbstractLocationManagerClass):

    def __init__(self):
        self.API = self.API_CLASS()

    #@ProductionCheck
    def create_location(self, location):
        """
        Creates a new location in Upkeep and associates it to the location passed as parameter
        """
        assert isinstance(location, LaundryRoom)
        response = self.API.create_location(location)
        setattr(location, self.provider_id_attr, response['id'])
        location.save()

    #@ProductionCheck
    def update_location(self, location, **kwargs):
        assert isinstance(location, LaundryRoom)
        return self.API.update_location(location, **kwargs)

    @ProductionCheck
    def activate_location(self, location):
        assert isinstance(location, LaundryRoom)
        assert hasattr(location, self.provider_id_attr)
        current_name = self.API.get_location(getattr(location, self.provider_id_attr))['name']
        if 'DISABLED' in current_name:
            data = {'name': current_name.strip('DISABLED')}
            return self.API.update_location(location, **data)

    @ProductionCheck
    def deactivate_location(self, location):
        """
        Adds the word 'DISABLED' to the location's name in Upkeep
        """
        assert isinstance(location, LaundryRoom)
        assert hasattr(location, self.provider_id_attr)
        current_name = self.API.get_location(getattr(location, self.provider_id_attr))['name']
        if not 'DISABLED' in current_name:
            data = {'name': 'DISABLED ' + current_name}
            return self.API.update_location(location, **data)

    #@ProductionCheck
    def delete_location(self, location, **kwargs):
        assert isinstance(location, LaundryRoom)
        return self.API.delete_location(location, **kwargs)

    @ProductionCheck
    def sync_names(self):
        q = {f'{self.provider_id_attr}__isnull' : False}
        rooms = LaundryRoom.objects.filter(**q)
        for room in rooms:
            current_name = self.API.get_location(getattr(room, self.provider_id_attr))['name']
            if room.display_name != current_name:
                data = {'name': room.display_name}
                self.API.update_location(room, **data)

    @ProductionCheck
    def sync_locations(laundry_group_id):
        #check for both names and active status and update
        locations = LaundryRoom.objects.filter(laundry_group__id=laundry_group_id)
        for location in locations:
            if location.is_active:
                if hasattr(location, self.provider_id_attr):
                    fields_to_update = {}
                    provider_location = self.API.get_location(getattr(room, self.provider_id_attr))
                    self.update_location(location)
                else:
                    self.save_location(location)
            else:
                if hasattr(location, self.provider_id_attr):
                    self.deactivate_location(location)
                if location.display_name != provider_location.get('name'):
                    fields_to_update.update({'name':location.display_name})