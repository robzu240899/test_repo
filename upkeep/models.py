from django.db import models

# Create your models here.
class StoredUpkeepToken(models.Model):
    session_token = models.CharField(max_length=100)
    saved_at = models.DateTimeField(auto_now_add=True)