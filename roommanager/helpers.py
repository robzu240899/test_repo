import requests
from io import BytesIO
from datetime import datetime
from lxml import etree
from fascard.api import *
from maintainx.api import MaintainxAPI
from roommanager import models 
from revenue.models import LaundryTransaction
from .models import MachineSlotMap, Slot, Machine
from .enums import MachineType, LanguageChoices

class Helpers(object):
     
    @classmethod 
    def get_active_slots(cls,location_id,use_room=True):
        '''
        @location_id key for the location we are filtering for 
        @use_room  boolean.  True=get slots at room level.  False= get slots at group level 
        @returns queryset of active slots
        '''
        if use_room == True:
            return models.Slot.objects.filter(laundry_room_id=location_id,is_active=True,
                                              laundry_room__is_active=True)   
        else:
            return models.Slot.objects.filter(laundry_room__laundry_group_id=location_id,
                                              is_active=True,
                                              laundry_room__is_active=True
                                              )
             
             
class UploadAssetAttachments():
    """
        Uploads attachments for an asset in Maintainx
    """
    
    @classmethod
    def _read_picture(cls, picture_url):
        if not picture_url: return None
        response = requests.get(picture_url)
        if response.status_code == 200: return BytesIO(response.content)
        else: return None

    @classmethod
    def upload_binary_data(cls, asset_id, binary_data, filename):
        api = MaintainxAPI()
        upload_response = api.update_asset_attachment(asset_id, binary_data, filename)
        assert upload_response['publicUrl']
        machine = models.Machine.objects.get(maintainx_id = asset_id)
        return models.MachineAttachmentTracker.objects.create(
            attachment_maintainx_url = upload_response['publicUrl'],
            machine = machine,
        )

    @classmethod
    def run(cls, asset_id, fields=[]):
        if not fields: fields = ['asset_picture', 'asset_serial_picture']
        machine_obj = models.Machine.objects.get(id=asset_id)
        for field in fields:
            picture_url = getattr(machine_obj, field)
            if not picture_url: continue
            if picture_url == 'NOT_AVAILABLE': continue
            try:
                records = models.MachineAttachmentTracker.objects.filter(url=picture_url)
                if records: continue
            except models.MachineAttachmentTracker.DoesNotExist:
                pass
            binary_data = cls._read_picture(picture_url)
            if not binary_data: continue
            file_name = getattr(machine_obj, field).split('/')[-1]
            try:
                cls.upload_binary_data(machine_obj.maintainx_id, binary_data, file_name)
            except:
                logger.error(f"Failed uploading {field} for machine with id {asset_id}.", exc_info=True)


class EquipmentTypeNameManager:

    def __init__(self, equipment_type):
        assert isinstance(equipment_type, models.EquipmentType)
        self.equipment_type = equipment_type
        self.initialize_data()

    @classmethod
    def parse_name(self, name):
        print(name)
        assert '--' in name
        name_scheme = name.split('--')
        name_scheme = [x.lower().strip() for x in name_scheme]
        assert len(name_scheme) >= 2
        extra_data = ''
        d = {
            'make': name_scheme[0],
            'model': name_scheme[1],
            'extra': extra_data.join(name_scheme[2:])
        }
        return d

    def initialize_data(self):
        name_scheme = self.parse_name(self.equipment_type.machine_text)
        self.make = name_scheme.get('make')
        self.model = name_scheme.get('model')

    def equals(self, second_equipment):
        assert isinstance(second_equipment, models.EquipmentType)
        second_equipment_name = self.parse_name(second_equipment.machine_text)
        second_equipment_make = second_equipment_name.get('make')
        second_equipment_model = second_equipment_name.get('model')

        if self.make == second_equipment_make and self.model == second_equipment_model:
            return True
        else:
            return False


class MissingBundleFinder():

    def check(self, room):
        need_scan = []
        for slot in room.slot_set.filter(is_active=True):
            machine = slot.get_current_machine(slot)
            if machine: 
                if machine.placeholder: need_scan.append(slot)
            else:
                need_scan.append(slot)
        return need_scan

    def _format(self, data):
        msg = ''
        for d in data: msg += f'{d}\n'
        return msg

    def get(self, room):
        need_scan = self.check(room)
        return self._format(need_scan)

class XMLResponse():

    def __init__(self, text_message):
        self.xml_root = etree.Element('xml')
        self.message_root = etree.Element('message')
        self.status_element = etree.Element('status')
        self.status_element.text = '1' #TODO: Implementing 1 as default. Gotta check if there are other codes for better verbosity
        self.text_element = etree.Element('text')
        self.text_element.text = text_message

    def get_response(self):
        self.message_root.append(self.status_element)
        self.message_root.append(self.text_element)
        self.xml_root.append(self.message_root)
        return etree.tostring(self.xml_root, xml_declaration=True, encoding='UTF-8')

#Deprecated in favor of a simple 
#transaction count
class DryerStartsCounter:

    @classmethod
    def get_count(cls, room):
        msm_queryset = MachineSlotMap.objects.filter(
            slot__laundry_room=room,
            machine__machine_type=MachineType.DRYER,
            machine__placeholder=False)
        total = 0
        for msm in msm_queryset:
            start_time = getattr(msm, 'start_time', None)
            if not start_time: continue
            end_time = getattr(msm, 'end_time', None)
            if not end_time: end_time = datetime.today()
            total += LaundryTransaction.objects.filter(
                machine = msm.machine,
                assigned_local_transaction_time__gte=start_time,
                assigned_local_transaction_time__lte=end_time).count()
        return total


def get_equipment_type(fascard_equipment_id, location):
    try:
        equipment_type = models.EquipmentType.objects.get(
            fascard_id = fascard_equipment_id,
            laundry_group_id = location.laundry_group_id
        )
        return equipment_type
    except Exception as e:
        raise Exception(
            'Failed to load EquipmentType instance with fascard id: {}. Laundry Room: {}({}). Exception: {}'.format(
                fascard_equipment_id,
                location,
                location.fascard_code,
                e
            )
        )

class MachineSlotMapUpdateManager():

    def __init__(self, slot):
        self.slot = slot

    @classmethod
    def update_transactions(self, start, end, slot_id, machine_id):
        machine = Machine.objects.get(id=machine_id)
        slot = Slot.objects.get(id=slot_id)
        if end is None:
            q = LaundryTransaction.objects.filter(
                slot=slot,
                utc_transaction_time__gte=start,
            )
        else:
            q = LaundryTransaction.objects.filter(
                slot=slot,
                utc_transaction_time__gte=start,
                utc_transaction_time__lte=end
            )
        for tx in q:
            tx.machine = machine
            tx.save()

    @staticmethod
    def get_previous_msm(msm, from_date=None):
        if from_date is None:
            from_date = msm.start_time
        print ("Getting previous msm using from_date: {}".format(from_date))
        previous_msm = MachineSlotMap.objects.filter(
            slot=msm.slot,
            start_time__lt=from_date
        ).exclude(id=msm.id).order_by('-start_time').first()

        return previous_msm

    @staticmethod
    def get_next_msm(msm):
        next_msm = MachineSlotMap.objects.filter(
                slot=msm.slot,
                #is_active=True,
                start_time__gte=msm.start_time
        ).first()
        return next_msm


    def effectuation_date_update(self):
        update_tx = False
        self.original_instance = MachineSlotMap.objects.get(pk=self.pk)
        #Is start_time being changed?
        utc = pytz.timezone('UTC')
        if original_instance.start_time != self.start_time:
            previous_msm = MachineSlotMap.objects.filter(
                slot=self.slot,
                #is_active=True,
                end_time__lte=original_instance.start_time
            ).order_by('-start_time').first()
            self.start_time = self.start_time.astimezone(utc)
            if previous_msm:
                previous_msm.end_time = self.start_time
                previous_msm.save()
                update_tx = True


        if original_instance.end_time is not None and original_instance.end_time != self.end_time:
            #Update the start_time of the next MachineSlotMap
            next_msm = MachineSlotMap.objects.filter(
                slot=self.slot,
                #is_active=True,
                start_time__gte=original_instance.start_time
            ).first()
            self.end_time = self.end_time.astimezone(utc)
            if next_msm:
                next_msm.start_time = self.end_time
                next_msm.save()
                update_tx = True

        if update_tx:
            self.update_transactions(
                start=self.start_time,
                end=self.end_time,
                slot=self.slot,
                machine=self.machine
            )


class MessagesTranslationHelper:
    database = {
        'successful_cardreader_change' : {
            LanguageChoices.ENGLISH : "Successfully changed the *Card Reader* of the hardware bundle",
            LanguageChoices.SPANISH : "Se cambió exitosamente el *Lector de tarjetas* de la asociacion de piezas"
        },
        'successful_machine_change' : {
            LanguageChoices.ENGLISH : "Successfully changed the *Machine* of the hardware bundle",
            LanguageChoices.SPANISH : "Se cambió exitosamente la *Maquina* de la asociacion de piezas"
        },
        'successful_slot_change' : {
            LanguageChoices.ENGLISH : "Successfully changed the *Slot* of the hardware bundle",
            LanguageChoices.SPANISH : "Se cambió exitosamente el *Slot* de la asociacion de piezas"
        },
        'successful_newbundle' : {
            LanguageChoices.ENGLISH : "Successfully created new hardware bundle",
            LanguageChoices.SPANISH : "Se creó exitosamente una nueva asociacion de piezas"
        },
        'successful_warehousing' : {
            LanguageChoices.ENGLISH : "Successfully warehoused machine and card reader bundle",
            LanguageChoices.SPANISH : "Se escaneó exitosamente la Maquina y el Lector de tarjetas en la bodega"
        },
        'picture_missing' : {
            LanguageChoices.ENGLISH : "Asset Picture is missing",
            LanguageChoices.SPANISH : "La foto de la maquina aun no ha sido escaneada"
        },
        'serial_picture_missing' : {
            LanguageChoices.ENGLISH : "Asset Serial Picture is missing",
            LanguageChoices.SPANISH : "La foto del numero serial de la maquina aun no ha sido escaneada"
        },
        'serial_number_missing' : {
            LanguageChoices.ENGLISH : "Asset Serial Number is missing",
            LanguageChoices.SPANISH : "El numero serial de la maquina aun no ha sido escaneado"
        },
        'factory_model_missing' : {
            LanguageChoices.ENGLISH : "Asset's Factory Model is missing",
            LanguageChoices.SPANISH : "El modelo de fabrica de la maquina aun no ha sido escaneado"
        },
        'bundle_requires_approval' : {
            LanguageChoices.ENGLISH : "[URGENT] A Bundle Change Requires Approval",
            LanguageChoices.SPANISH : "[URGENTE] Un cambio de asociacion require aprobación"
        },
        'asset_update_requires_approval' : {
            LanguageChoices.ENGLISH : "[URGENT] A Bundle Update Requires Approval",
            LanguageChoices.SPANISH : "[URGENTE] Una actualizacion require aprobación"
        },
        'msm_doesnt_exist' : {
            LanguageChoices.ENGLISH : "The MachineSlotMap for the slot being paired does not exist",
            LanguageChoices.SPANISH : "El mapa Maquina-Slot (MachineSlotMap) para el slot que esta siendo emparejado/asociado no existe"
        },
        'pieces_bundled' : {
            LanguageChoices.ENGLISH : "The pieces were bundled already",
            LanguageChoices.SPANISH : "Las piezas ya fueron asociadas previamente"
        },
        'asset_update_approval_sent' : {
            LanguageChoices.ENGLISH : "Some attributes were updated and an approval request was created",
            LanguageChoices.SPANISH : "Algunos atributos de estas piezas fueron actualizados y se creó una solicitud de aprobacion"
        },
        'warehouse_born_prohibited' : {
            LanguageChoices.ENGLISH : "Warehouse-born bundles are not allowed",
            LanguageChoices.SPANISH : "Las asociaciones nuevas hechas en la bodega no estan permitidas"
        },
        'bundle_approval_overwritten' : {
            LanguageChoices.ENGLISH : "A Previous Bundle Change Request for the same pieces is being overwritten by this new submission.",
            LanguageChoices.SPANISH : "Una solicitud previa de asociación para estas piezas está siendo reemplazada por este nuevo escaneo."
        },
        'enqueued_bundled' : {
            LanguageChoices.ENGLISH : "Enqueued bundle change ({}) for approval. Please call to the office",
            LanguageChoices.SPANISH : "Se agendó el cambio de asociación ({}) para ser aprobado. Por favor llamar a la oficina"
        },
        'scanning_failed' : {
            LanguageChoices.ENGLISH : "Scanning process Failed with Exception: {}",
            LanguageChoices.SPANISH : "El proceso de escaneo falló con el error: {}"
        },
        'unknown_exception' : {
            LanguageChoices.ENGLISH : "Unknown exception: {}",
            LanguageChoices.SPANISH : "Error desconocido: {}"
        },
        'missing_fields' : {
            LanguageChoices.ENGLISH : "MISSING FIELDS: ",
            LanguageChoices.SPANISH : "CAMPOS FALTANTES: "
        },
        'updated_fields' : {
            LanguageChoices.ENGLISH : "UPDATED FIELDS: ",
            LanguageChoices.SPANISH : "CAMPOS ACTUALIZADOS: "
        },
        'slot_inactive' : {
            LanguageChoices.ENGLISH : "Slot is no longer active",
            LanguageChoices.SPANISH : "El Slot ya no está activo"
        },
        'slot_doesnt_exist' : {
            LanguageChoices.ENGLISH : "Slot retrieved by Fascard does not exists in reporting server",
            LanguageChoices.SPANISH : "El Slot retornado por fascard no existe en nuestros servidores. Contactar a la oficina."
        },
        'codes_are_the_same' : {
            LanguageChoices.ENGLISH : "Fascard Reader code and Asset code are the same",
            LanguageChoices.SPANISH : "Invalido. El codigo (tag) del lector de fascard y el codigo (tag) de la maquina son el mismo"
        },
        'datamatrix_doesnt_exists' : {
            LanguageChoices.ENGLISH : "No response from fascard. DataMatrix relation does not exist",
            LanguageChoices.SPANISH : "No se obtuvo respuesta de Fascard. El codigo matriz no existe"
        },
        'invalid_current_tag' : {
            LanguageChoices.ENGLISH : "Invalid current tag. There is no existing asset with the specified current tag",
            LanguageChoices.SPANISH : "Tag actual invalido. No existe ningun dispositivo con ese tag"
        },
        'invalid_new_tag' : {
            LanguageChoices.ENGLISH : "Invalid new tag. There is an existing asset",
            LanguageChoices.SPANISH : "El tag nuevo es invalido. Ya existe un dispositivo con ese tag"
        },
        'no_valid_tag_record' : {
            LanguageChoices.ENGLISH : "Invalid tag: %(tag)s. There is no existing ValidTag record for this tag",
            LanguageChoices.SPANISH : "Tag invalido: %(tag)s. No existe ningun registro ValidTag para este tag"
        },
        'tag_swap' : {
            LanguageChoices.ENGLISH : "Previous tag: %(current_tag)s. New Tag: %(new_tag)s.",
            LanguageChoices.SPANISH : "Anterior Tag: %(current_tag)s. Nuevo Tag: %(new_tag)s."
        },
        'tag_swap_approval_email_subject' : {
            LanguageChoices.ENGLISH : "Tag Swap requires approval. Please call to the office",
            LanguageChoices.SPANISH : "El cambio de tags requiere aprobación. Por favor contacte a la oficina"
        },
        'tag_swap_approval_email_body' : {
            LanguageChoices.ENGLISH : "%(rendered_response)s. Tag Swap Enqueued for approval. Please call to the office",
            LanguageChoices.SPANISH : "%(rendered_response)s. El cambio de tags se agendó para aprobacion. Por favor llamar a la oficina"
        },
        'successful_tag_swap' : {
            LanguageChoices.ENGLISH : "Successful change of tags",
            LanguageChoices.SPANISH : "Cambio de tags exitoso"
        },
        'unsuccessful_tag_swap' : {
            LanguageChoices.ENGLISH : "Unsuccessful change of tags",
            LanguageChoices.SPANISH : "Cambio de tags fallido"
        },
        #MessagesTranslationHelper.get('pieces_bundled', self.user_language)
        'asset_already_warehoused' : {
            LanguageChoices.ENGLISH : "The asset is already on the warehouse",
            LanguageChoices.SPANISH : "El dispositivo ya está en la bodega"
        },
        'asset_already_disposed' : {
            LanguageChoices.ENGLISH : "The asset was marked as disposed before",
            LanguageChoices.SPANISH : "El dispositivo fue marcado como desechado anteriormente"
        },
        'mapout_approval' : {
            LanguageChoices.ENGLISH : "Mapout Action Enqueued for approval. Please call to the office",
            LanguageChoices.SPANISH : "Movimiento agendado para aprobación. Por favor llamar a la oficina."
        },
        'successful_mapout' : {
            LanguageChoices.ENGLISH : "Successful Map out",
            LanguageChoices.SPANISH : "Movimiento exitoso"
        },
        'unsuccessful_mapout' : {
            LanguageChoices.ENGLISH : "Unsuccessful Map out",
            LanguageChoices.SPANISH : "El movimiento falló"
        },
        'card_reader_tag_as_machine' : {
            LanguageChoices.ENGLISH : "Wrong bundle. You are trying to assign a Card Reader Tag to a Machine",
            LanguageChoices.SPANISH : "Scan Incorrecto. Estas intentado asignarle a la maquina un tag que corresponde a lector de tarjetas"
        }
    }

    @classmethod
    def get(cls, key, lang=None):
        if not lang: lang = LanguageChoices.ENGLISH
        assert key in cls.database
        assert lang in [LanguageChoices.ENGLISH, LanguageChoices.SPANISH]
        return cls.database[key][lang]