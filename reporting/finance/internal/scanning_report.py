from roommanager.models import HardwareBundlePairing



class BundleScanningReport():

    def __init__(self, query_parameters: dict):
        self.query_parameters = self._check_query_parameters(query_parameters)
        self.base_queryset = HardwareBundlePairing.objects.filter()

    def _check_query_parameters(self, query_parameters):
        assert isinstance(query_parameters, dict)
        acceptable_fields = [field.name for field in HardwareBundlePairing._meta.local_fields]
        for param in query_parameters.keys():
            if '__' in param:
                param = param.split('__')[0]
            if not param in acceptable_fields:
                raise Exception(
                    f"Invalid query parameters. Available parameters: {','.join(acceptable_fields)}"
                )
        return query_parameters

    def get_dataset(self):
        pass

