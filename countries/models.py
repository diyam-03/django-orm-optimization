"""
Data model.

Why these tables? Each relationship type triggers a different N+1 fix:

  Region  --< Country            one-to-many (FK)    -> select_related   (SQL JOIN)
  Country >--< Language          many-to-many        -> prefetch_related (extra query)
  Country >--< Currency          many-to-many        -> prefetch_related (extra query)
"""
from django.db import models


class Region(models.Model):
    name = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Language(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Currency(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    symbol = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name_plural = "currencies"
        ordering = ["code"]

    def __str__(self):
        return self.code


class Country(models.Model):
    name = models.CharField(max_length=120)
    cca3 = models.CharField(max_length=12, unique=True)
    capital = models.CharField(max_length=120, blank=True)
    flag = models.CharField(max_length=16, blank=True)
    population = models.BigIntegerField(default=0)
    area = models.FloatField(default=0)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="countries")
    languages = models.ManyToManyField(Language, related_name="countries", blank=True)
    currencies = models.ManyToManyField(Currency, related_name="countries", blank=True)
    # Synthetic rows exist only so the index demo has enough data to matter.
    is_synthetic = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "countries"
        # The three indexes match the three queries the API actually runs:
        #   search by exact name              -> ctry_name_idx
        #   "population above X" / sort by it -> ctry_pop_idx
        #   "biggest countries in a region"   -> ctry_region_pop_idx (composite)
        # Names are explicit so the benchmark can find (and temporarily drop) them.
        indexes = [
            models.Index(fields=["name"], name="ctry_name_idx"),
            models.Index(fields=["population"], name="ctry_pop_idx"),
            models.Index(fields=["region", "-population"], name="ctry_region_pop_idx"),
        ]

    def __str__(self):
        return self.name
