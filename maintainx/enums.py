


class MaintainxDefaultCategories:
    DAMAGE = "Damage"
    ELECTRICAL = "Electrical"
    MECHANICAL = "Mechanical"
    PREVENTIVE = "Preventive"
    REFRIGERATION = "Refrigeration"
    SAFETY = "Safety"
    STANDARD_OPERATING_PROCEDURE = "Standard Operating Procedure"
    BUNDLE_CHANGE_OR_ASSET_UPDATE = "Bundle Changes / Asset Updates"
    PRICING_CHANGES = 'Admin -- meter pricing changes'

    CATEGORIES_LIST = [
        DAMAGE,
        ELECTRICAL,
        MECHANICAL,
        PREVENTIVE,
        REFRIGERATION,
        SAFETY,
        STANDARD_OPERATING_PROCEDURE,
        BUNDLE_CHANGE_OR_ASSET_UPDATE,
        PRICING_CHANGES
    ]


class MaintainxWorkOrderPriority:
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    PRIORITIES_LIST = [NONE, LOW, MEDIUM, HIGH]