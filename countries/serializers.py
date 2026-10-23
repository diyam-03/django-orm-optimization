from rest_framework import serializers

from .models import Country


class CountrySerializer(serializers.ModelSerializer):
    """
    The N+1 trap lives here, and it is completely normal-looking code.

    `obj.region.name`, `obj.languages.all()` and `obj.currencies.all()` each touch
    a related table. If the queryset did not load those up front, Django runs a
    NEW query for every country, for every field.
    """

    region = serializers.CharField(source="region.name")
    languages = serializers.SerializerMethodField()
    currencies = serializers.SerializerMethodField()

    class Meta:
        model = Country
        fields = ["id", "name", "cca3", "flag", "capital", "population", "area", "region", "languages", "currencies"]

    def get_languages(self, obj):
        return [lang.name for lang in obj.languages.all()]

    def get_currencies(self, obj):
        return [c.code for c in obj.currencies.all()]
