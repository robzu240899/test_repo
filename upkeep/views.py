from django.contrib.auth.mixins import LoginRequiredMixin
from django.template.response import TemplateResponse
from django.shortcuts import render
from django.views import View
from .forms import NonGeneratedForm
from .utils import UpkeepNongeneratedManager
from .enums import DeleteChoices

# Create your views here.
class NonGeneratedView(LoginRequiredMixin, View):
    """
    Retrieves first n transactions in a room based on either laundry_room field or assigned_laundry_room_field
    """
    template_name = 'non_generated_upkeep.html'
    form_class = NonGeneratedForm

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        context = self.get_context_data()
        context.update({'form':form})
        return TemplateResponse(request, self.template_name, context)

    def get_context_data(self, **kwargs):
        context = {}
        self.upkeep_manager = UpkeepNongeneratedManager()
        context['assets'] = self.upkeep_manager.get_nongenerated_assets(ids_only=False)
        context['locations'] = self.upkeep_manager.get_nongenerated_locations()
        context['meters'] = self.upkeep_manager.get_nongenerated_meters()
        return context

    def post(self, request, *args, **kwargs):
        self.upkeep_manager = UpkeepNongeneratedManager()
        context = self.kwargs
        form = self.form_class(request.POST)
        response = {
            'assets' : [0, 0],
            'locations' : [0, 0],
            'meters': [0, 0]
        }
        if form.is_valid():
            objects_to_be_delete = form.cleaned_data.get('objects_to_be_delete')
            print (objects_to_be_delete)
            if objects_to_be_delete == DeleteChoices.ALL_ASSETS:
                response['assets'] = self.upkeep_manager.delete('assets')
            elif objects_to_be_delete == DeleteChoices.ASSETS_NO_EXTRAS:
                response['assets'] = self.upkeep_manager.delete('assets_no_extra')
            elif objects_to_be_delete == DeleteChoices.ALL_LOCATIONS:
                response['locations'] = self.upkeep_manager.delete('locations')
            elif objects_to_be_delete == DeleteChoices.ALL_METERS:
                response['meters'] = self.upkeep_manager.delete('meters')
        context.update({'form': form , 'upkeep_response':response})
        return TemplateResponse(request, self.template_name, context)