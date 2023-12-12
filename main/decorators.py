from django.conf import settings


class ProductionCheck:

    def __init__(self, f):
        self.f = f
        self.production = settings.IS_PRODUCTION

    def __get__(self, obj, objtype):
        """Support instance methods."""
        import functools
        return functools.partial(self.__call__, obj)

    def __call__(self, *args, **kwargs):
        if self.production:
        #if True:
            r = self.f(*args, **kwargs)
            if r:
                return r