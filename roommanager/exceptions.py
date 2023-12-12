

class WrongEquipmentTypeForMachine(Exception):
    
    def __init__(self, machine, msg=None):
        if msg is None:
            msg = "The Machine %s has a different equipment type than \
            the Slot to which it is being coupled" % machine
        super(WrongEquipmentTypeForMachine, self).__init__(msg)
        self.machine = machine


class WrongEquipmentTypeForBundle(Exception):

    def __init__(self, machine, equipment_type, msg=None):
        if msg is None:
            msg = "The Machine {} is being associated with an incompatible equipment type: {}".format(
                machine,
                equipment_type
            )
        super(WrongEquipmentTypeForBundle, self).__init__(msg)
        self.machine = machine