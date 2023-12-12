class FailedEventRuleCreation(Exception):

    def __init__(self, machine, equipment_type, msg=None):
        if msg is None:
            msg = "The Machine {} is being associated with an incompatible equipment type: {}".format(
                machine,
                equipment_type
            )
        super(FailedEventRuleCreation, self).__init__(msg)
        self.machine = machine