from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from .matching import exact_item
from .models import Entry, Item, ItemAlias, Section, TapOperation
from .normalize import make_key
from .quantity import change_quantity, default_tap_quantity


@dataclass
class AddResult:
    status: str
    entry: Entry


def fallback_section():
    return Section.objects.get(is_fallback=True)


def register_item(name, section=None, store=None, user=None, quantity=""):
    from .classification import classify_section

    if not make_key(name) or len(name.strip()) > 200:
        raise ValidationError("品目名は1〜200文字で入力してください。")
    existing = exact_item(make_key(name))
    if existing:
        return existing
    section = section or classify_section(name)
    return _register_item(name, section, store, user, quantity)


@transaction.atomic
def _register_item(name, section, store, user, quantity):
    # 品目名と別名をまたぐ登録も、この共通ロックで直列化する。
    Section.objects.select_for_update().get(is_fallback=True)
    key = make_key(name)
    if not key:
        raise ValidationError("品目名を入力してください。")
    existing = exact_item(key)
    if existing:
        return existing
    try:
        with transaction.atomic():
            item = Item(
                name=name.strip(),
                section=section or fallback_section(),
                default_store=store,
                created_by=user,
                tap_quantity=default_tap_quantity(name, quantity),
            )
            item.full_clean()
            item.save()
            return item
    except (IntegrityError, ValidationError):
        existing = exact_item(key)
        if existing:
            return existing
        raise


@transaction.atomic
def add_alias(item, alias):
    Section.objects.select_for_update().get(is_fallback=True)
    key = make_key(alias)
    existing = exact_item(key)
    if existing and existing.pk != item.pk:
        raise ValidationError(
            f"それは既に品目「{existing.name}」です。統合してください。"
        )
    found = ItemAlias.objects.filter(alias_key=key).first()
    if found:
        return found
    obj = ItemAlias(item=item, alias=alias.strip())
    obj.full_clean()
    obj.save()
    return obj


@transaction.atomic
def add_to_list(item, quantity="", note="", store=None, user=None):
    item = Item.objects.select_for_update().get(pk=item.pk)
    entry = (
        Entry.objects.select_for_update()
        .filter(item=item, completed_at__isnull=True)
        .first()
    )
    if entry and not entry.is_checked:
        return AddResult("already_listed", entry)
    now = timezone.now()
    if entry:
        entry.is_checked = False
        entry.checked_at = None
        entry.checked_by = None
        entry.quantity = quantity or item.default_quantity
        entry.note = note or item.default_note
        entry.store = store or item.default_store
        entry.save()
        status = "revived"
    else:
        try:
            with transaction.atomic():
                entry = Entry.objects.create(
                    item=item,
                    quantity=quantity or item.default_quantity,
                    note=note or item.default_note,
                    store=store or item.default_store,
                    added_by=user,
                )
        except IntegrityError:
            entry = Entry.objects.get(item=item, completed_at__isnull=True)
            return AddResult("already_listed", entry)
        status = "added"
    values = {"use_count": F("use_count") + 1, "last_used_at": now}
    if note:
        values["default_note"] = note
    Item.objects.filter(pk=item.pk).update(**values)
    return AddResult(status, entry)


@transaction.atomic
def merge_items(src, dst):
    if src.pk == dst.pk:
        raise ValidationError("同じ品目には統合できません。")
    Section.objects.select_for_update().get(is_fallback=True)
    locked = {
        item.pk: item
        for item in Item.objects.select_for_update()
        .filter(pk__in=[src.pk, dst.pk])
        .order_by("pk")
    }
    src, dst = locked[src.pk], locked[dst.pk]
    target = Entry.objects.filter(item=dst, completed_at__isnull=True).first()
    for entry in Entry.objects.filter(item=src):
        if entry.completed_at is None and target:
            target.quantity = target.quantity or entry.quantity
            target.note = target.note or entry.note
            target.save()
            entry.delete()
        else:
            entry.item = dst
            entry.save()
    names = [a.alias for a in src.aliases.all()] + [src.name]
    last_used = [dt for dt in [src.last_used_at, dst.last_used_at] if dt]
    dst.use_count += src.use_count
    dst.last_used_at = max(last_used) if last_used else None
    dst.is_favorite = dst.is_favorite or src.is_favorite
    src.delete()
    dst.save()
    for alias in names:
        add_alias(dst, alias)
    return dst


def move_items(item_ids, section):
    return Item.objects.filter(pk__in=item_ids).update(section=section)


def entries_for_store(queryset, store=None):
    if store:
        queryset = queryset.filter(Q(store=store) | Q(store__isnull=True))
    return queryset


def complete_shopping(store=None):
    return entries_for_store(
        Entry.objects.filter(completed_at__isnull=True, is_checked=True), store
    ).update(completed_at=timezone.now(), updated_at=timezone.now())


@dataclass
class TapResult:
    status: str
    entry: Entry | None
    previous: dict | None = None


@transaction.atomic
def tap_item(item, action, request_id, user, store=None, quantity="", note=""):
    try:
        operation_id = UUID(str(request_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError("操作IDが不正です。再読み込みしてください。") from exc
    if action not in {"increment", "decrement", "remove", "restore"}:
        raise ValidationError("数量操作が不正です。")
    item = Item.objects.select_for_update().get(pk=item.pk)
    operation = TapOperation.objects.filter(pk=operation_id).first()
    entry = (
        Entry.objects.select_for_update()
        .filter(item=item, completed_at__isnull=True)
        .first()
    )
    if operation:
        if (
            operation.item_id != item.pk
            or operation.user_id != user.pk
            or operation.action != action
        ):
            raise ValidationError("操作IDが別の操作に使われています。")
        return TapResult("already_processed", entry)
    previous = (
        {"quantity": entry.quantity, "note": entry.note, "store_id": entry.store_id}
        if entry
        else None
    )
    if action == "remove":
        if entry:
            entry.delete()
        result = TapResult("removed", None, previous)
    elif action == "restore":
        if entry:
            result = TapResult("already_listed", entry)
        else:
            addition = add_to_list(item, quantity, note, store, user)
            result = TapResult("restored", addition.entry)
    elif action == "decrement" and (not entry or entry.is_checked):
        result = TapResult("unchanged", entry)
    else:
        current = (
            (entry.quantity or item.tap_quantity)
            if entry and not entry.is_checked
            else ""
        )
        updated = change_quantity(
            current, item.tap_quantity, -1 if action == "decrement" else 1
        )
        if not updated:
            if entry:
                entry.delete()
            result = TapResult("removed", None, previous)
        elif entry and not entry.is_checked:
            entry.quantity = updated
            entry.save(update_fields=["quantity", "updated_at"])
            result = TapResult(
                "incremented" if action == "increment" else "decremented",
                entry,
                previous,
            )
        else:
            addition = add_to_list(item, updated, store=store, user=user)
            result = TapResult(addition.status, addition.entry, previous)
    TapOperation.objects.create(id=operation_id, item=item, user=user, action=action)
    TapOperation.objects.filter(
        created_at__lt=timezone.now() - timedelta(days=7)
    ).delete()
    return result
