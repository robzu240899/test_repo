import threading
from django.core.mail import EmailMessage


class EmailThread(threading.Thread):

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.content_type = None
        super(EmailThread, self).__init__()

    def run(self):
        message = EmailMessage(**self.kwargs)
        if self.content_type: message.content_subtype = self.content_type
        message.send(fail_silently=False)

