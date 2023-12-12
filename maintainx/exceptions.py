


class MaintainxTooManyRequests(Exception):
    """
    Trigger when maintainx replies to a request with a 429 Error code.
    """
    pass
