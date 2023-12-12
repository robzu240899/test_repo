import json
from datetime import datetime, date
from django.contrib.contenttypes.models import ContentType
from roommanager.models import LaundryRoom, Slot

class FixtureGenerator():

    def __init__(self, model_name):
        assert isinstance(str, model_name)
        assert model_name in ContentType.objects.all().values_list('model', flat=True)
        self.model_name = model_name
        self.set_content_type_data()
        self.set_model_data()
        #TODO: Add custom query support (specially dates handling)
        #TODO: Add custom fields support

    def _set_content_type_data(self):
        self.content_type = ContentType.objects.get(model=self.model_name)
        self.content_type_name = '.'.join(ct.natural_key())

    def _set_model_data(self):
        self.model_class = self.content_type.model_class()
        self.model_fields = [field.attname for field in self.model_class._meta.fields]

    @classmethod
    def save_file(filename, final_list):
        json_str = json.dumps(final_list)
        filename = 'laundryroomsfixtures{}.json'.format(datetime.today())
        with open(filename, 'w') as writable:
            writable.write(json_str)
            writable.close()

    def run(self):
        q = self.model_class.objects.all()
        self.FINAL_LIST = list()

        for record in q:
            d = dict()
            d = {
                'model' : self.content_type_name,
                'pk' : record.pk,
                fields : dict()
            }
            for field in self.model_fields:
                d['fields'][field] = getattr(record, field, None)
            self.FINAL_LIST.append(d)

        self.save_file

