"""
The two daily-workflow pages: check out and check in. Both live inside the
admin so they share its login, sidebar and styling.
"""

from django.contrib import admin, messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import BarcodeForm, CheckoutForm
from .models import Loan
from .services import CirculationError, checkin, checkout, find_book


def _base_context(request, title: str) -> dict:
    context = admin.site.each_context(request)
    # No "opts" on purpose: Unfold would otherwise show "Library > Loans"
    # in the header instead of the page title.
    context.update({"title": title})
    return context


@permission_required("library.add_loan", raise_exception=True)
def checkout_view(request):
    context = _base_context(request, "Check out")
    book = None
    scan_form = BarcodeForm(request.GET or None)
    checkout_form = None

    if request.method == "POST":
        checkout_form = CheckoutForm(request.POST)
        if checkout_form.is_valid():
            data = checkout_form.cleaned_data
            book = find_book(data["barcode"])
            if book is None:
                messages.error(request, f"No book with barcode {data['barcode']}.")
                return redirect("admin:library_checkout")
            try:
                loan = checkout(
                    book=book,
                    borrower_name=data["borrower_name"],
                    borrower_grade=data["borrower_grade"],
                    borrower_phone=data["borrower_phone"],
                    loan_days=data["loan_days"],
                    user=request.user,
                    notes=data["notes"],
                )
            except CirculationError as exc:
                messages.error(request, str(exc))
                return redirect("admin:library_checkout")
            who = loan.borrower_name
            if loan.borrower_grade:
                who += f" ({loan.get_borrower_grade_display()})"
            messages.success(
                request,
                f"Checked out “{loan.book.title}” to {who}. Due {loan.due_date:%b %d, %Y}.",
            )
            return redirect("admin:library_checkout")
        # Invalid form: re-show the book so the librarian can fix the fields.
        book = find_book(request.POST.get("barcode", ""))

    elif scan_form.is_bound and scan_form.is_valid():
        barcode = scan_form.cleaned_data["barcode"]
        book = find_book(barcode)
        if book is None:
            messages.error(request, f"No book with barcode {barcode}.")
            return redirect("admin:library_checkout")
        if not book.is_available:
            current = book.current_loan
            if current:
                messages.warning(
                    request,
                    f"“{book.title}” is already checked out to {current.borrower_name} "
                    f"(due {current.due_date:%b %d, %Y}). Check it in first.",
                )
            else:
                messages.warning(
                    request, f"“{book.title}” is {book.get_status_display().lower()}."
                )
            return redirect("admin:library_checkout")
        checkout_form = CheckoutForm(initial={"barcode": book.barcode})

    recent = Loan.objects.open().select_related("book").order_by("-checked_out_at")[:10]
    context.update(
        {
            "scan_form": BarcodeForm() if book else scan_form,
            "checkout_form": checkout_form,
            "book": book,
            "recent_loans": recent,
            "checkin_url": reverse("admin:library_checkin"),
        }
    )
    return render(request, "admin/library/checkout.html", context)


@permission_required("library.change_loan", raise_exception=True)
def checkin_view(request):
    context = _base_context(request, "Check in")
    form = BarcodeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        barcode = form.cleaned_data["barcode"]
        book = find_book(barcode)
        if book is None:
            messages.error(request, f"No book with barcode {barcode}.")
            return redirect("admin:library_checkin")
        try:
            loan = checkin(book=book, user=request.user)
        except CirculationError as exc:
            messages.warning(request, str(exc))
            return redirect("admin:library_checkin")

        late_days = (timezone.localdate() - loan.due_date).days
        shelf = f" Shelf {book.shelf.code}." if book.shelf else ""
        if late_days > 0:
            messages.warning(
                request,
                f"Checked in “{book.title}” from {loan.borrower_name}. "
                f"It was {late_days} day{'s' if late_days != 1 else ''} late.{shelf}",
            )
        else:
            messages.success(
                request, f"Checked in “{book.title}” from {loan.borrower_name}.{shelf}"
            )
        return redirect("admin:library_checkin")

    today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    returned_today = (
        Loan.objects.filter(returned_at__gte=today_start)
        .select_related("book", "book__shelf")
        .order_by("-returned_at")[:15]
    )
    context.update(
        {
            "form": form,
            "returned_today": returned_today,
            "checkout_url": reverse("admin:library_checkout"),
        }
    )
    return render(request, "admin/library/checkin.html", context)
