from django import forms

from .models import Item, Section, Store


class PasteForm(forms.Form):
    text = forms.CharField(
        label="LINEの文を貼り付け",
        max_length=20000,
        widget=forms.Textarea(
            attrs={"rows": 14, "placeholder": "★業務スーパー\nバナナ\n納豆2パック"}
        ),
    )


class ImportRowForm(forms.Form):
    include = forms.BooleanField(label="取り込む", required=False)
    name = forms.CharField(label="品名", max_length=200)
    quantity = forms.CharField(label="数量", max_length=100, required=False)
    note = forms.CharField(label="メモ", max_length=500, required=False)
    store = forms.ModelChoiceField(
        label="店",
        queryset=Store.objects.all(),
        required=False,
        empty_label="品目の既定の店",
    )
    section = forms.ModelChoiceField(
        label="新規品目のジャンル",
        queryset=Section.objects.all(),
        required=False,
        empty_label="その他",
    )
    choice = forms.ChoiceField(label="品目の確認", required=False)

    def __init__(self, *args, candidates=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["choice"].choices = (
            [("", "入力した品名のまま")]
            + [(str(i.pk), f"{i.name}にする") for i in candidates]
            + [("new", "別の新規品目として登録")]
        )


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            "name",
            "name_reading",
            "section",
            "default_store",
            "default_quantity",
            "tap_quantity",
            "default_note",
            "is_favorite",
            "is_hidden",
        ]
        labels = {"section": "ジャンル", "default_store": "既定の店"}


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ["name", "description"]
