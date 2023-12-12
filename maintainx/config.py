WORK_ORDER_FIELD_MAP = {
    'id': 'maintainx_id', 
    'title': 'title',
    'description' : 'description',
    'priority': 'priority_level', 
    'assetId': 'asset_maintainx_id',
    'locationId': 'location_maintainx_id',
    'completedAt': 'completed_date', 
    'completerId': 'completed_by_id', 
    'categories': 'category',
    'creatorId': 'assigned_by_id',
    'status': 'status',
    'createdAt': 'created_date',
    'updatedAt': 'updated_date',
}


WORK_ORDER_PART_FIELD_MAP = {
    'id': 'maintainx_id',
    'name': 'name',
    'area': 'area',
    'description': 'description',
    'availableQuantity': 'available_quantity',
    'barcode': 'barcode',
    'copyOnRecurring': 'copy_on_recurring',
    'minimumQuantity': 'minimum_quantity',
    'unitCost': 'unit_cost'
}


USER_FIELD_MAP = {
    'id' : 'maintainx_id',
    'firstName' : 'first_name',
    'lastName' : 'last_name',
    'role' : 'role',
    'email' : 'email',
    'phoneNumber' : 'phone_number',
    'removedFromOrganization' : 'removed_from_organization'
}
