"""
Circulation rules live here, not in views, so they are easy to test and reuse.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Book, Loan


class CirculationError(Exception):
    """Raised when a checkout or check-in is not allowed."""


def find_book(barcode: str) -> Book | None:
    barcode = (barcode or "").strip()
    if not barcode:
        return None
    return Book.objects.select_related("shelf", "category").filter(barcode=barcode).first()


@transaction.atomic
def checkout(
    *,
    book: Book,
    borrower_name: str,
    borrower_grade: str = "",
    borrower_phone: str = "",
    loan_days: int | None = None,
    user=None,
    notes: str = "",
) -> Loan:
    # Lock the row so two librarians cannot check out the same book at once.
    book = Book.objects.select_for_update().get(pk=book.pk)

    if book.status == Book.Status.CHECKED_OUT:
        current = book.current_loan
        who = f" to {current.borrower_name}" if current else ""
        raise CirculationError(f"{book.title} is already checked out{who}.")
    if book.status == Book.Status.LOST:
        raise CirculationError(f"{book.title} is marked as lost. Mark it available first.")
    if book.status == Book.Status.REMOVED:
        raise CirculationError(f"{book.title} has been removed from the library.")

    borrower_name = (borrower_name or "").strip()
    if not borrower_name:
        raise CirculationError("Borrower name is required.")

    loan_days = loan_days or settings.LIBRARY_DEFAULT_LOAN_DAYS
    now = timezone.now()
    loan = Loan.objects.create(
        book=book,
        borrower_name=borrower_name,
        borrower_grade=(borrower_grade or "").strip(),
        borrower_phone=(borrower_phone or "").strip(),
        checked_out_at=now,
        due_date=timezone.localdate(now) + timedelta(days=loan_days),
        checked_out_by=user if getattr(user, "is_authenticated", False) else None,
        notes=notes or "",
    )
    book.status = Book.Status.CHECKED_OUT
    book.save(update_fields=["status", "updated_at"])
    return loan


@transaction.atomic
def checkin(*, book: Book, user=None, notes: str = "") -> Loan:
    book = Book.objects.select_for_update().get(pk=book.pk)
    loan = Loan.objects.filter(book=book, returned_at__isnull=True).first()

    if loan is None:
        if book.status == Book.Status.CHECKED_OUT:
            # Data got out of sync somehow; heal it rather than block the librarian.
            book.status = Book.Status.AVAILABLE
            book.save(update_fields=["status", "updated_at"])
        raise CirculationError(f"{book.title} is not checked out.")

    loan.returned_at = timezone.now()
    loan.checked_in_by = user if getattr(user, "is_authenticated", False) else None
    if notes:
        loan.notes = f"{loan.notes}\n{notes}".strip()
    loan.save(update_fields=["returned_at", "checked_in_by", "notes"])

    if book.status != Book.Status.REMOVED:
        book.status = Book.Status.AVAILABLE
        book.save(update_fields=["status", "updated_at"])
    return loan
