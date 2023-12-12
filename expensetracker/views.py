'''
Created on Apr 05, 2017

@author: Duong
'''
from django.shortcuts import render
from django.views.generic import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

# Create your views here.

class ExpenseTracker(View):
    
    @method_decorator(login_required)
    def get(self,request):
        return render(request, "expensetracker/index.html")