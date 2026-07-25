from django.shortcuts import render
from django.http import JsonResponse

# Create your views here.

def MessManagementTest(request):
    return JsonResponse({"message": "Mess Management API is working!"})