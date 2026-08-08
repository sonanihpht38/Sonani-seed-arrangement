from django.contrib import admin

from .models import Company, ParameterType, ParameterValue, SystemSetting

admin.site.register(Company)
admin.site.register(SystemSetting)
admin.site.register(ParameterType)
admin.site.register(ParameterValue)
