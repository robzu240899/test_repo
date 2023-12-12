import pytz
from abc import ABCMeta, abstractmethod

class AbstractLocationManagerClass:
    __metaclass__ = ABCMeta

    @abstractmethod
    def create_location(self):
        raise NotImplementedError

    @abstractmethod
    def update_location(self, room):
        raise NotImplementedError

    @abstractmethod
    def activate_location(self, room):
        raise NotImplementedError

    @abstractmethod
    def deactivate_location(self, room):
        raise NotImplementedError

    @abstractmethod
    def delete_location(self, room):
        raise NotImplementedError

    @abstractmethod
    def sync_names(self):
        raise NotImplementedError

    @abstractmethod
    def sync_locations(self):
        raise NotImplementedError
    


class AbstractAssetManagerClass:
    __metaclass__ = ABCMeta

    @abstractmethod
    def _get_hardware_bundles(self):
        raise NotImplementedError

    @abstractmethod
    def _build_asset_name(self):
        raise NotImplementedError
    
    @abstractmethod
    def create_asset_meter(self):
        raise NotImplementedError

    @abstractmethod
    def _get_custom_fields_payload(self):
        raise NotImplementedError

    @abstractmethod
    def create_or_update_meter(self):
        raise NotImplementedError

    @abstractmethod
    def get_mapout_status(self):
        raise NotImplementedError

    @abstractmethod
    def create_or_update(self):
        raise NotImplementedError

    @abstractmethod
    def _fetch_extra_fields(self):
        raise NotImplementedError

    @abstractmethod
    def _handle_extra_fields(self):
        raise NotImplementedError

    @abstractmethod
    def build_asset_payload(self, asset):
        raise NotImplementedError

    @abstractmethod
    def sync_asset_meters(self):
        raise NotImplementedError

    @abstractmethod
    def sync_room_meters(self):
        raise NotImplementedError

    @abstractmethod
    def get_asset_provider_url(self):
        raise NotImplementedError


class AbstractWorkOrderManager:
    __metaclass__ = ABCMeta

    @abstractmethod
    def update_record(self, record_obj):
        raise NotImplementedError

    @abstractmethod
    def run(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def clean_date(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def transform_record(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def update_record(self, *args, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def create_work_order(self, *args, **kwargs):
        raise NotImplementedError
    



