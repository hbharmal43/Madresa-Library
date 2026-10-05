from django import forms
from django.conf import settings

from unfold.widgets import (
    UnfoldAdminSelectWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
)


def loan_day_choices():
    return [(d, f"{d} days") for d in settings.LIBRARY_LOAN_DAY_CHOICES]


class BarcodeForm(forms.Form):
    """Single scan field. A USB scanner types the digits and sends Enter."""

    barcode = forms.CharField(
        label="Scan barcode",
        max_length=32,
        widget=UnfoldAdminTextInputWidget(
            attrs={
                "autofocus": True,
                "autocomplete": "off",
                "inputmode": "numeric",
                "placeholder": "Scan or type the barcode and press Enter",
            }
        ),
    )

    def clean_barcode(self):
        return self.cleaned_data["barcode"].strip()


class CheckoutForm(forms.Form):
    barcode = forms.CharField(widget=forms.HiddenInput)
    borrower_name = forms.CharField(
        label="Borrower name",
        max_length=150,
        widget=UnfoldAdminTextInputWidget(
            attrs={"autofocus": True, "autocomplete": "off", "placeholder": "Full name"}
        ),
    )
    borrower_phone = forms.CharField(
        label="Phone (optional)",
        max_length=30,
        required=False,
        widget=UnfoldAdminTextInputWidget(attrs={"autocomplete": "off", "inputmode": "tel"}),
    )
    loan_days = forms.TypedChoiceField(
        label="Loan period",
        coerce=int,
        widget=UnfoldAdminSelectWidget,
    )
    notes = forms.CharField(
        label="Notes (optional)",
        required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["loan_days"].choices = loan_day_choices()
        self.fields["loan_days"].initial = settings.LIBRARY_DEFAULT_LOAN_DAYS

    def clean_borrower_name(self):
        return self.cleaned_data["borrower_name"].strip()
