from django.contrib import admin

from .models import Country, Currency, Language, Region

admin.site.register([Region, Language, Currency])


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "cca3", "region", "population")
    search_fields = ("name", "cca3")
    list_filter = ("region", "is_synthetic")
