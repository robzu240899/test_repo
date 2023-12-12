WORK_ORDER_FIELD_MAP = {
    'id': 'upkeep_id', 
    'title': 'title',
    'description' : 'description',
    'priority': 'priority_level', 
    'asset': 'asset_upkeep_id',
    'location': 'location_upkeep_id',
    'dateCompleted': 'completed_date', 
    'completedByUser': 'completed_by_upkeep_id', 
    'completedByUsername': 'completed_by_upkeep_username',
    'workOrderNo': 'work_order_no',
    'category': 'category',
    'assignedByUser': 'assigned_by_upkeep_id',
    'assignedByUsername': 'assigned_by_upkeep_username',
    'assignedToUser': 'assigned_to_upkeep_id',
    'assignedToUsername': 'assigned_to_upkeep_username',
    'status': 'status',
    'createdAt': 'created_date',
    'dueDate': 'duedate',
    'updatedAt': 'updated_date'
}


WORK_ORDER_PART_FIELDMAP = {
    'id': 'upkeep_id',
    'serial': 'serial',
    'details': 'details',
    'quantity': 'quantity', 
    'name': 'name', 
    'area': 'area', 
    'createdByUser': 'created_by_upkeep_id',
    'createdAt': 'created_date', 
    'updatedAt': 'updated_date'
}


UPKEEP_USER_FIELD_MAP = {
    'id' : 'upkeep_id',
    'firstName' : 'first_name',
    'lastName' : 'last_name',
    'jobTitle' : 'role',
    'email' : 'email',
    'phoneNumber' : 'phone_number',
}