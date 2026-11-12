from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .normalize import make_key
from .quantity import parse_quantity
from .reading import normalize_reading, reading_for_name, reading_sort_key


class Store(models.Model):
    name = models.CharField("店名", max_length=100, unique=True)
    aliases = models.JSONField("別名", default=list, blank=True)
    order = models.IntegerField("表示順", default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.name


class Section(models.Model):
    name = models.CharField("ジャンル名", max_length=100, unique=True)
    description = models.CharField("含めるもの", max_length=300, blank=True)
    order = models.IntegerField("表示順", default=0)
    is_fallback = models.BooleanField(default=False)

    class Meta:
        ordering = ["is_fallback", "order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_fallback"],
                condition=Q(is_fallback=True),
                name="one_fallback_section",
            )
        ]

    def delete(self, *args, **kwargs):
        if self.is_fallback:
            raise ValidationError("その他は削除できません。")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.name


class Item(models.Model):
    name = models.CharField("品目名", max_length=200, unique=True)
    name_key = models.CharField(max_length=300, unique=True, editable=False)
    name_reading = models.CharField(
        "読み（並び順）",
        max_length=1000,
        blank=True,
        help_text="空欄なら名前から自動入力します。読みが違う場合はかなで修正できます。",
    )
    default_note = models.CharField("既定のメモ", max_length=500, blank=True)
    default_quantity = models.CharField("既定数量", max_length=100, blank=True)
    tap_quantity = models.CharField(
        "1タップの数量",
        max_length=100,
        default="1個",
        help_text="例: 1個、1パック、100g",
    )
    default_store = models.ForeignKey(
        Store, null=True, blank=True, on_delete=models.SET_NULL
    )
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    is_favorite = models.BooleanField("★", default=False)
    is_hidden = models.BooleanField("非表示", default=False)
    use_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_favorite", "-use_count", "name"]

    def clean(self):
        amount, _ = parse_quantity(self.tap_quantity)
        if amount <= 0:
            raise ValidationError(
                {"tap_quantity": "1タップの数量は0より大きくしてください。"}
            )
        self.name = self.name.strip()
        self.name_key = make_key(self.name)
        previous = (
            Item.objects.filter(pk=self.pk).values("name", "name_reading").first()
            if self.pk
            else None
        )
        if not self.name_reading.strip() or (
            previous
            and self.name != previous["name"]
            and self.name_reading == previous["name_reading"]
        ):
            self.name_reading = reading_for_name(self.name)
        else:
            self.name_reading = normalize_reading(self.name_reading)
        if not self.name_key:
            raise ValidationError("品目名を入力してください。")
        if Item.objects.filter(name_key=self.name_key).exclude(pk=self.pk).exists():
            raise ValidationError("同じ名前の品目が既にあります。統合してください。")
        if (
            ItemAlias.objects.filter(alias_key=self.name_key)
            .exclude(item_id=self.pk)
            .exists()
        ):
            raise ValidationError("他の品目の別名と重複しています。統合してください。")

    def save(self, *args, **kwargs):
        self.clean()
        if kwargs.get("update_fields") and "name" in kwargs["update_fields"]:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "name_key",
                "name_reading",
            }
        super().save(*args, **kwargs)

    @property
    def sort_key(self):
        return (
            reading_sort_key(self.name_reading or reading_for_name(self.name))
            + "\0"
            + normalize_reading(self.name)
        )

    def __str__(self):
        return self.name


class ItemAlias(models.Model):
    item = models.ForeignKey(Item, related_name="aliases", on_delete=models.CASCADE)
    alias = models.CharField("別名", max_length=200)
    alias_key = models.CharField(max_length=300, unique=True, editable=False)

    def clean(self):
        self.alias_key = make_key(self.alias)
        if not self.alias_key:
            raise ValidationError("別名を入力してください。")
        if (
            Item.objects.filter(name_key=self.alias_key)
            .exclude(pk=self.item_id)
            .exists()
        ):
            raise ValidationError("他の品目名と重複しています。統合してください。")
        if (
            ItemAlias.objects.filter(alias_key=self.alias_key)
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError("この別名は既に登録されています。")

    def save(self, *args, **kwargs):
        self.clean()
        if kwargs.get("update_fields") and "alias" in kwargs["update_fields"]:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"alias_key"}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.alias


class Entry(models.Model):
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="entries")
    quantity = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=500, blank=True)
    store = models.ForeignKey(Store, null=True, blank=True, on_delete=models.SET_NULL)
    is_checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checked_entries",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="added_entries",
    )
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["item__section__is_fallback", "item__section__order", "added_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["item"],
                condition=Q(completed_at__isnull=True),
                name="one_open_entry_per_item",
            )
        ]


class TapOperation(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    item = models.ForeignKey(Item, null=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    action = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
