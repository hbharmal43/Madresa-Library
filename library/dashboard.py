"""Context for the admin index page (configured via UNFOLD["DASHBOARD_CALLBACK"])."""

from django.urls import reverse
from django.utils import timezone

from .models import Book, Loan


def dashboard_callback(request, context: dict) -> dict:
    today = timezone.localdate()
    books = Book.objects.active()
    open_loans = Loan.objects.open().select_related("book", "book__shelf")

    overdue = open_loans.filter(due_date__lt=today).order_by("due_date")
    due_soon = open_loans.filter(due_date__gte=today).order_by("due_date")[:10]
    recent = Loan.objects.select_related("book").order_by("-checked_out_at")[:10]

    loan_list = reverse("admin:library_loan_changelist")
    book_list = reverse("admin:library_book_changelist")

    context.update(
        {
            "title": "Dashboard",
            "stats": [
                {
                    "title": "Books in library",
                    "value": books.count(),
                    "link": book_list,
                },
                {
                    "title": "Available",
                    "value": books.available().count(),
                    "link": f"{book_list}?status__exact=available",
                },
                {
                    "title": "Checked out",
                    "value": open_loans.count(),
                    "link": f"{loan_list}?state=open",
                },
                {
                    "title": "Overdue",
                    "value": overdue.count(),
                    "link": f"{loan_list}?state=overdue",
                    "danger": True,
                },
            ],
            "overdue_loans": overdue[:15],
            "due_soon": due_soon,
            "recent_loans": recent,
            "today": today,
            "checkout_url": reverse("admin:library_checkout"),
            "checkin_url": reverse("admin:library_checkin"),
        }
    )
    return context
