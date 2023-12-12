from django.db import transaction
from .threads import RefundWorkOrderThread

def refund_as_work_order(sender, instance, created, **kwargs):
    print ("Entering signal after post save")
    if not created:
        return
    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(lambda: RefundWorkOrderThread(instance).start())
    else:
        RefundWorkOrderThread(instance).start()
    return True