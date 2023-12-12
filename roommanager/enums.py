
class SlotType():
    STANDARD = 'STANDARD'
    DOUBLE = 'DOUBLE'
    
    CHOICES = ((STANDARD,STANDARD),(DOUBLE,DOUBLE))
    
# class MachineStateType():
#     UNKNOWN = -5
#     DIAGNOSTIC = -4
#     DISABLED = -3
#     ERROR = -2
#     OFFLINE = -1
#     IDLE = 0
#     RUNNING = 1
#     CHOICES = ((DIAGNOSTIC,DIAGNOSTIC),(DISABLED,DISABLED),(OFFLINE,OFFLINE),(IDLE,IDLE),(RUNNING,RUNNING),(ERROR,ERROR),
#                       (UNKNOWN,UNKNOWN))
    
class MachineType():
    UNKNOWN = -1 
    WASHER = 0
    DRYER = 1
    COMBO_STACK = 3
    CHOICES = ((UNKNOWN,'UNKNOWN'),(WASHER,'WASHER'),(DRYER,'DRYER'),(COMBO_STACK,'COMBO_STACK'))

class VerboseMachineType():
    UNKNOWN = 'Unknown'
    WASHER = 'Washer'
    DRYER = 'Dryer'
    COMBO_STACK = 'ComboStack'
    CHOICES = ((UNKNOWN,'UNKNOWN'),(WASHER,'WASHER'),(DRYER,'DRYER'))
    map_to_machinetype = {
        MachineType.UNKNOWN : UNKNOWN,
        MachineType.WASHER : WASHER,
        MachineType.DRYER : DRYER,
        MachineType.COMBO_STACK : COMBO_STACK,
    }


class TimeZoneType():
    EASTERN = 'US/Eastern'
    WESTERN = 'US/Western'
    CHOICES = ((EASTERN,EASTERN),(WESTERN,WESTERN))
    

class HardwareType():
    SLOT = 'SLOT'
    MACHINE = 'MACHINE'
    CARD_READER = 'CARD_READER'
    CHOICES = ((SLOT,SLOT), (MACHINE,MACHINE), (CARD_READER,CARD_READER))
    

class ChangeType():
    SLOT_CHANGE = 'SLOT_CHANGE'
    MACHINE_CHANGE = 'MACHINE_CHANGE'
    CARD_READER_CHANGE = 'CARD_READER_CHANGE'
    WAREHOUSE = 'WAREHOUSE'
    NEW_BUNDLE = 'NEW'
    CHOICES = (
        (SLOT_CHANGE,SLOT_CHANGE),
        (MACHINE_CHANGE,MACHINE_CHANGE),
        (CARD_READER_CHANGE,CARD_READER_CHANGE),
        (NEW_BUNDLE,NEW_BUNDLE)
    )


class BundleType():
    STACK_DRYER = 'STACKDRYER'
    STACK_DRYER_DUAL_POCKET = 'STACKDRYER_DUALPOCKET'
    SINGLE = 'SINGLE'
    WAREHOUSE = 'WAREHOUSE'
    STACKED_WAREHOUSE = 'STACKED_WAREHOUSE'
    SWAP_SERVICE = 'SWAP_SERVICE'
    CHOICES = (
        (STACK_DRYER, STACK_DRYER),
        (STACK_DRYER_DUAL_POCKET, STACK_DRYER_DUAL_POCKET),
        (SINGLE, SINGLE),
        (WAREHOUSE, WAREHOUSE)
    )


class AssetPicturesChoice():
    ACCEPT_AND_REPLACE = 'ACCEPT_AND_REPLACE'
    SAVE_DONT_REPLACE = 'SAVE_DONT_REPLACE'
    REJECT = 'REJECT'
    NON_APPLICABLE = 'NA'
    ACCEPT_AND_REPLACE_ = (ACCEPT_AND_REPLACE, 'Accept and Replace Current')
    SAVE_DONT_REPLACE_ = (SAVE_DONT_REPLACE, 'Save Picture But Do Not Replace Current')
    REJECT_ = (REJECT, 'Reject')
    NA_ = (NON_APPLICABLE, 'NA')

    CHOICES = (
        ACCEPT_AND_REPLACE_,
        SAVE_DONT_REPLACE_,
        REJECT_,
        NA_
    )

    
ORPHANE_MESSAGES = {
    HardwareType.SLOT : 'The Slot {} needs to be re scanned',
    HardwareType.MACHINE : 'The Machine with asset code {} needs to be re scanned. Last location known: {}',
    HardwareType.CARD_READER : 'The Card Reader with card-reader-code {} needs to be re scanned. Last location known: {}'
}


MissingAssetFieldNotifications = {
    'asset_picture' : 'picture_missing',
    'asset_serial_picture' : 'serial_picture_missing',
    'asset_serial_number' : 'serial_number_missing',
    'asset_factory_model' : 'factory_model_missing'
}


class CardReaderStatus():
    AVAILABLE = 'available'
    BUNDLED = 'bundled'
    CHOICES = ((AVAILABLE,AVAILABLE), (BUNDLED,BUNDLED))


class CardReaderCondition():
    REFURBISHED = 'refurbished'
    NEW = 'new'
    UNKNOWN = 'unknown'
    CHOICES = ((NEW,NEW), (REFURBISHED,REFURBISHED), (UNKNOWN,UNKNOWN))


class OrphanedPieceAnswerChoices:
    WAREHOUSE = ('warehouse', 'Warehouse')
    OFFICE = ('office', 'Office')
    BROOKLYN_OFFICE = ('brooklyn', 'Brooklyn Office')
    OTHER_ROOM = ('other-room', 'Another Laundry Room')
    OTHER_SLOT_SAME_ROOM = ('other-slot-same-room', 'Another Slot in the same Room')
    DISPOSED = ('disposed', 'Being Disposed')
    SOLD = ('sold', 'Sold')
    MANUFACTURER = ('manufacturer', 'Returning to Manufactureer')
    ABANDONED = ('abandoned', 'Abandoned on Site')
    REBUNDLE = ('rebundled', 'Will get rebundled with same CardReader/Machine')
    NEW_HARDWARE_BUNDLE = ('new-hardware-bundle', 'Get Bundled with new Hardware')
    DELETED = ('deleted', 'Will get Deleted')

    CHOICES = (
        WAREHOUSE,
        OFFICE,
        BROOKLYN_OFFICE,
        OTHER_ROOM,
        OTHER_SLOT_SAME_ROOM,
        DISPOSED,
        SOLD,
        MANUFACTURER,
        ABANDONED,
        REBUNDLE,
        NEW_HARDWARE_BUNDLE,
        DELETED
    )

    SLOT_CHOICES = (
        REBUNDLE,
        NEW_HARDWARE_BUNDLE,
        DELETED
    )

    MACHINE_CARDREADER_CHOICES = (
        WAREHOUSE,
        OFFICE,
        BROOKLYN_OFFICE,
        OTHER_ROOM,
        OTHER_SLOT_SAME_ROOM,
        DISPOSED,
        SOLD,
        MANUFACTURER,
        ABANDONED,
    )


class LanguageChoices:
    SPANISH = 'Spanish'
    ENGLISH = 'English'

    CHOICES = (
        (SPANISH, SPANISH),
        (ENGLISH, ENGLISH)
    )


class AssetMapOutChoices:
    DISPOSED = 'disposed'
    EN_ROUTE = 'en-route-to-wareouse'
    PICKUP = 'mark-for-pickup'

    CHOICES = (
        (DISPOSED, DISPOSED),
        (EN_ROUTE, EN_ROUTE),
        (PICKUP, PICKUP)
    )

# class SlotErrorType():
#     UNKNOWN = -5
#     DIAGNOSTIC = -4
#     DISABLED = -3
#     ERROR = -2
#     OFFLINE = -1
#     LONG_IDLE = -6
#     LONG_RUNNING = -7 
#     SHORT_RUNNING = -8 
#     FLICKERING = -9
#     LONG_TRANSACTION_GAP = -10
#     CHOICES = ((UNKNOWN,'UNKNOWN'),(DIAGNOSTIC,'DIAGNOSTIC'),(DISABLED,'DISABLED'),
#                (ERROR,'ERROR'),(OFFLINE,'OFFLINE'),(LONG_IDLE,'LONG_IDLE'),(LONG_RUNNING,'LONG_RUNNING'),(SHORT_RUNNING,'SHORT_RUNNING'),
#                (FLICKERING,'FLICKERING'),(LONG_TRANSACTION_GAP,LONG_TRANSACTION_GAP))
#     FASCAR_ERRORS = [UNKNOWN,DIAGNOSTIC,DISABLED,ERROR,OFFLINE]
    
# class TransactionScrapeStateType():
#     STARTED = 0
#     SCRAPED = 1
#     INGESTED = 2
#     RUNTIME = 3
#     ERROR = 4
#     RESETTING = 5
#     CHOICES = ((STARTED,STARTED),(INGESTED,INGESTED),(SCRAPED,SCRAPED),(RUNTIME,RUNTIME),(ERROR,ERROR),(RESETTING,RESETTING))
    
# class LocationLevel():
#     ROOM = 1
#     GROUP = 2
#     MACHINE = 3
#     BILLING_GROUP  = 4
#     PERSON = 5
#     CHOICES = ((ROOM,'Room'),(GROUP,'Group'),(MACHINE,'Machine'), (PERSON,'Person'),
#                (BILLING_GROUP,'Billing Group- Not Implemented For Revenue Report'))

# class TimeLevel():
#     DAY = 1 
#     MONTH = 2
#     SINGLE_PERIOD = 3
#     QUARTER = 4
#     CHOICES = ((DAY,'Day'),(MONTH,'Month'),(QUARTER,'Quarter'),
#                (SINGLE_PERIOD,'Single Period- Not Valid For Revenue Report'))  
       
# class RevenueRule():
#     EARNED = 'EARNED'
#     FUNDS = 'FUNDS'
#     CHOICES = ((EARNED,EARNED),(FUNDS,FUNDS))
    
# class CaclulatedRevenueMetricType():
#     STATIC = 'STATIC'
#     DIVIDE_BY_REVENUE = 'DIVIDE_BY_REVENUE'
#     BOOLEAN = 'BOOLEAN'



# class PersonAliasSource():   
# 
#     LAUNDRY_TRANSACTION = 'LAUNDRY_TRANSACTION'
#     OTHER = 'OTHER'
# 
#     CHOICES = ((LAUNDRY_TRANSACTION,LAUNDRY_TRANSACTION),(OTHER,OTHER))
    
    
    