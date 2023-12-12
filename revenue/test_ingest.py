'''
Created on Mar 5, 2017

@author: Thomas
'''
import os
from datetime import datetime,date
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from fascard.api import FascardApi
from fascard.config import FascardScrapeConfig
from main import settings

from roommanager.models import LaundryGroup,LaundryRoom,LaundryRoomMeter,Slot,Machine,MachineSlotMap, \
                                EquipmentType, Slot
from roommanager.enums import MachineType, SlotType

from Utils.CSVIngest.ingest import CSVIngestor
#from testhelpers.recipes import BasicRecipeMixin
from .ingest import FascardUserIngestor, FascardTransactionIngestor, FascardUserAccountSync, FascardTransactionSync, \
                    FascardUserAccountSync
from .models import FascardUser
from .matcher import CheckAttributionMatcher, MatchFilters, WebBasedMatcherAdaptor, StandardMatcher as StandardRevenueMatcher
from revenue.models import LaundryTransaction, FailedLaundryTransactionIngest, TransactionsPool

class TestFascardUserIngest(TestCase):

    def setUp(self):
        self.test_folder = os.path.join(settings.TEST_FILE_FOLDER,'test_revenue_ingest')
        CSVIngestor(LaundryGroup,file_name = os.path.join(self.test_folder,'laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)

    def test_ingest_one_group(self):
        FascardUserIngestor.ingest(laundry_group_id=1, predownloaded_file_name=os.path.join(self.test_folder,'fascard_user_group1.csv'))
        fascard_users=FascardUser.objects.all()
        self.assertEqual(fascard_users.count(),1375)
        self.assertEqual(fascard_users.exclude(laundry_group_id=1).count(),0)
        self.assertEqual(fascard_users.filter(is_employee=True).count(),28)

    def test_ingest_both_groups(self):
        #Ingest laundry users for 2 different laundry groups
        FascardUserIngestor.ingest(laundry_group_id=1, predownloaded_file_name=os.path.join(self.test_folder,'fascard_user_group1.csv'))
        FascardUserIngestor.ingest(laundry_group_id=2, predownloaded_file_name=os.path.join(self.test_folder,'fascard_user_group2.csv'))

        self.assertEqual(FascardUser.objects.filter(laundry_group_id=1).count(),1375)
        self.assertEqual(FascardUser.objects.filter(laundry_group_id=2).count(),12)

    def test_ingest_from_fascard(self):
        FascardUserIngestor.ingest(laundry_group_id=1)
        self.assertGreaterEqual(FascardUser.objects.filter(laundry_group_id=1).count(),1375)
        self.assertEqual(FascardUser.objects.exclude(laundry_group_id=1).count(),0)
        self.assertGreaterEqual(FascardUser.objects.filter(is_employee=True).count(),28)


class TestFascardUserAPIIngest(TestCase):

    @classmethod
    def setUpTestData(cls):
        laundry_group = LaundryGroup.objects.create(
            display_name = 'Aces Laundry'
        )
        cls.laundry_group_id = laundry_group.id
        cls.syncer = FascardUserAccountSync(laundry_group.id)

    def setUp(self):
        self.start_from_id = 1
        self.end_at_id = 1000

    def test_ingest(self):
        #Ingest of test user
        self.syncer.sync_users(
            start_from_id = self.start_from_id,
            end_at_id = self.end_at_id
        )
        #FascardUser.objects.filter(email_address='daniel@aptsny.com').first()
        self.assertEqual(FascardUser.objects.filter(email_address='daniel@aptsny.com').exists(), True)
        print (FascardUser.objects.all().count())

    def test_update(self):
        test_user = FascardUser.objects.create(
            fascard_user_account_id = 3,
            email_address = 'daniel@aptsny.com',
            laundry_group_id = self.laundry_group_id
        )
        self.syncer.sync_users(
            update=True,
            start_from_id=self.start_from_id,
            end_at_id=self.end_at_id
        )
        test_user.refresh_from_db()
        self.assertEqual(test_user.name, 'Daniel Scharfman')


class TestFascardTransactionIngest(TestCase):

    def setUp(self):
        self.test_folder = os.path.join(settings.TEST_FILE_FOLDER,'test_revenue_ingest')

        CSVIngestor(LaundryGroup,file_name = os.path.join(self.test_folder,'laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(self.test_folder,'laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(Slot,file_name = os.path.join(self.test_folder,'slots_arden_and_autobond.csv')).ingest(date_format=None,
                datetime_format='%m/%d/%Y %H:%M:%S %p')
        #create machines and maps
        for slot in Slot.objects.all():
            try:
                web_display_name = int(slot.web_display_name)
            except ValueError as e:
                continue
            if web_display_name<100:
                machine_type =  MachineType.WASHER
            elif web_display_name<200:
                machine_type = MachineType.DRYER
            else:
                continue
            machine_new = Machine.objects.create(machine_type=machine_type,machine_text='New Machine')
            machine_old = Machine.objects.create(machine_type=machine_type,machine_text='Old Machine')
            MachineSlotMap.objects.create(machine=machine_old,slot=slot,start_time=datetime(2015,1,1,0,0,0),end_time=datetime(2016,1,1,0,0,0))
            MachineSlotMap.objects.create(machine=machine_new,slot=slot,start_time=datetime(2016,1,1,0,0,0),end_time=None)

        FascardUserIngestor.ingest(laundry_group_id=1, predownloaded_file_name=os.path.join(self.test_folder,'fascard_user.csv'))


    def test_basic(self):
        FascardTransactionIngestor.ingest(1, start_date=date(2017,2,1), final_date=date(2017,2,1),
                                          file_time_zone=("Coordinated Universal Time",'UTC'), local_time_zone='America/New_York',
                                          predownloaded_file_name=os.path.join(self.test_folder,'laundry_transaction_20170201_20170202_arden_and_autobon.csv'))
        arden_street_room = LaundryRoom.objects.get(display_name='1 Arden ST')
        test_slot = Slot.objects.get(laundry_room=arden_street_room,web_display_name=2)
        self.assertEqual(LaundryTransaction.objects.all().count(),202)
        self.assertEqual(LaundryTransaction.objects.filter(laundry_room=arden_street_room).count(),118)
        self.assertEqual(LaundryTransaction.objects.filter(slot=test_slot).count(),6)
        #No mismatches of slot
        self.assertEqual(LaundryTransaction.objects.filter(slot=test_slot, fascard_record_id__in=('4807557','4807919','4809906','4811267','4812261','4812584')).count(),6)
        #machine is mapped correctly
        for tx in LaundryTransaction.objects.filter(slot=test_slot):
            self.assertEqual(tx.machine.machine_text,'New Machine')
            self.assertEqual(tx.machine.machine_type,MachineType.WASHER)

        test_tx = LaundryTransaction.objects.get(fascard_record_id='4807900')
        self.assertEqual(test_tx.laundry_room,arden_street_room)
        self.assertEqual(test_tx.slot.laundry_room,arden_street_room)
        self.assertEqual(test_tx.slot.web_display_name,'1')
        self.assertEqual(test_tx.machine.machine_type,MachineType.WASHER)
        self.assertEqual(test_tx.machine.machine_text,'New Machine')
        self.assertEqual(test_tx.web_display_name,'1')
        self.assertEqual(test_tx.transaction_type,'100')
        self.assertEqual(test_tx.last_four,'2799')
        self.assertEqual(test_tx.card_number,'xxx2799')
        self.assertAlmostEqual(test_tx.credit_card_amount,1.50,2)
        self.assertAlmostEqual(test_tx.cash_amount,0,2)
        self.assertAlmostEqual(test_tx.balance_amount,0,2)
        #TODO: get this working
        #self.assertEqual(test_tx.last_four,0,'2799')
        self.assertEqual(test_tx.utc_transaction_time,datetime(2017,2,1,16,55))
        self.assertEqual(test_tx.utc_transaction_date,date(2017,2,1))

        self.assertEqual(test_tx.local_transaction_time,datetime(2017,2,1,11,55))

        self.assertEqual(LaundryTransaction.objects.get(fascard_record_id='4807900').authorizedotnet_id,
                         '1879')

        self.assertEqual(LaundryTransaction.objects.get(fascard_record_id='4823119').loyalty_card_number,
                         '12121212')
        self.assertEqual(FailedLaundryTransactionIngest.objects.count(),0)


    def test_rescrape(self):
        FascardTransactionIngestor.ingest(1, start_date=date(2017,2,1), final_date=date(2017,2,1),
                                          file_time_zone=("Coordinated Universal Time",'UTC'), local_time_zone='America/New_York',
                                          predownloaded_file_name=os.path.join(self.test_folder,'laundry_transaction_20170201_20170202_arden_and_autobon.csv'))
        num_tx = LaundryTransaction.objects.count()
        FascardTransactionIngestor.ingest(1, start_date=date(2017,2,1), final_date=date(2017,2,1),
                                          file_time_zone=("Coordinated Universal Time",'UTC'), local_time_zone='America/New_York',
                                          predownloaded_file_name=os.path.join(self.test_folder,'laundry_transaction_20170201_20170202_arden_and_autobon.csv'))
        num_tx_2 = LaundryTransaction.objects.count()
        self.assertEqual(num_tx,num_tx_2)
        self.assertEqual(FailedLaundryTransactionIngest.objects.count(),0)


    def test_duplicate_slot(self):
        '''We have an issue where web display names can be duplicated within a laundry room.  This can't cause the ingest to fail.  We fix it by looking at last run time.
        NB: machine slot map is not a viable option since each slot will have an active map.'''
        #Create a duplicate slot
        arden_street_room = LaundryRoom.objects.get(display_name='1 Arden ST')
        old_slot = Slot.objects.get(laundry_room=arden_street_room,web_display_name=2)
        old_slot.last_run_time = datetime(2017,1,1)
        old_slot.save()
        old_map = MachineSlotMap.objects.get(slot = old_slot, is_active = True)
        new_slot = Slot.objects.create(laundry_room = old_slot.laundry_room, web_display_name = old_slot.web_display_name,
                                             slot_fascard_id = 9999, slot_type = old_slot.slot_type, last_run_time = datetime(2018,1,1))
        new_map = MachineSlotMap.objects.create(slot = new_slot, machine = old_map.machine, start_time = old_map.start_time)
        #Ingest data
        FascardTransactionIngestor.ingest(1, start_date=date(2017,2,1), final_date=date(2017,2,1),
                                          file_time_zone=("Coordinated Universal Time",'UTC'), local_time_zone='America/New_York',
                                          predownloaded_file_name=os.path.join(self.test_folder,'laundry_transaction_20170201_20170202_arden_and_autobon.csv'))
        #Make sure that the transactions are all matched to the correct slot, aka the one with the latest runtime timestamp
        arden_street_room = LaundryRoom.objects.get(display_name='1 Arden ST')
        self.assertEqual(LaundryTransaction.objects.filter(slot=old_slot).count(), 0)
        self.assertEqual(LaundryTransaction.objects.filter(slot=new_slot).count(), 6)


class TestFailedIngest(TransactionTestCase):


    def test_failed_ingest(self):
        self.test_folder = os.path.join(settings.TEST_FILE_FOLDER,'test_revenue_ingest')
        CSVIngestor(LaundryGroup,file_name = os.path.join(self.test_folder,'laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(self.test_folder,'laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)

        FascardTransactionIngestor.ingest(1, start_date=date(2017,2,1), final_date=date(2017,2,1),
                                          file_time_zone=("Coordinated Universal Time",'UTC'), local_time_zone='America/New_York',
                                          predownloaded_file_name=os.path.join(self.test_folder,'laundry_transaction_null_time.csv'))
        self.assertEqual(LaundryTransaction.objects.count(),0)

        self.assertGreater(FailedLaundryTransactionIngest.objects.count(),100,"Too few errors recorded.")
        self.assertEqual(FailedLaundryTransactionIngest.objects.filter(external_fascard_id=None).count(),0,"All errors should have a external fascard id recorded.")
        self.assertEqual(FailedLaundryTransactionIngest.objects.filter(error_message=None).count(),0,"All errors should have an error message recorded.")


class TestExternalIdCreation(TransactionTestCase):

    #Fascard's RecID field isn't unique across our two accounts.  But it is when combined with sysID
    #Ensure this is handeled correctly.  external id = RecID + '-' + sysId.
    def test_standered(self):
        self.test_folder = os.path.join(settings.TEST_FILE_FOLDER,'test_revenue_ingest')
        CSVIngestor(LaundryGroup,file_name = os.path.join(self.test_folder,'laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(self.test_folder,'laundry_room.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        FascardTransactionIngestor.ingest(1, start_date=date(2017,2,1), final_date=date(2017,2,1),
                                          file_time_zone=("Coordinated Universal Time",'UTC'), local_time_zone='America/New_York',
                                          predownloaded_file_name=os.path.join(self.test_folder,'tx_external_ids_1.csv'))
        FascardTransactionIngestor.ingest(2, start_date=date(2017,2,1), final_date=date(2017,2,1),
                                          file_time_zone=("Coordinated Universal Time",'UTC'), local_time_zone='America/New_York',
                                          predownloaded_file_name=os.path.join(self.test_folder,'tx_external_ids_2.csv'))

        self.assertEqual(LaundryTransaction.objects.count(),4)
        tx1 = LaundryTransaction.objects.get(external_fascard_id='1000001-86')
        self.assertEqual(tx1.laundry_room_id, 1)
        self.assertEqual(tx1.fascard_record_id, '1000001')
        self.assertEqual(tx1.sys_config_id, '86')
        self.assertEqual(tx1.laundry_room_id, 1)

        tx2 = LaundryTransaction.objects.get(external_fascard_id='1000001-212')
        self.assertEqual(tx2.laundry_room_id, 62)
        self.assertEqual(tx2.fascard_record_id, '1000001')
        self.assertEqual(tx2.sys_config_id, '212')
        self.assertEqual(tx2.laundry_room_id, 62)


class TestFascardTransactionIngestBig(TestCase):
    #Used to test larger set of data to make sure there are no failures

    def test_standard(self):
        self.test_folder = os.path.join(settings.TEST_FILE_FOLDER,'test_revenue_ingest')

        CSVIngestor(LaundryGroup,file_name = os.path.join(self.test_folder,'laundry_group.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(LaundryRoom,file_name = os.path.join(self.test_folder,'laundry_room_big.csv')).ingest(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT)
        CSVIngestor(Slot,file_name = os.path.join(self.test_folder,'slot_big.csv')).ingest(date_format=None,
                datetime_format='%m/%d/%Y %H:%M:%S %p')
        #create machines and maps
        for slot in Slot.objects.all():
            try:
                web_display_name = int(slot.web_display_name)
            except ValueError as e:
                continue
            if web_display_name<100:
                machine_type =  MachineType.WASHER
            elif web_display_name<200:
                machine_type = MachineType.DRYER
            else:
                continue
            machine_new = Machine.objects.create(machine_type=machine_type,machine_text='New Machine')
            machine_old = Machine.objects.create(machine_type=machine_type,machine_text='Old Machine')
            MachineSlotMap.objects.create(machine=machine_old,slot=slot,start_time=datetime(2015,1,1,0,0,0),end_time=datetime(2016,1,1,0,0,0))
            MachineSlotMap.objects.create(machine=machine_new,slot=slot,start_time=datetime(2016,1,1,0,0,0),end_time=None)

        #NB: We removed all users from ingest table for ease of testing.
        #NB: start and end date are only relavent for file downloading, but we use a predownloaded file here.
        FascardTransactionIngestor.ingest(1, start_date=date(2017,5,1), final_date=date(2017,5,20),
                                   file_time_zone=("Coordinated Universal Time",'UTC'), local_time_zone='America/New_York',
                                   predownloaded_file_name=os.path.join(self.test_folder,'laundry_transaction_big.csv'))
        self.assertGreater(LaundryTransaction.objects.count(),1000)
        self.assertEqual(FailedLaundryTransactionIngest.objects.count(),0)



class TestAPITransactionIngestor(TestCase):
    """
    Using all transactions that happened in December 2019 at 1 Arden Street
    """

    fixtures = ['laundrygroups.json', 'laundryrooms.json', 'slots.json', 'users.json']

    def test_ingest(self):
        initial_count = LaundryTransaction.objects.filter(
            local_transaction_date__gte=date(2019,11,1),
            local_transaction_date__lte=date(2019,11,30)
        ).count()
        self.assertEqual(initial_count, 0)
        #Sync Transactions between Nov 01 and Nov 30 of 2019
        start_from_id = 12571000
        end_at_id = 12834700
        ins = FascardTransactionSync(1)
        ins.sync_transactions(start_from_id, end_at_id)
        #Match transactions
        StandardRevenueMatcher.match_all()
        CheckAttributionMatcher.match()
 
        for tx in LaundryTransaction.objects.all():
            WebBasedMatcherAdaptor.process(tx.id)

        count = LaundryTransaction.objects.filter(
            local_transaction_date__gte=date(2019,11,1),
            local_transaction_date__lte=date(2019,11,30)
        ).count()

        self.assertEqual(count, 150940)

        #GET THE FILE
        tx_pool = TransactionsPool.objects.last()
        

class TestMeterUpdate(TestCase):

    def setUp(self):
        self.laundry_group = LaundryGroup.objects.create(
            display_name = 'Group',
            notes = 'None'
        )
        self.laundry_room = LaundryRoom.objects.create(
            display_name = 'Test Location',
            fascard_code = 1,
            laundry_group = self.laundry_group
        )
        self.slot = Slot.objects.create(
            laundry_room = self.laundry_room,
            web_display_name = '1'
        )
        self.equipment_type = EquipmentType.objects.create(
            fascard_id = 1,
            laundry_group = self.laundry_group,
            machine_text = 'Wascomat',
            machine_type = 1, #dryer
            equipment_start_check_method = 'STANDARD',
        )
        self.machine = Machine.objects.create(
            equipment_type=self.equipment_type,
			machine_type = 1
        )
        self.room_meter = LaundryRoomMeter.objects.create(
            laundry_room = self.laundry_room,

        )

    def test_meter_update(self):
        meter = getattr(self.machine, 'meter', None)
        self.assertNotEqual(meter, None)
        meter.transactions_counter =  100
        meter.save()
        meter.refresh_from_db()
        LaundryTransaction.objects.create(
            slot=self.slot,
            machine=self.machine,
            external_fascard_id = 1,
            fascard_record_id = 1,
            laundry_room = self.laundry_room,
            local_transaction_date = date.today(),
            credit_card_amount = Decimal('10.0'),
            transaction_type='100'
        )
        self.assertEqual(meter.transactions_counter, 101)
        self.room_meter.refresh_from_db()
        self.assertEqual(self.room_meter.dryers_start_counter, 1)
