from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Exists, OuterRef, Q
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    ChoicesDropdownFilter,
    RangeDateFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from . import views
from .exports import books_to_xlsx_response
from .models import Book, Category, Loan, Shelf
from .services import CirculationError, checkin

# ---------------------------------------------------------------------------
# Auth models re-registered so they pick up the Unfold styling
# ---------------------------------------------------------------------------
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("name", "book_count")
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _book_count=Count("books", filter=~Q(books__status=Book.Status.REMOVED))
        )

    @display(description="Books", ordering="_book_count")
    def book_count(self, obj):
        url = reverse("admin:library_book_changelist")
        return format_html('<a href="{}?category__id__exact={}">{}</a>', url, obj.pk, obj._book_count)


@admin.register(Shelf)
class ShelfAdmin(ModelAdmin):
    list_display = ("code", "section", "position", "description", "book_count")
    list_filter = ("section",)
    search_fields = ("code", "description")
    fields = ("code", "description")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _book_count=Count("books", filter=~Q(books__status=Book.Status.REMOVED))
        )

    @display(description="Books on shelf", ordering="_book_count")
    def book_count(self, obj):
        url = reverse("admin:library_book_changelist")
        return format_html('<a href="{}?shelf__id__exact={}">{}</a>', url, obj.pk, obj._book_count)


class LoanInline(TabularInline):
    model = Loan
    extra = 0
    can_delete = False
    fields = ("borrower_name", "borrower_grade", "borrower_phone", "checked_out_at", "due_date", "returned_at", "checked_out_by")
    readonly_fields = fields
    ordering = ("-checked_out_at",)
    verbose_name_plural = "Loan history"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Book)
class BookAdmin(ModelAdmin):
    list_display = ("barcode", "title", "author", "category", "shelf", "status_label", "borrowed_by")
    list_editable = ("shelf",)
    list_filter = (
        ("status", ChoicesDropdownFilter),
        ("category", RelatedDropdownFilter),
        ("shelf", RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = ("barcode", "title", "author", "publication")
    search_help_text = "Scan a barcode or type part of the title or author."
    ordering = ("title", "barcode")
    list_per_page = 50
    readonly_fields = ("added_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("barcode", "title", "author", "publication", "category")}),
        ("Location & status", {"fields": ("shelf", "status", "notes")}),
        ("Record", {"fields": ("added_at", "updated_at"), "classes": ("collapse",)}),
    )
    inlines = (LoanInline,)
    actions = ("export_selected_xlsx", "mark_available", "mark_lost", "mark_removed")
    actions_list = ("export_all_xlsx",)
    actions_row = ("row_checkout", "row_checkin")

    # --- columns -----------------------------------------------------------
    @display(
        description="Status",
        ordering="status",
        label={
            Book.Status.AVAILABLE: "success",
            Book.Status.CHECKED_OUT: "warning",
            Book.Status.LOST: "danger",
            Book.Status.REMOVED: "",
        },
    )
    def status_label(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Borrowed by")
    def borrowed_by(self, obj):
        loan = getattr(obj, "_open_loan", None)
        if loan is None:
            return ""
        overdue = loan.due_date < timezone.localdate()
        style = ' class="text-red-600 font-semibold"' if overdue else ""
        return format_html("<span{}>{}</span> <span class=\"text-xs\">(due {})</span>", style, loan.borrower_name, loan.due_date.strftime("%b %d"))

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("category", "shelf")
        return qs

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        # Attach open loans in one query so the "Borrowed by" column is cheap.
        books = list(cl.result_list)
        loans = Loan.objects.open().filter(book__in=books)
        by_book = {loan.book_id: loan for loan in loans}
        for book in books:
            book._open_loan = by_book.get(book.pk)
        return cl

    # --- permissions ------------------------------------------------------
    def has_delete_permission(self, request, obj=None):
        # Hard delete wipes loan history; keep it for superusers only.
        return request.user.is_superuser

    # --- row actions ------------------------------------------------------
    @action(description="Check out", icon="output", url_path="checkout-row")
    def row_checkout(self, request, object_id):
        book = Book.objects.get(pk=object_id)
        url = reverse("admin:library_checkout")
        return _redirect(f"{url}?barcode={book.barcode}")

    @action(description="Check in", icon="input", url_path="checkin-row")
    def row_checkin(self, request, object_id):
        book = Book.objects.get(pk=object_id)
        try:
            loan = checkin(book=book, user=request.user)
            messages.success(request, f"Checked in “{book.title}” from {loan.borrower_name}.")
        except CirculationError as exc:
            messages.warning(request, str(exc))
        return _redirect(reverse("admin:library_book_changelist"))

    # --- bulk actions -----------------------------------------------------
    @action(description="Export all books to Excel", icon="download", url_path="export-xlsx")
    def export_all_xlsx(self, request):
        return books_to_xlsx_response(Book.objects.all())

    @admin.action(description="Export selected books to Excel")
    def export_selected_xlsx(self, request, queryset):
        return books_to_xlsx_response(queryset, filename="library-selected.xlsx")

    @admin.action(description="Mark selected as available")
    def mark_available(self, request, queryset):
        self._bulk_status(request, queryset, Book.Status.AVAILABLE, "marked available")

    @admin.action(description="Mark selected as lost")
    def mark_lost(self, request, queryset):
        self._bulk_status(request, queryset, Book.Status.LOST, "marked lost")

    @admin.action(description="Remove selected from library")
    def mark_removed(self, request, queryset):
        self._bulk_status(request, queryset, Book.Status.REMOVED, "removed (history is kept)")

    def _bulk_status(self, request, queryset, status, verb):
        """Change status for selected books, never touching books that are still out."""
        has_open_loan = Exists(Loan.objects.filter(book=OuterRef("pk"), returned_at__isnull=True))
        queryset = queryset.annotate(_out=has_open_loan)
        blocked = queryset.filter(_out=True).count()
        updated = Book.objects.filter(pk__in=queryset.filter(_out=False).values("pk")).update(status=status)
        messages.success(request, f"{updated} book(s) {verb}.")
        if blocked:
            messages.warning(request, f"{blocked} book(s) skipped because they are checked out. Check them in first.")


# ---------------------------------------------------------------------------
# Circulation
# ---------------------------------------------------------------------------
class LoanStateFilter(admin.SimpleListFilter):
    title = "state"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return (("open", "Checked out"), ("overdue", "Overdue"), ("returned", "Returned"))

    def queryset(self, request, queryset):
        if self.value() == "open":
            return queryset.open()
        if self.value() == "overdue":
            return queryset.overdue()
        if self.value() == "returned":
            return queryset.returned()
        return queryset


@admin.register(Loan)
class LoanAdmin(ModelAdmin):
    list_display = ("book_link", "barcode", "borrower_name", "borrower_grade", "borrower_phone", "checked_out_at", "due_date", "state_label", "returned_at")
    list_filter = (LoanStateFilter, ("borrower_grade", ChoicesDropdownFilter), ("due_date", RangeDateFilter), ("checked_out_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("borrower_name", "borrower_phone", "book__barcode", "book__title")
    date_hierarchy = "checked_out_at"
    ordering = ("-checked_out_at",)
    list_per_page = 50
    autocomplete_fields = ("book",)
    readonly_fields = ("book", "checked_out_at", "returned_at", "checked_out_by", "checked_in_by")
    fields = ("book", "borrower_name", "borrower_grade", "borrower_phone", "checked_out_at", "due_date", "returned_at", "checked_out_by", "checked_in_by", "notes")
    actions_row = ("row_checkin",)
    actions_detail = ("detail_checkin",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("book", "checked_out_by")

    def has_add_permission(self, request):
        # Loans are created from the Check out page so the book status stays in sync.
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @display(description="Book", ordering="book__title")
    def book_link(self, obj):
        url = reverse("admin:library_book_change", args=[obj.book_id])
        return format_html('<a href="{}">{}</a>', url, obj.book.title)

    @display(description="Barcode", ordering="book__barcode")
    def barcode(self, obj):
        return obj.book.barcode

    @display(description="State", label={"Overdue": "danger", "Out": "warning", "Returned": "success"})
    def state_label(self, obj):
        if obj.returned_at:
            return "Returned"
        if obj.is_overdue:
            return "Overdue"
        return "Out"

    @action(description="Check in", icon="input", url_path="checkin-row")
    def row_checkin(self, request, object_id):
        loan = Loan.objects.select_related("book").get(pk=object_id)
        self._do_checkin(request, loan)
        return _redirect(reverse("admin:library_loan_changelist"))

    @action(description="Check in", icon="input", url_path="checkin", variant=ActionVariant.PRIMARY)
    def detail_checkin(self, request, object_id):
        loan = Loan.objects.select_related("book").get(pk=object_id)
        self._do_checkin(request, loan)
        return _redirect(reverse("admin:library_loan_change", args=[object_id]))

    def _do_checkin(self, request, loan):
        if loan.returned_at:
            messages.info(request, "This loan was already returned.")
            return
        try:
            checkin(book=loan.book, user=request.user)
            messages.success(request, f"Checked in “{loan.book.title}” from {loan.borrower_name}.")
        except CirculationError as exc:
            messages.warning(request, str(exc))

    # Custom pages hang off the Loan admin so they get admin auth + context.
    def get_urls(self):
        custom = [
            path("checkout/", self.admin_site.admin_view(views.checkout_view), name="library_checkout"),
            path("checkin/", self.admin_site.admin_view(views.checkin_view), name="library_checkin"),
        ]
        return custom + super().get_urls()


def _redirect(url):
    from django.http import HttpResponseRedirect

    return HttpResponseRedirect(url)
