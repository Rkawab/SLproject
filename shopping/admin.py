from django.contrib import admin

from .models import Entry, Item, ItemAlias, Section, Store, TapOperation


class AliasInline(admin.TabularInline):
    model = ItemAlias
    extra = 1


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["name", "section", "default_store", "is_favorite", "is_hidden"]
    list_filter = ["section", "is_hidden"]
    search_fields = ["name", "aliases__alias"]
    inlines = [AliasInline]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    exclude = ["is_fallback"]

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register([Store, ItemAlias, Entry, TapOperation])
