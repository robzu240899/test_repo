from main import settings
from django.contrib.staticfiles.storage import ManifestFilesMixin
from storages.backends.s3boto3 import S3Boto3Storage


class ManifestStaticFilesStorage(ManifestFilesMixin, S3Boto3Storage):
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    location = settings.S3_STATIC_DIR

    def read_manifest(self):
        try: return super(ManifestStaticFilesStorage,self).read_manifest()
        except IOError: return None