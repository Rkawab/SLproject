import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .api_views import entry_data, item_data, open_entries
from .classification import classify_section
from .forms import ImportRowForm, ItemForm, PasteForm, SectionForm
from .line_parser import parse_lines
from .matching import match_item
from .models import Item, ItemAlias, Section, Store
from .normalize import make_key
from .reading import item_sort_key
from .services import (
    add_alias,
    add_to_list,
    complete_shopping,
    fallback_section,
    merge_items,
    move_items,
    register_item,
)


@login_required
def shopping_list(request):
    return render(
        request,
        "shopping/list.html",
        {
            "stores": Store.objects.all(),
            "initial_entries": [entry_data(e) for e in open_entries()],
        },
    )


@login_required
@require_POST
def complete(request):
    store = (
        get_object_or_404(Store, pk=request.POST.get("store_id"))
        if request.POST.get("store_id")
        else None
    )
    count = complete_shopping(store)
    messages.success(request, f"購入済み{count}件を片付けました。")
    return redirect("shopping:list")


@login_required
def add_page(request):
    items = sorted(
        Item.objects.filter(is_hidden=False).select_related("section"),
        key=item_sort_key,
    )
    sections = list(Section.objects.all())
    for section in sections:
        section.page_items = [item for item in items if item.section_id == section.pk]
    return render(
        request,
        "shopping/add.html",
        {
            "sections": sections,
            "item_data": [item_data(item) for item in items],
            "section_data": [
                {
                    "id": s.pk,
                    "name": s.name,
                    "description": s.description,
                    "is_fallback": s.is_fallback,
                }
                for s in sections
            ],
            "frequent": Item.objects.filter(is_hidden=False).order_by(
                "-is_favorite", "-use_count", "-last_used_at", "name"
            )[:12],
            "initial_entries": [entry_data(e) for e in open_entries()],
            "stores": Store.objects.all(),
        },
    )


@login_required
def paste(request):

    return render(request, "shopping/paste.html", {"form": PasteForm()})


@login_required
@require_POST
def paste_preview(request):

    confirming = request.POST.get("action") == "confirm"
    if confirming:
        token = request.POST.get("token", "")
        if not token or token != request.session.get("paste_token"):
            messages.error(
                request,
                "取込は確定済みか、有効期限が切れました。もう一度読み取ってください。",
            )
            return redirect("shopping:paste")
        text = request.session.get("paste_text", "")
    else:
        form = PasteForm(request.POST)
        if not form.is_valid():
            return render(request, "shopping/paste.html", {"form": form})
        text = form.cleaned_data["text"]
        request.session["paste_text"] = text
        request.session["paste_token"] = secrets.token_urlsafe(24)
    parsed = parse_lines(text)
    rows = []
    valid = True
    for index, row in enumerate(parsed):
        if row.kind == "heading":
            rows.append({"parsed": row, "form": None})
            continue
        match = row.match
        form = ImportRowForm(
            request.POST if confirming else None,
            prefix=f"row-{index}",
            candidates=match.candidates,
            initial={
                "include": row.include,
                "name": match.name,
                "quantity": match.quantity,
                "note": match.note,
                "store": row.store,
                "section": classify_section(match.name)
                if not confirming and match.kind == "new"
                else None,
            },
        )
        if confirming:
            if not form.is_valid():
                # 取り込まない行にもフォーム値を保持し、意図せぬ登録をしない。
                valid = False
        rows.append({"parsed": row, "form": form})
    if confirming and valid:
        count = 0
        with transaction.atomic():
            for row in rows:
                form = row["form"]
                if not form or not form.cleaned_data["include"]:
                    continue
                data = form.cleaned_data
                match = match_item(data["name"])
                if data["choice"] and data["choice"] != "new":
                    item = Item.objects.get(pk=int(data["choice"]))
                elif data["choice"] == "new" or not match.item:
                    item = register_item(
                        data["name"],
                        data["section"] or fallback_section(),
                        data["store"],
                        request.user,
                        quantity=data["quantity"],
                    )
                else:
                    item = match.item
                result = add_to_list(
                    item, data["quantity"], data["note"], data["store"], request.user
                )
                if result.status == "already_listed":
                    # プレビューで明示的に取り込むを選んだ既存行のみ数量・メモ更新。
                    result.entry.quantity = data["quantity"]
                    result.entry.note = data["note"]
                    if data["store"]:
                        result.entry.store = data["store"]
                    result.entry.save()
                else:
                    count += 1
        request.session.pop("paste_token", None)
        request.session.pop("paste_text", None)
        messages.success(request, f"{count}件をリストに追加しました。")
        return redirect("shopping:list")
    return render(
        request,
        "shopping/preview.html",
        {"rows": rows, "token": request.session["paste_token"]},
    )


@login_required
@require_http_methods(["GET", "POST"])
def items(request):

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "move":
            section = get_object_or_404(Section, pk=request.POST.get("section"))
            count = move_items(request.POST.getlist("item_ids"), section)
            messages.success(request, f"{count}件を{section.name}に移動しました。")
        elif action in ("favorite", "hidden"):
            with transaction.atomic():
                item = get_object_or_404(
                    Item.objects.select_for_update(), pk=request.POST.get("item_id")
                )
                field = "is_favorite" if action == "favorite" else "is_hidden"
                setattr(item, field, not getattr(item, field))
                item.save(update_fields=[field])
        return redirect("shopping:items")
    all_items = sorted(Item.objects.select_related("section"), key=item_sort_key)
    sections = list(Section.objects.all())
    for section in sections:
        section.page_items = [
            item for item in all_items if item.section_id == section.pk
        ]
    pairs = []
    for index, item in enumerate(all_items):
        for other in all_items[index + 1 :]:
            if item.name_key in other.name_key or other.name_key in item.name_key:
                pairs.append((item, other))
    return render(
        request, "shopping/items.html", {"sections": sections, "pairs": pairs}
    )


@login_required
@require_http_methods(["GET", "POST"])
def item_edit(request, pk):

    item = get_object_or_404(Item, pk=pk)
    form = ItemForm(instance=item)
    alias_error = ""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "alias-add":
            try:
                add_alias(item, request.POST.get("alias", ""))
                return redirect("shopping:item-edit", pk=pk)
            except ValidationError as exc:
                alias_error = " / ".join(exc.messages)
        elif action == "alias-delete":
            ItemAlias.objects.filter(
                pk=request.POST.get("alias_id"), item=item
            ).delete()
            return redirect("shopping:item-edit", pk=pk)
        else:
            form = ItemForm(request.POST, instance=item)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                    messages.success(request, "品目を保存しました。")
                    return redirect("shopping:items")
                except ValidationError as exc:
                    form.add_error(None, exc)
    return render(
        request,
        "shopping/item_edit.html",
        {"item": item, "form": form, "alias_error": alias_error},
    )


@login_required
@require_http_methods(["GET", "POST"])
def item_merge(request, pk):

    src = get_object_or_404(Item, pk=pk)
    targets = Item.objects.exclude(pk=pk)
    if request.method == "POST":
        dst = get_object_or_404(targets, pk=request.POST.get("target"))
        merge_items(src, dst)
        messages.success(request, f"{src.name}を{dst.name}に統合しました。")
        return redirect("shopping:items")
    query = request.GET.get("q", "").strip()
    if query:
        key = make_key(query)
        targets = targets.filter(
            Q(name_key__contains=key) | Q(aliases__alias_key__contains=key)
        ).distinct()
    selected = (
        targets.filter(pk=request.GET.get("target")).first()
        if request.GET.get("target")
        else None
    )
    return render(
        request,
        "shopping/merge.html",
        {"item": src, "targets": targets, "selected": selected, "query": query},
    )


@login_required
@require_http_methods(["GET", "POST"])
def sections(request):

    form = SectionForm()
    if request.method == "POST":
        action = request.POST.get("action")
        section = (
            get_object_or_404(Section, pk=request.POST.get("section_id"))
            if request.POST.get("section_id")
            else None
        )
        if action in ("add", "edit"):
            form = SectionForm(request.POST, instance=section)
            if form.is_valid():
                obj = form.save(commit=False)
                if not obj.pk:
                    obj.order = (
                        Section.objects.filter(is_fallback=False).aggregate(
                            value=Max("order")
                        )["value"]
                        or 0
                    ) + 1
                obj.save()
                return redirect("shopping:sections")
        elif section and action == "delete":
            if section.is_fallback:
                messages.error(request, "その他は削除できません。")
            elif request.POST.get("confirm") == "yes":
                with transaction.atomic():
                    Item.objects.filter(section=section).update(
                        section=fallback_section()
                    )
                    section.delete()
            else:
                return render(
                    request,
                    "shopping/section_delete.html",
                    {
                        "section": section,
                        "count": Item.objects.filter(section=section).count(),
                    },
                )
            return redirect("shopping:sections")
        elif section and action in ("up", "down"):
            if not section.is_fallback:
                with transaction.atomic():
                    ordered = list(
                        Section.objects.select_for_update().filter(is_fallback=False)
                    )
                    index = next(i for i, s in enumerate(ordered) if s.pk == section.pk)
                    other = index + (-1 if action == "up" else 1)
                    if 0 <= other < len(ordered):
                        ordered[index], ordered[other] = ordered[other], ordered[index]
                    for order, obj in enumerate(ordered, 1):
                        Section.objects.filter(pk=obj.pk).update(order=order)
            return redirect("shopping:sections")
    return render(
        request,
        "shopping/sections.html",
        {"sections": Section.objects.all(), "form": form},
    )
