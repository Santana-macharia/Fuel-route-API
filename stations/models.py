from django.db import models


class Station(models.Model):
    """One truck stop, de-duplicated by OPIS id and geocoded to city level."""

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=9, decimal_places=6)  # USD per gallon
    lat = models.FloatField()
    lng = models.FloatField()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"
