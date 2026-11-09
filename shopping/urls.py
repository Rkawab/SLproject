from django.urls import path

from . import api_views, views

app_name = "shopping"
urlpatterns = [
    path("", views.shopping_list, name="list"),
    path("items/", views.items, name="items"),
    path("items/<int:pk>/edit/", views.item_edit, name="item-edit"),
    path("items/<int:pk>/merge/", views.item_merge, name="item-merge"),
    path("sections/", views.sections, name="sections"),
    path("paste/", views.paste, name="paste"),
    path("paste/preview/", views.paste_preview, name="paste-preview"),
    path("add/", views.add_page, name="add"),
    path("complete/", views.complete, name="complete"),
    path("api/entries/", api_views.entries, name="api-entries"),
    path("api/entries/<int:pk>/toggle/", api_views.toggle, name="api-toggle"),
    path("api/entries/<int:pk>/update/", api_views.update_entry, name="api-update"),
    path("api/entries/<int:pk>/delete/", api_views.delete_entry, name="api-delete"),
    path("api/add/", api_views.add, name="api-add"),
    path("api/items/", api_views.create_item, name="api-items"),
    path("api/items/suggest/", api_views.suggest, name="api-suggest"),
]
