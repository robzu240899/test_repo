class WorkOrderStatus:
    COMPLETE = 'complete'
    ON_HOLD = 'onHold'
    OPEN = 'open'
    IN_PROGRESS = 'inProgress'

    CHOICES = (
        (COMPLETE, 'Complete'),
        (ON_HOLD, 'On Hold'),
        (OPEN, 'Open'),
        (IN_PROGRESS, 'In Progress')
    )

class DeleteChoices:
    ALL_ASSETS  = 'ASSETS'
    ASSETS_NO_EXTRAS = 'ASSETS_NO_EXTRAS'
    ALL_LOCATIONS = 'LOCATIONS'
    ALL_METERS = 'METERS'

    CHOICES = (
        (ALL_ASSETS, 'Delete All Assets'),
        (ASSETS_NO_EXTRAS, 'Delete Only Assets with NO Image and NO Work Order'),
        (ALL_LOCATIONS, 'Delete All Locations'),
        (ALL_METERS, 'Delete All Meters'),
    )