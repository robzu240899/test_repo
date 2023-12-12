from django import forms
from .enums import DeleteChoices


class NonGeneratedForm(forms.Form):
    objects_to_be_delete = forms.ChoiceField(choices=DeleteChoices.CHOICES)