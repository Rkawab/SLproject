import json
from functools import wraps

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .matching import match_item, split_quantity_note
from .models import Entry, Item, Section, Store
from .normalize import make_key
from .services import add_alias, add_to_list, register_item, tap_item


def api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "ログインしてください。"}, status=401)
        try:
            if request.method == "POST":
                request.payload = json.loads(request.body or b"{}")
                if not isinstance(request.payload, dict):
                    raise ValueError("入力形式が不正です。")
            return view(request, *args, **kwargs)
        except (ValueError, TypeError, ValidationError) as exc:
            message = (
                " / ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else str(exc)
            )
            return JsonResponse(
                {"error": message or "入力を確認してください。"}, status=400
            )
        except ObjectDoesNotExist:
            return JsonResponse({"error": "対象が見つかりません。"}, status=404)
        except IntegrityError:
            return JsonResponse(
                {"error": "同じ品目が既にあります。再読み込みしてください。"},
                status=409,
            )

    return wrapped


def text_field(data, name, limit, default=""):
    value = data.get(name, default)
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{name} は{limit}文字以内で入力してください。")
    return value.strip()


def optional_object(model, value):
    return model.objects.get(pk=int(value)) if value else None


def item_data(item):
    return {
        "id": item.pk,
        "name": item.name,
        "section_id": item.section_id,
        "section": item.section.name,
        "tap_quantity": item.tap_quantity,
        "tap_url": reverse("shopping:api-tap", args=[item.pk]),
        "quantity": item.default_quantity,
        "note": item.default_note,
        "store_id": item.default_store_id,
        "is_hidden": item.is_hidden,
    }


def entry_data(entry):
    return {
        "id": entry.pk,
        "item_id": entry.item_id,
        "tap_quantity": entry.item.tap_quantity,
        "name": entry.item.name,
        "quantity": entry.quantity,
        "note": entry.note,
        "store_id": entry.store_id,
        "section_id": entry.item.section_id,
        "section": entry.item.section.name,
        "section_order": entry.item.section.order,
        "is_fallback": entry.item.section.is_fallback,
        "is_checked": entry.is_checked,
        "added_by": entry.added_by_id,
        "updated_at": entry.updated_at.isoformat(),
        "toggle_url": reverse("shopping:api-toggle", args=[entry.pk]),
        "update_url": reverse("shopping:api-update", args=[entry.pk]),
        "delete_url": reverse("shopping:api-delete", args=[entry.pk]),
    }


def open_entries():
    return Entry.objects.filter(completed_at__isnull=True).select_related(
        "item__section", "store"
    )


@require_GET
@api
def entries(request):
    # 最大50件程度なので全件返却。削除・完了もクライアントの置換で反映する。
    return JsonResponse(
        {
            "full": True,
            "entries": [entry_data(e) for e in open_entries()],
            "since": timezone.now().isoformat(),
        }
    )


@require_POST
@api
@transaction.atomic
def toggle(request, pk):
    entry = get_object_or_404(open_entries().select_for_update(of=("self",)), pk=pk)
    checked = request.payload.get("checked", not entry.is_checked)
    if not isinstance(checked, bool):
        raise ValueError("checked は真偽値で指定してください。")
    entry.is_checked = checked
    entry.checked_at = timezone.now() if checked else None
    entry.checked_by = request.user if checked else None
    entry.save()
    return JsonResponse({"entry": entry_data(entry)})


@require_POST
@api
@transaction.atomic
def update_entry(request, pk):
    entry = get_object_or_404(open_entries().select_for_update(of=("self",)), pk=pk)
    entry.quantity = text_field(request.payload, "quantity", 100, entry.quantity)
    entry.note = text_field(request.payload, "note", 500, entry.note)
    if "store_id" in request.payload:
        entry.store = optional_object(Store, request.payload["store_id"])
    entry.save()
    return JsonResponse({"entry": entry_data(entry)})


@require_POST
@api
def delete_entry(request, pk):
    Entry.objects.filter(pk=pk, completed_at__isnull=True).delete()
    return JsonResponse({"status": "deleted", "id": pk})


def added_response(item, request, data, quantity="", note=""):
    result = add_to_list(
        item,
        text_field(data, "quantity", 100, quantity),
        text_field(data, "note", 500, note),
        optional_object(Store, data.get("store_id")),
        request.user,
    )
    return JsonResponse(
        {
            "status": result.status,
            "entry": entry_data(result.entry),
            "item": item_data(item),
            "requested": {
                "quantity": text_field(data, "quantity", 100, quantity),
                "note": text_field(data, "note", 500, note),
            },
        }
    )


@require_POST
@api
def add(request):
    data = request.payload
    if data.get("item_id"):
        quantity, note = "", ""
        if data.get("raw"):
            _, quantity, note = split_quantity_note(text_field(data, "raw", 800))
        return added_response(
            Item.objects.get(pk=int(data["item_id"])), request, data, quantity, note
        )
    raw = text_field(data, "raw", 800)
    if not make_key(raw):
        raise ValueError("品名を入力してください。")
    result = match_item(raw)
    if not make_key(result.name):
        raise ValueError("品名を入力してください。")
    if result.item:
        return added_response(result.item, request, data, result.quantity, result.note)
    if result.kind == "new" and data.get("auto_register") is True:
        item = register_item(
            result.name,
            store=optional_object(Store, data.get("store_id")),
            user=request.user,
            quantity=result.quantity,
        )
        response = added_response(
            item, request, data, result.quantity or item.tap_quantity, result.note
        )
        payload = json.loads(response.content)
        payload["auto_registered"] = True
        return JsonResponse(payload)
    return JsonResponse(
        {
            "status": result.kind,
            "name": result.name,
            "quantity": result.quantity,
            "note": result.note,
            "candidates": [item_data(i) for i in result.candidates],
        }
    )


@require_GET
@api
def suggest(request):
    key = make_key(request.GET.get("q", "")[:200])
    matches = []
    if key:
        for item in Item.objects.filter(is_hidden=False).prefetch_related("aliases"):
            aliases = [a.alias for a in item.aliases.all() if key in a.alias_key]
            if key in item.name_key or aliases:
                prefix = item.name_key.startswith(key) or any(
                    make_key(a).startswith(key) for a in aliases
                )
                matches.append(
                    (
                        not prefix,
                        item.name,
                        item_data(item) | {"alias": aliases[0] if aliases else ""},
                    )
                )
    matches.sort(key=lambda row: row[:2])
    return JsonResponse({"items": [row[2] for row in matches[:5]]})


@require_POST
@api
def create_item(request):
    data = request.payload
    name = text_field(data, "name", 200)
    quantity = text_field(data, "quantity", 100)
    text_field(data, "note", 500)
    if data.get("alias_item_id"):
        item = Item.objects.get(pk=int(data["alias_item_id"]))
        add_alias(item, name)
    else:
        item = register_item(
            name,
            optional_object(Section, data.get("section_id")),
            optional_object(Store, data.get("store_id")),
            request.user,
            quantity=quantity,
        )
    return added_response(item, request, data, quantity or item.tap_quantity)


@require_POST
@api
def tap(request, pk):
    data = request.payload
    result = tap_item(
        get_object_or_404(Item, pk=pk),
        text_field(data, "action", 16, "increment"),
        text_field(data, "request_id", 40),
        request.user,
        optional_object(Store, data.get("store_id")),
        text_field(data, "quantity", 100),
        text_field(data, "note", 500),
    )
    item = Item.objects.get(pk=pk)
    return JsonResponse(
        {
            "status": result.status,
            "entry": entry_data(result.entry) if result.entry else None,
            "previous": result.previous,
            "item": item_data(item),
        }
    )
