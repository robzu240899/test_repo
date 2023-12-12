SLOT_STATE_ERROR_HEADERS = [
            'building name',
            'display name',
            'start time',
            'end time',
            'error(s)',
            'mlvmacherror_description',
            'slot_status_text',
            'maintainx_asset_url',
            'fascard_url',
            'fascard_id',
            'internal_id',
]


FLICKERING_ERRORS = [
    'building_name',
    'display_name',
    'start_time',
    'end_time', 
    'maintainx_asset_url'
]

TIME_RANGE_HEADERS = [
    'building name',
    'display name',
    'start time',
    'end time',
    'duration',
    'error(s)',
    'mlvmacherror_description',
    'slot_status_text',
    'maintainx_asset_url',
    'fascard_url',
    'fascard_id',
    'internal_id',
]

METER_RAISES_HEADERS = [
    'billing_group',
    'date',
    'raise_limit (i.e description)',
    'admin_url'
]

UPKEEP_SYNCING_HEADERS = [
    'location',
    'name',
    'asset_code',
    'scans',
    'upkeep_url',
    'maintainx_url'
]

UNBUNBLED_SLOTS_HEADERS = [
    '__str__',
    'latest_bundle'
]