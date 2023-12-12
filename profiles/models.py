from django.db import models
from django.contrib.auth.models import User


class UserType():
    EXECUTIVE = 'executive'
    BACKOFFICE = 'backoffice'
    TECHNICIAN = 'technician'
    CHOICES = (
        (EXECUTIVE, EXECUTIVE),
        (BACKOFFICE, BACKOFFICE),
        (TECHNICIAN, TECHNICIAN),
    )


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_profile')
    user_type = models.CharField(
        choices=UserType.CHOICES,
        blank=False,
        max_length=20,
        null=False)

    def __str__(self):
        return f"{self.user.get_full_name()}: {self.user_type}"