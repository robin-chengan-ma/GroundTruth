from django.db import models


class Supplier(models.Model):
    class Tier(models.TextChoices):
        PRIORITY = "priority", "priority"
        NORMAL = "normal", "normal"
        WATCH = "watch", "watch"

    name = models.CharField(max_length=200, unique=True)
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.NORMAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "suppliers"

    def __str__(self):
        return self.name
