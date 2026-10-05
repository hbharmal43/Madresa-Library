"""
Data model for the library.

One ``Book`` row is one physical book with its own barcode sticker, exactly
like one row in the original spreadsheet. The same title can therefore appear
several times with different barcodes.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Shelf(models.Model):
    """
    A physical shelf. ``code`` is what gets printed on the shelf label
    (A1, A2 ... E6). ``section`` is the bookcase letter, kept separately so the
    shelf list can be grouped and sorted naturally.
    """

    code = models.CharField(
        max_length=10,
        unique=True,
        validators=[RegexValidator(r"^[A-Z]{1,3}\d{1,3}$", "Use a format like A1 or B12.")],
        help_text="Printed label for this shelf, e.g. A1.",
    )
    section = models.CharField(
        max_length=3,
        editable=False,
        db_index=True,
        help_text="Bookcase letter, derived from the code.",
    )
    position = models.PositiveSmallIntegerField(
        editable=False,
        help_text="Row number within the bookcase, derived from the code.",
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional note, e.g. 'Children's books, bottom row'.",
    )

    class Meta:
        ordering = ["section", "position"]
        verbose_name_plural = "shelves"

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        letters = "".join(ch for ch in self.code if ch.isalpha())
        digits = "".join(ch for ch in self.code if ch.isdigit())
        self.section = letters
        self.position = int(digits) if digits else 0
        super().save(*args, **kwargs)


class BookQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(status=Book.Status.REMOVED)

    def available(self):
        return self.filter(status=Book.Status.AVAILABLE)

    def checked_out(self):
        return self.filter(status=Book.Status.CHECKED_OUT)


class Book(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        CHECKED_OUT = "checked_out", "Checked out"
        LOST = "lost", "Lost"
        REMOVED = "removed", "Removed"

    barcode = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Number printed on the barcode sticker. Scan it or type it.",
    )
    title = models.CharField("name of the book", max_length=255)
    author = models.CharField(max_length=255, blank=True)
    publication = models.CharField(max_length=255, blank=True)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="books"
    )
    shelf = models.ForeignKey(
        Shelf, null=True, blank=True, on_delete=models.SET_NULL, related_name="books"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )
    notes = models.TextField(blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BookQuerySet.as_manager()

    class Meta:
        ordering = ["title", "barcode"]

    def __str__(self) -> str:
        return f"{self.title} [{self.barcode}]"

    def clean(self):
        self.barcode = (self.barcode or "").strip()
        self.title = (self.title or "").strip()

    @property
    def is_available(self) -> bool:
        return self.status == self.Status.AVAILABLE

    @property
    def current_loan(self):
        """The open loan for this book, or None."""
        return self.loans.filter(returned_at__isnull=True).select_related("checked_out_by").first()


class LoanQuerySet(models.QuerySet):
    def open(self):
        return self.filter(returned_at__isnull=True)

    def returned(self):
        return self.filter(returned_at__isnull=False)

    def overdue(self):
        return self.open().filter(due_date__lt=timezone.localdate())


class Loan(models.Model):
    """
    One checkout. ``returned_at`` is null while the book is out.
    There can be at most one open loan per book (enforced by a DB constraint).
    """

    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="loans")
    borrower_name = models.CharField(max_length=150)
    borrower_phone = models.CharField(max_length=30, blank=True)
    checked_out_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(db_index=True)
    returned_at = models.DateTimeField(null=True, blank=True, db_index=True)
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checkouts",
    )
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checkins",
    )
    notes = models.TextField(blank=True)

    objects = LoanQuerySet.as_manager()

    class Meta:
        ordering = ["-checked_out_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["book"],
                condition=Q(returned_at__isnull=True),
                name="one_open_loan_per_book",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.book} -> {self.borrower_name}"

    @property
    def is_open(self) -> bool:
        return self.returned_at is None

    @property
    def is_overdue(self) -> bool:
        return self.is_open and self.due_date < timezone.localdate()

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.due_date).days
