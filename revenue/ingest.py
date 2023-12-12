import csv 
import logging
import pytz
import time
import traceback
from datetime import datetime, date, timedelta
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from uuid import uuid4
from django.db import transaction
from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile
from django.db.models import Max 
from Utils.CSVIngest.ingest import CSVIngestor
from Utils.CSVIngest.ingest2 import CSVTrasnformer
from fascard.api import FascardApi
from fascard.fascardbrowser import FascardBrowser
from fascard.config import FascardReportConfig, FascardScrapeConfig
from fascard.utils import TimeHelper
from roommanager.models import LaundryRoom, Slot, LaundryGroup
from .enums import TransactionType, AddValueSubType
from .models import FascardUser,LaundryTransaction,FailedLaundryTransactionIngest, TransactionGaps, TransactionsPool, TxLastIDLog

logger = logging.getLogger(__name__)

class FascardUserIngestor(object):
    
    @classmethod 
    def ingest(cls,laundry_group_id,predownloaded_file_name=None):
        if predownloaded_file_name is None:
            temp_file_name=FascardReportConfig.create_user_report_file_name()
            cls.__download_file(laundry_group_id,temp_file_name)
        else:
            temp_file_name = predownloaded_file_name
        cls.__ingest(temp_file_name,laundry_group_id)
        #TODO: add in file deletion 
     
    @classmethod
    def __download_file(cls,laundry_group_id,file_name):
        br = FascardBrowser()
        br.set_login_ins(laundry_group_id)
        br.download_report("users",file_name)
    
    @classmethod 
    def precheck_function(cls,fascard_user): 
        if FascardUser.objects.filter(fascard_user_account_id=fascard_user.fascard_user_account_id,laundry_group_id=fascard_user.laundry_group_id):
            return False 
        else:
            return True 
    
    @classmethod 
    def __ingest(cls,file_name,laundry_group_id):
        constants = {'laundry_group_id':laundry_group_id}
        ingestor = CSVIngestor(FascardUser,file_name,FascardReportConfig.FASCARD_USER_FIELD_MAP,constants)
        ingestor.ingest(date_format=None, 
                        datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT,precheck_function=cls.precheck_function)
    

class FascardUserAccountSync:
    limit = 1000
    prev = False

    def __init__(self, laundry_group_id):
        self.laundry_group_id = laundry_group_id
        self.laundry_group = LaundryGroup.objects.get(pk=self.laundry_group_id)
        self.api_client = FascardApi(laundry_group_id=self.laundry_group_id)

    def _assign_attributes(self, user_obj, fascard_user_id, fields_map):
        for fascard_field, local_field in fields_map.items():
            if hasattr(user_obj, local_field):
                val = self.hash_map[fascard_user_id][fascard_field]
                if fascard_field == 'LastActivityDate':
                    val = parse(val).replace(tzinfo=None)
                setattr(user_obj, local_field, val)
        setattr(user_obj, 'laundry_group', self.laundry_group)
        return user_obj

    def init_hashmap(self, users_list):
        self.fascard_user_ids = []
        self.hash_map = {}
        for user_data in users_list:
            self.hash_map[user_data['ID']] = user_data
            self.fascard_user_ids.append(user_data['ID'])

    def _sync(self, users_list):
        self.init_hashmap(users_list)
        existing_users_ids = FascardUser.objects.filter(
            fascard_user_account_id__in=self.fascard_user_ids
            ).values_list('fascard_user_account_id', flat=True)

        non_existing_users = list(set(self.fascard_user_ids) - set(existing_users_ids))
        fields_map =  FascardReportConfig.FASCARD_API_USER_FIELD_MAP
        for fascard_user in non_existing_users:
            new_user_object = FascardUser()
            user_obj = self._assign_attributes(new_user_object, fascard_user, fields_map)
            try:
                user_obj.save()
            except Exception as e:
                failure = traceback.format_exc()
                logger.error('Failed to save user: {}. Traceback: {}'.format(e, failure))
                continue

    def _update(self, users_list):
        self.init_hashmap(users_list)
        fields_map = FascardReportConfig.FASCARD_API_USER_FIELD_MAP
        for fascard_user_id in self.fascard_user_ids:
            try:
                user = FascardUser.objects.get(
                    fascard_user_account_id=fascard_user_id,
                    laundry_group = self.laundry_group)
            except FascardUser.DoesNotExist:
                user = FascardUser()
            user_obj = self._assign_attributes(user, fascard_user_id, fields_map)
            try:
                user_obj.save()
            except Exception as e:
                failure = traceback.format_exc()
                logger.error('Failed to save user: {}. Traceback: {}'.format(e, failure))
                continue

    def _update_employees(self):
        employees = []
        for fascard_user in FascardUser.objects.filter(is_employee=True):
            try:
                user_data = self.api_client.get_user_account(fascard_user.fascard_user_account_id)
                employees.append(user_data[0])
            except:
                continue
        self._update(employees)


    def sync_users(self, update=False, start_from_id=None, end_at_id=None):
        #last_id = 1 #Use this if you want to scrape all users all over again. "this is no longer use to avoid not scraping all users in case an ingest is not ran"
        #last_activity_date = datetime.now() - relativedelta(days=1)


        #Then we get the max Last activity date among all the users and convert the string from the dictionary 
        #to a datetime object so that we can later process it in an isoformat as we were doing before.
        last_activity_date =  FascardUser.objects.aggregate(max_date=Max('fascard_last_activity_date'))
        last_activity_date = last_activity_date['max_date']
        #last_activity_date = datetime.strptime(last_activity_date, "%Y-%m-%dT%H:%M:%S.%fZ")

        ingest_start_time = datetime.now()
        if update:
            assert start_from_id
        if start_from_id:
            last_id = start_from_id
        else:
            latest_user = FascardUser.objects.all().order_by('fascard_user_account_id').last()
            last_id = getattr(latest_user, 'fascard_user_account_id', 1)
        while True:
            if end_at_id and int(last_id) > int(end_at_id):
                break
            logger.info('Ingesting. Current Last ID: {}'.format(last_id))
            query_start = datetime.now()
            logger.info(f"Query start: {query_start}")
            users = self.api_client.get_user_account_list(
                self.limit,
                self.prev,
                last_id,
                last_activity_date.isoformat()
            )
            query_end = datetime.now()
            logger.info(f"Query End: {query_end}")
            logger.info(f"Query took: {(query_end - query_start).seconds}")
            if len(users) > 0:
                last_id = users[0]['ID']
                if update:
                    self._update(users)
                else:
                    self._sync(users)
            else:
                break
        ingest_end_time = datetime.now()
        logger.info(f"Ingesting users from API took {(ingest_end_time-ingest_start_time).seconds}")
        try:
            logger.info("Calling _update_employees")
            self._update_employees()
        except Exception as e:
            logger.error("Failed updating employee profiles: {}".format(e), exc_info=True)

    @classmethod
    def run_as_job(self, laundry_group_id):
        try:
            ins = FascardUserAccountSync(laundry_group_id)
            ins.sync_users(update=True, start_from_id=1)
        except Exception as e:
            logger.error('User Scrapper Job failed with error: {}'.format(e), exc_info=True)
            raise Exception(e)


class FascardTransactionSync:
    limit = 1000
    Older = False

    def __init__(self, laundry_group_id):
        self.laundry_group_id =laundry_group_id
        self.laundry_group = LaundryGroup.objects.get(pk=self.laundry_group_id) 
        self.api_client = FascardApi(self.laundry_group_id)
        self.fieldsmap = FascardReportConfig.FASCARDAPI_TRANSACTION_FIELD_MAP
        self.cleaner = FascardTransactionIngestor
        self.date_time_format = FascardScrapeConfig.TIME_INPUT_FORMAT
        self.ALL_IDS = []

    def clean_transaction(self, tx):
        #Simply re-using Tom's logic
        cleaned_tx = {}
        for old_key,value in tx.items():
            if old_key in self.fieldsmap:
                new_key = self.fieldsmap.get(old_key)
                cleaned_tx[new_key] = value

        cleaned_tx['laundry_room_id'] = self.cleaner.post_procesing_get_laundry_room_id(
            cleaned_tx['fascard_code'],
            self.laundry_group_id)
        cleaned_tx['external_fascard_id'] = '%s-%s' % (cleaned_tx['fascard_record_id'], cleaned_tx['sys_config_id'])
        cleaned_tx['slot_id'] = self.cleaner.post_procesing_get_slot_id(cleaned_tx['laundry_room_id'],cleaned_tx['web_display_name'])
        cleaned_tx['machine_id'] = self.cleaner.post_processing_get_machine_id(cleaned_tx['slot_id'])
        cleaned_tx['card_number'] = cleaned_tx['last_four']
        cleaned_tx['last_four'] = self.cleaner.post_processing_get_last_four(cleaned_tx['last_four'])
        
        cleaned_tx['fascard_user_id'] = self.cleaner.post_processing_match_user(
            cleaned_tx['external_fascard_user_id'],
            self.laundry_group_id)
        
        cleaned_tx['utc_transaction_time'] = parse(cleaned_tx['utc_transaction_time']).replace(tzinfo=None)

        packed_values = self.cleaner.post_processing_get_time_zone_conversions(
            FascardReportConfig.REPORT_TIME_ZONE[1],
            FascardReportConfig.CONVERT_TO_TIME_ZONE,
            cleaned_tx['utc_transaction_time'])

        local_transaction_date, local_transaction_time, utc_transaction_time, utc_transaction_date = packed_values
        cleaned_tx['local_transaction_date'] = local_transaction_date
        cleaned_tx['local_transaction_time'] = local_transaction_time
        cleaned_tx['utc_transaction_time'] = utc_transaction_time
        cleaned_tx['utc_transaction_date'] = utc_transaction_date
        if cleaned_tx['transaction_type'] != TransactionType.ADD_VALUE and cleaned_tx['trans_sub_type'] != AddValueSubType.CREDIT_ON_WEBSITE:
            cleaned_tx['assigned_laundry_room_id'] = cleaned_tx['laundry_room_id']
            cleaned_tx['assigned_local_transaction_time'] = cleaned_tx['local_transaction_time'] 
            cleaned_tx['assigned_utc_transaction_time'] = cleaned_tx['utc_transaction_time']
        return cleaned_tx
        #parses string to date-time and makes it timezone-naive

    def fetch_last_id(self):
        pytz_timezone = pytz.timezone('America/New_York')
        now = datetime.now().astimezone(pytz_timezone)
        l = 0
        r = 30
        while True:
            q = LaundryTransaction.objects.all().order_by('-utc_transaction_time')[l:r]
            for tx in q:
                if tx.local_transaction_time <= now.replace(tzinfo=None):
                    last_id = tx.fascard_record_id
                    return last_id
                else:
                    continue
            l += 30
            r += 30

    def save_ids_file(self):
        """
            Save all IDs of transactions being ingested
        """
        string_repr = ','.join(self.ALL_IDS)
        filename = 'TransactionIdsPool - {}'.format(datetime.today())
        try:
            transactions_pool = TransactionsPool.objects.create(number_of_records=len(self.ALL_IDS))
            transactions_pool.transaction_ids.save(filename, ContentFile(bytes(string_repr.encode("utf-8"))))
        except Exception as e:
            logger.error("ALERT: Could not save Transactions Pool file to S3. Error: {}".format(e))

    def _sync(self, transaction_list):
        save_counter = 0
        updates_counter = 0
        create_list = []
        for pos, tx in enumerate(transaction_list):
            try:
                clean_tx = self.clean_transaction(tx)
            except Exception as e:
                raise Exception(e)
                logger.error('Failed cleaning transaction: {} with Exception: '.format(
                    tx, e
                ))
                continue
            if str(clean_tx['transaction_type']) == '50':
                self.merge_transactions.append(clean_tx)
            kwargs={}
            for k,v in clean_tx.items():
                if hasattr(LaundryTransaction, k): kwargs[k] = v
            previous = LaundryTransaction.objects.filter(external_fascard_id=kwargs['external_fascard_id'])
            if previous:
                previous.update(**kwargs)
                updates_counter += 1            
            else:
                try:
                    #LaundryTransaction.objects.create(**kwargs)
                    create_list.append(LaundryTransaction(**kwargs))
                    save_counter += 1
                except Exception as e:
                    logger.error('Failed creating transaction with data: {}. Exception: {}'.format(kwargs, e), exc_info=True)
                    try:
                        external_fascard_id = kwargs['external_fascard_id']
                    except:
                        external_fascard_id = 'Unknown'
                    try:
                        row = str(kwargs)
                    except:
                        row = 'Unknown'
                    error_message = str(e)
                    FailedLaundryTransactionIngest.objects.create(row=row,error_message=error_message,external_fascard_id=external_fascard_id)

            #Add to data structure

            current_tx_date = kwargs['local_transaction_date']
            current_tx_fascard_id = kwargs['external_fascard_id']
            self.ALL_IDS.append(current_tx_fascard_id)
            gap = 0
            if pos:
                gap = abs((current_tx_date - prev_temp_date).days)
            if gap > settings.METRIC_TRAILING_DAYS:
                #print ("Found Gap ({}): {} - {}. At TX with ID: {}".format(gap,current_tx_date, prev_temp_date, current_tx_fascard_id))
                if not current_tx_fascard_id in self.transactions_with_gaps:
                    self.transactions_with_gaps.append(current_tx_fascard_id)

            prev_temp_date = current_tx_date
            #Add Transaction ID to current pool usable for Metrics calculations.
        with transaction.atomic():
            for record in create_list: record.save()
        #try:
        #    LaundryTransaction.objects.bulk_create(create_list)
        #except Exception as e:
        #    logger.error(f"Failed bulk creating transactions: {e}", exc_info=True)
        return (save_counter, updates_counter)

    def process_merge_transactions(self):
        for merge_tx in self.merge_transactions:
            user_transactions = self.api_client.get_transactions_list(
                lastID=merge_tx.get('fascard_record_id'),
                user_account_id=merge_tx.get('external_fascard_user_id'),
                limit=1000,
                Older=True,
            )
            self._sync(user_transactions)

    def save_gaps(self):
        lst = self.transactions_with_gaps
        string_repr = ','.join(lst)

        try:
            TransactionGaps.objects.create(
                transaction_ids = string_repr,
                number_of_records = len(lst)
            )
        except Exception as e:
            logger.error('Failed saving gap transactions ids with error {}'.format(e))

    def sync_transactions(self, start_from_id=None, end_at_id=None):
        if not start_from_id:
            last_id = self.fetch_last_id()
            TxLastIDLog.objects.create(last_id=last_id)
        else:
            last_id = start_from_id
        logger.info(f"Ingesting transactions from id: {last_id}")
        if not last_id:
            err_str = "Could not find a valid last_id. Transaction ingest Needs manual intervention"
            logger.error(err_str)
            raise Exception(err_str)

        total_saves = 0
        total_updates = 0

        self.transactions_with_gaps = []
        self.merge_transactions = []
        while True:
            #logger.info('Ingesting. Current Last ID: {}'.format(last_id))
            if end_at_id and int(last_id) > int(end_at_id):
                break
            logger.info(f'Querying API with last_id: {last_id}')
            transactions = self.api_client.get_transactions_list(
                lastID=last_id,
                limit=self.limit,
                Older=self.Older,
            )
            if len(transactions) > 0:
                last_id = transactions[0]['ID']
                _sync_start = time.time()
                saves, updates = self._sync(transactions)
                _sync_end = time.time()
                logger.info(f'Saves: {saves}. Updates: {updates}. Processing time: {(_sync_end - _sync_start)} seconds')
                total_saves += saves
                total_updates += updates
                TxLastIDLog.objects.create(last_id=last_id)
            else:
                break

        self.save_gaps()
        self.save_ids_file()
        self.process_merge_transactions()
        return True


    @classmethod
    def run_as_job(cls, laundry_group_id, start_from_id=None):
        start = time.time()
        ins = FascardTransactionSync(laundry_group_id)
        #re-ingest transactions starting from the last 2 'last_id' logs i.e (n-2)(n-1)(n)
        last_id_logs = TxLastIDLog.objects.order_by('-timestamp')[:2]
        if not start_from_id and last_id_logs:
            result = ins.sync_transactions(start_from_id=list(last_id_logs)[-1].last_id)
            new_last_id = ins.fetch_last_id()
            TxLastIDLog.objects.create(last_id=new_last_id)
        else:
            result = ins.sync_transactions(start_from_id=start_from_id)
        end = time.time()
        logger.info(f"Ran Tx Sync in : {(end-start)/60.0} minutes")
        return result


    # @classmethod
    # def binarysearch(cls, array, initial, last_index, point):
    #     while initial <= last_index:
    #         midpoint = (initial + last_index) // 2
    #         if array[midpoint] == point:
    #             return True
    #         elif array[midpoint] < point:
    #             initial = midpoint + 1
    #         else:
    #             #array[midpoint] > point
    #             last_index = midpoint - 1
    #     return False

    #def patch as dict and return

    #Sync with binary search
    # def _sync_binary(self, users_list):
    #     print ("Running from binary")
    #     #fascard_user_ids = [user['UserID'] for user in users_list]
    #     fascard_user_ids = []
    #     hash_map = {}
    #     for user in users_list:
    #         hash_map[user['ID']] = user
    #         fascard_user_ids.append(user['ID'])
        
    #     existing_users_ids = FascardUser.objects.filter(
    #         fascard_user_account_id__in=fascard_user_ids
    #         ).values_list('fascard_user_account_id', flat=True)
    #     #current_user_ids = FascardUser.objects.all()# FascardUser.objects.filter(fascard_id__in=fascard_user_ids) get only current userID's
    #     #non_existing = filter(lambda x: x in current_user_ids, fascard_user_ids)
    #     #binary search
    #     non_existing_users = []
    #     length = len(existing_users_ids)
    #     existing = sorted(list(existing_users_ids))
    #     for userid in fascard_user_ids:
    #         found = self.binarysearch(
    #             existing,
    #             0,
    #             length-1,
    #             userid
    #         )
    #         if not found:
    #             non_existing_users.append(userid)
    #     print ("Non existing: {}".format(non_existing_users))
    #     for fascard_user in non_existing_users:
    #         fields_map =  FascardReportConfig.FASCARD_API_USER_FIELD_MAP
    #         for fascard_field, local_field in fields_map.items():
    #             new_user_object = FascardUser
    #             if hasattr(new_user_object, local_field):
    #                 setattr(new_user_object, local_field, hash_map[fascard_user][fascard_field])
    #         print ("Expected to save")
    #             #FascardUser.objects.create(**)


class TransactionDatasetManager():

    def __init__(self, tracker_model, reprocess=False):
        self.tracker_model = tracker_model
        self.dataset = dict()
        self.processed_counter = 0
        self.reprocess = reprocess

    def mark_as_processed(self, processed_date):
        assert hasattr(self, 'temp_pool')
        processed_pool = self.dataset[processed_date]['tx_fascard_ids']
        for processed_id in processed_pool:
            i = self.temp_pool.index(processed_id)
            self.temp_pool[i] = processed_id + 'p'
            self.tracker_model.processed_transactions_counter +=1
        self.tracker_model.save()

    def persist_changes(self):
        #Save self.temp_pool to file
        string_repr = ','.join(self.temp_pool)
        filename = self.tracker_model.transaction_ids.file.name
        try:
            self.tracker_model.transaction_ids.save(
                filename, 
                ContentFile(bytes(string_repr.encode("utf-8")))
            )
            self.tracker_model.save()
        except Exception as e:
            logger.error("ALERT: Could not save Transactions Pool file to S3. Error: {}".format(e))

    def get_data(self):
        if isinstance(self.tracker_model.transaction_ids, FieldFile):
            bytes_obj = self.tracker_model.transaction_ids.read()
            ids_list = bytes_obj.decode('utf-8')
            self.file_buffer = ids_list
        else:
            ids_list = self.tracker_model.transaction_ids

        tx_ids = ids_list.split(',')
        if not self.reprocess:
            self.temp_pool = tx_ids
            to_process = [tx_id for tx_id in tx_ids if not 'p' in tx_id]
        else:
            #process transactions all over again
            #transform ids
            self.temp_pool = [tx_id.replace('p','') for tx_id in tx_ids] 
            to_process = self.temp_pool
        transactions = LaundryTransaction.objects.filter(external_fascard_id__in=to_process)
        for tx in transactions:
            if tx.assigned_local_transaction_time:
                #Assigned Manager
                current_date = tx.assigned_local_transaction_time.date()
            elif tx.local_transaction_time:
                current_date = tx.local_transaction_time.date()

            if current_date not in self.dataset:
                self.dataset[current_date] = {
                    'tx_fascard_ids': list(),
                    'machines': list(), 
                    'rooms': list(), 
                    'billing_groups': list()
                }
            self.dataset[current_date]['tx_fascard_ids'].append(tx.external_fascard_id)

            room = None
            if tx.assigned_laundry_room:
                room = tx.assigned_laundry_room
            elif tx.laundry_room:
                room = tx.laundry_room
            if room:
                room_id = room.id
                if room_id not in self.dataset[current_date]['rooms']:
                    self.dataset[current_date]['rooms'].append(room_id)

                ext = room.laundryroomextension_set.first()
                if ext:
                    if getattr(ext, 'billing_group', None) is not None:
                        bg_id = ext.billing_group.id
                        if bg_id not in self.dataset[current_date]['billing_groups']:
                            self.dataset[current_date]['billing_groups'].append(bg_id)

                if tx.machine_id:
                    machine_id = tx.machine_id
                    if machine_id not in self.dataset[current_date]['machines']:
                        self.dataset[current_date]['machines'].append(machine_id)
        #print ("Dict MAP: {}".format(self.dataset))
        return self.dataset



class FascardTransactionIngestor(object):  
    
    @classmethod 
    def ingest(cls,laundry_group_id,start_date,final_date,file_time_zone=FascardReportConfig.REPORT_TIME_ZONE,local_time_zone=FascardReportConfig.CONVERT_TO_TIME_ZONE,
               predownloaded_file_name=None):
        if predownloaded_file_name is None:
            temp_file_name=FascardReportConfig.create_transaction_report_file_name()
            cls.__download_file(laundry_group_id,start_date,final_date,temp_file_name)
        else:
            temp_file_name = predownloaded_file_name        
        transformer = CSVTrasnformer(LaundryTransaction,temp_file_name,FascardReportConfig.FASCARD_TRANSACTION_FIELD_MAP)
        for tx in transformer.unsaved_orm_objects(date_format=None,datetime_format=FascardScrapeConfig.TIME_INPUT_FORMAT):
            try:
                tx['laundry_room_id'] = cls.post_procesing_get_laundry_room_id(tx['fascard_code'],laundry_group_id)
                tx['external_fascard_id'] = '%s-%s' % (tx['fascard_record_id'], tx['sys_config_id'])
                tx['slot_id'] = cls.post_procesing_get_slot_id(tx['laundry_room_id'],tx['web_display_name'])
                tx['machine_id'] = cls.post_processing_get_machine_id(tx['slot_id'])
                tx['card_number'] = tx['last_four']
                tx['last_four'] = cls.post_processing_get_last_four(tx['last_four'])
                tx['fascard_user_id'] = cls.post_processing_match_user(tx['external_fascard_user_id'],laundry_group_id)
                local_transaction_date, local_transaction_time, utc_transaction_time, utc_transaction_date = cls.post_processing_get_time_zone_conversions(FascardReportConfig.REPORT_TIME_ZONE[1],
                                                                                                                        FascardReportConfig.CONVERT_TO_TIME_ZONE,
                                                                                                                        tx['utc_transaction_time'])
                tx['local_transaction_date'] = local_transaction_date
                tx['local_transaction_time'] = local_transaction_time
                tx['utc_transaction_time'] = utc_transaction_time
                tx['utc_transaction_date'] = utc_transaction_date
                
                previous = LaundryTransaction.objects.filter(external_fascard_id=tx['external_fascard_id'])
                #TODO: prevent machine overrite 
                if previous:
                    previous.update(**tx)
                else:
                    LaundryTransaction.objects.create(**tx)
            except Exception as e:
                try:
                    external_fascard_id = tx['external_fascard_id']
                except:
                    external_fascard_id = 'Unknown'
                try:
                    row = str(tx)
                except:
                    row = 'Unknown'
                error_message = str(e)
                FailedLaundryTransactionIngest.objects.create(row=row,error_message=error_message,external_fascard_id=external_fascard_id)


    @classmethod 
    def __download_file(cls,laundry_group_id,start_date,final_date,temp_file_name):
        br = FascardBrowser()
        br.set_login_ins(laundry_group_id)
        br.download_report("laundry transaction",temp_file_name,start_date,final_date)

    @classmethod 
    def post_procesing_get_laundry_room_id(cls,fascard_code,laundry_group_id):
        try:
            laundry_room_id = LaundryRoom.objects.filter(fascard_code=fascard_code,laundry_group_id=laundry_group_id).first().id
        except:
            laundry_room_id = None 
        return laundry_room_id
            
    
    @classmethod 
    def post_procesing_get_slot_id(cls,laundry_room_id,web_display_name):
        #NB: We use last run time to break ties when the same laundry room has multiple slots with the same web display name.  
        #This happens when a slot is taken offline and a new one created with the same web display name.
        slot = Slot.objects.filter(laundry_room_id=laundry_room_id,web_display_name=web_display_name).order_by('-last_run_time').first()
        if slot:
            return slot.id
        else:
            return None
            
    @classmethod 
    def post_processing_get_machine_id(cls,slot_id):
        try:
            machine_id = Slot.get_current_machine(slot_id).id
        except:
            machine_id = None 
        return machine_id 

    @classmethod 
    def post_processing_get_last_four(cls,last_four):
        try:
            return last_four[-4:]
        except:
            return None
        
    @classmethod 
    def post_processing_get_time_zone_conversions(cls,from_tz,to_tz,utc_transaction_time):
        ingest_time = pytz.timezone(from_tz).localize(utc_transaction_time)
        
        local_time_zone = pytz.timezone(to_tz)
        utc_time_zone = pytz.timezone('UTC')
        
        local_time = ingest_time.astimezone(local_time_zone)
        utc_time = ingest_time.astimezone(utc_time_zone)
        
        local_transaction_time = datetime(local_time.year,local_time.month,local_time.day,local_time.hour,local_time.minute,local_time.second)
        local_transaction_date = local_transaction_time.date()
        utc_transaction_time = datetime(utc_time.year,utc_time.month,utc_time.day,utc_time.hour,utc_time.minute,utc_time.second)
        utc_transaction_date = utc_transaction_time.date()
        
        return local_transaction_date, local_transaction_time, utc_transaction_time, utc_transaction_date 
    
    @classmethod 
    def post_processing_match_user(cls,external_fascard_user_id,laundry_group_id):
        fascard_user = FascardUser.objects.filter(laundry_group_id=laundry_group_id, fascard_user_account_id = external_fascard_user_id).first()
        if fascard_user:
            return fascard_user.id 
        else:
            return None 