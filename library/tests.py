from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Book, Category, Loan, Shelf
from .services import CirculationError, checkin, checkout

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "library_data.xlsx"


def make_book(barcode="535520", title="Je nama te rab ne gama", **kwargs):
    return Book.objects.create(barcode=barcode, title=title, **kwargs)


class ShelfTests(TestCase):
    def test_code_is_normalised_and_split(self):
        shelf = Shelf.objects.create(code=" b12 ")
        self.assertEqual(shelf.code, "B12")
        self.assertEqual(shelf.section, "B")
        self.assertEqual(shelf.position, 12)

    def test_seed_shelves_is_idempotent(self):
        call_command("seed_shelves", verbosity=0)
        call_command("seed_shelves", verbosity=0)
        self.assertEqual(Shelf.objects.count(), 30)
        self.assertEqual(list(Shelf.objects.values_list("code", flat=True))[:7], ["A1", "A2", "A3", "A4", "A5", "A6", "B1"])


class CirculationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("lib", password="x")
        self.book = make_book()

    def test_checkout_creates_open_loan_and_marks_book(self):
        loan = checkout(book=self.book, borrower_name="  Ali  ", loan_days=7, user=self.user)
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.CHECKED_OUT)
        self.assertEqual(loan.borrower_name, "Ali")
        self.assertEqual(loan.due_date, timezone.localdate() + timedelta(days=7))
        self.assertEqual(loan.checked_out_by, self.user)
        self.assertIsNone(loan.returned_at)

    def test_cannot_checkout_twice(self):
        checkout(book=self.book, borrower_name="Ali")
        with self.assertRaises(CirculationError):
            checkout(book=self.book, borrower_name="Fatema")
        self.assertEqual(Loan.objects.count(), 1)

    def test_cannot_checkout_removed_or_lost(self):
        for status in (Book.Status.REMOVED, Book.Status.LOST):
            self.book.status = status
            self.book.save()
            with self.assertRaises(CirculationError):
                checkout(book=self.book, borrower_name="Ali")

    def test_borrower_name_required(self):
        with self.assertRaises(CirculationError):
            checkout(book=self.book, borrower_name="   ")

    def test_checkin_closes_loan(self):
        checkout(book=self.book, borrower_name="Ali")
        loan = checkin(book=self.book, user=self.user)
        self.book.refresh_from_db()
        self.assertIsNotNone(loan.returned_at)
        self.assertEqual(loan.checked_in_by, self.user)
        self.assertEqual(self.book.status, Book.Status.AVAILABLE)

    def test_checkin_when_not_out_raises(self):
        with self.assertRaises(CirculationError):
            checkin(book=self.book)

    def test_overdue_queryset(self):
        loan = checkout(book=self.book, borrower_name="Ali")
        self.assertEqual(Loan.objects.overdue().count(), 0)
        loan.due_date = timezone.localdate() - timedelta(days=3)
        loan.save()
        self.assertEqual(Loan.objects.overdue().count(), 1)
        self.assertEqual(loan.days_overdue, 3)


class ImportCommandTests(TestCase):
    def test_import_real_spreadsheet_twice_has_no_duplicates(self):
        call_command("import_books", str(DATA_FILE), verbosity=0)
        first = Book.objects.count()
        self.assertEqual(first, 206)  # 209 rows minus 2 duplicate barcodes and 1 row with no title
        call_command("import_books", str(DATA_FILE), verbosity=0)
        self.assertEqual(Book.objects.count(), first)
        self.assertTrue(Category.objects.filter(name="Hiqayat").exists())
        book = Book.objects.get(barcode="535520")
        self.assertEqual(book.title, "Je nama te rab ne gama")
        self.assertEqual(book.publication, "Attalim North America")

    def test_reimport_keeps_shelf_and_status(self):
        call_command("import_books", str(DATA_FILE), verbosity=0)
        shelf = Shelf.objects.create(code="A1")
        book = Book.objects.get(barcode="535520")
        book.shelf = shelf
        book.save()
        checkout(book=book, borrower_name="Ali")
        call_command("import_books", str(DATA_FILE), verbosity=0)
        book.refresh_from_db()
        self.assertEqual(book.shelf, shelf)
        self.assertEqual(book.status, Book.Status.CHECKED_OUT)

    def test_dry_run_saves_nothing(self):
        call_command("import_books", str(DATA_FILE), "--dry-run", verbosity=0)
        self.assertEqual(Book.objects.count(), 0)


class AdminPagesTests(TestCase):
    def setUp(self):
        self.librarian = User.objects.create_user("lib", password="x", is_staff=True)
        self.librarian.groups.add(Group.objects.get(name="Librarian"))
        self.client.force_login(self.librarian)
        self.shelf = Shelf.objects.create(code="A1")
        self.book = make_book(shelf=self.shelf)

    def test_dashboard_renders(self):
        checkout(book=self.book, borrower_name="Ali")
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Overdue")
        self.assertContains(response, "Ali")

    def test_checkout_flow(self):
        url = reverse("admin:library_checkout")
        # Step 1: scan
        response = self.client.get(url, {"barcode": "535520"})
        self.assertContains(response, "Who is borrowing")
        self.assertContains(response, self.book.title)
        # Step 2: borrower details
        response = self.client.post(
            url,
            {"barcode": "535520", "borrower_name": "Ali", "borrower_grade": "4", "borrower_phone": "", "loan_days": 7},
            follow=True,
        )
        self.assertContains(response, "Checked out")
        self.assertContains(response, "Rabea (4)")
        loan = Loan.objects.get()
        self.assertEqual(loan.borrower_name, "Ali")
        self.assertEqual(loan.borrower_grade, "4")
        self.assertEqual(loan.due_date, timezone.localdate() + timedelta(days=7))
        # Scanning it again warns instead of showing the form
        response = self.client.get(url, {"barcode": "535520"}, follow=True)
        self.assertContains(response, "already checked out to Ali")

    def test_checkout_without_grade_is_allowed(self):
        response = self.client.post(
            reverse("admin:library_checkout"),
            {"barcode": "535520", "borrower_name": "Teacher Sb", "borrower_grade": "", "borrower_phone": "", "loan_days": 14},
            follow=True,
        )
        self.assertContains(response, "Checked out")
        self.assertEqual(Loan.objects.get().borrower_grade, "")

    def test_checkout_rejects_unknown_grade(self):
        response = self.client.post(
            reverse("admin:library_checkout"),
            {"barcode": "535520", "borrower_name": "Ali", "borrower_grade": "12", "borrower_phone": "", "loan_days": 14},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Loan.objects.count(), 0)

    def test_loan_list_filters_by_grade(self):
        checkout(book=self.book, borrower_name="Ali", borrower_grade="4")
        other = make_book(barcode="2", title="Other")
        checkout(book=other, borrower_name="Zahra", borrower_grade="9")
        response = self.client.get(reverse("admin:library_loan_changelist"), {"borrower_grade__exact": "9"})
        self.assertContains(response, "Zahra")
        self.assertNotContains(response, "Ali")

    def test_checkout_unknown_barcode(self):
        response = self.client.get(reverse("admin:library_checkout"), {"barcode": "000"}, follow=True)
        self.assertContains(response, "No book with barcode 000")

    def test_checkin_flow(self):
        checkout(book=self.book, borrower_name="Ali")
        response = self.client.post(reverse("admin:library_checkin"), {"barcode": "535520"}, follow=True)
        self.assertContains(response, "Checked in")
        self.assertContains(response, "Shelf A1")
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.AVAILABLE)

    def test_checkin_late_message(self):
        loan = checkout(book=self.book, borrower_name="Ali")
        loan.due_date = timezone.localdate() - timedelta(days=2)
        loan.save()
        response = self.client.post(reverse("admin:library_checkin"), {"barcode": "535520"}, follow=True)
        self.assertContains(response, "2 days late")

    def test_book_changelist_and_export(self):
        checkout(book=self.book, borrower_name="Ali")
        response = self.client.get(reverse("admin:library_book_changelist"))
        self.assertContains(response, "Ali")
        response = self.client.get(reverse("admin:library_book_export_all_xlsx"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])

    def test_loan_changelist_and_row_checkin(self):
        loan = checkout(book=self.book, borrower_name="Ali")
        response = self.client.get(reverse("admin:library_loan_changelist"), {"state": "open"})
        self.assertContains(response, "Ali")
        response = self.client.get(reverse("admin:library_loan_row_checkin", args=[loan.pk]), follow=True)
        self.assertContains(response, "Checked in")
        loan.refresh_from_db()
        self.assertIsNotNone(loan.returned_at)

    def test_remove_action_skips_checked_out(self):
        other = make_book(barcode="1", title="Other")
        checkout(book=self.book, borrower_name="Ali")
        self.client.post(
            reverse("admin:library_book_changelist"),
            {"action": "mark_removed", "_selected_action": [self.book.pk, other.pk]},
            follow=True,
        )
        self.book.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.book.status, Book.Status.CHECKED_OUT)
        self.assertEqual(other.status, Book.Status.REMOVED)

    def test_librarian_cannot_hard_delete(self):
        response = self.client.get(reverse("admin:library_book_delete", args=[self.book.pk]))
        self.assertEqual(response.status_code, 403)

    def test_add_book_via_admin(self):
        response = self.client.post(
            reverse("admin:library_book_add"),
            {
                "barcode": "999",
                "title": "New book",
                "author": "",
                "publication": "",
                "category": "",
                "shelf": self.shelf.pk,
                "status": "available",
                "notes": "",
                "loans-TOTAL_FORMS": 0,
                "loans-INITIAL_FORMS": 0,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Book.objects.filter(barcode="999").exists())
