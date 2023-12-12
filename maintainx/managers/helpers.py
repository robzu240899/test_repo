import logging
from cmmsproviders.assets.manager import AssetType
from roommanager.enums import VerboseMachineType, BundleType


logger = logging.getLogger(__name__)


class MachineHelper:

    def build_asset_payload(self, machine: AssetType) -> dict:
        """
        Controls the creation of the entire payload to be sent during creation or update of the associated
        asset record in Upkeep

        Params:
        machine : Machine
            Object instance
        """
        for field in self.create_required_fields:
            if getattr(machine, field, None) is None:
                err_str = 'Machine information is incomplete. Missing field: {}'.format(field)
                logger.error(err_str)
                raise Exception(err_str)

        #NOTE: Can change hardware bundles for machineslotmaps. Would that be more reliable?        
        related_slots, hardware_bundles, active_bundles = self.get_related_data(machine)
        location_bundles = hardware_bundles
        if active_bundles: location_bundles = active_bundles
        if all(related_slots): related_slots.sort(key=lambda x: x.web_display_name)
        self.latest_status_mapout = self.get_mapout_status(machine)
        category = VerboseMachineType.map_to_machinetype.get(machine.machine_type)
        location = location_bundles[0].location
        machine_name, status = self._build_asset_name(machine, related_slots, location)
        machine_model = machine.get_asset_model()
        machine_description = self._build_machine_description(machine, related_slots, active_bundles)
        if self.latest_status_mapout:
            machine_description += f" Latest Status Mapout: {self.latest_status_mapout.status}"
            machine_name += f" ({self.latest_status_mapout.status})"

        if machine_model is None:
            logger.error(
                f"Could not sync asset to {self.provider_name}: The Machine does not have an equipment type."
            )
            print (f"Could not sync asset to {self.provider_name}: The Machine does not have an equipment type.")
            return {}
        if getattr(location, self.provider_location_id_attr) is None:
            logger.error(
                f"Could not sync asset to {self.provider_name}: The location does not have a provider id"
            )
            print (f"Could not sync asset to {self.provider_name}: The location does not have a provider id")
            return {}
        payload = {
            'name' : machine_name,
            'model' : machine.get_asset_model(),
            'serial' : machine.asset_code, #Barcode
            'location' : getattr(location, self.provider_location_id_attr),
            'category' : category, #enums.WASHER, enums.DRYER
            'description' : machine_description,
        }
        return payload


class CardReaderHelper:
    admin_base_url = 'https://system.aceslaundry.com/admin/roommanager/cardreaderasset/{}/change/'

    def build_asset_payload(self, card_reader: AssetType) -> dict:
        payload = {}
        description = {
            'Condition' : card_reader.condition,
            'Link' : self.admin_base_url.format(card_reader.id)
        }
        current_bundle = card_reader.get_current_bundle()
        if current_bundle:
            if current_bundle.bundle_type in [BundleType.WAREHOUSE, BundleType.STACKED_WAREHOUSE]:
                description['Status'] = 'Warehouse'
            else:
                description['Status'] = 'Bundled'
            description['Machine'] = current_bundle.slot
            machine_url = self.get_asset_provider_url(current_bundle.machine)
            if machine_url: description['Associated Machine'] = machine_url
        else:
            description['Status'] = 'Available'
        self.latest_status_mapout = self.get_mapout_status(card_reader)
        if self.latest_status_mapout: description['Latest Status Mapout'] = self.latest_status_mapout.status
        related_slots, hardware_bundles, active_bundles = self.get_related_data(card_reader)
        location_bundles = hardware_bundles
        if active_bundles: location_bundles = active_bundles
        location = location_bundles[0].location if location_bundles else card_reader.get_location()
        name, status = self._build_asset_name(card_reader, related_slots, location)
        if self.latest_status_mapout: name += f" ({self.latest_status_mapout.status})"
        location = card_reader.get_location()
        if not getattr(location, self.provider_location_id_attr):
            self.location_manager().create_location(location)
            location.refresh_from_db()
        payload = {
            'name' : name,
            'model' : card_reader.get_asset_model(),
            'serial' : getattr(card_reader, 'card_reader_tag'),
            'location' : getattr(location, self.provider_location_id_attr),
            'category' : self.category,
            'description' : self._dict_as_string(description),
        }
        return payload