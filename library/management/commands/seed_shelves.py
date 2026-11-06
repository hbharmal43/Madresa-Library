from django.core.management.base import BaseCommand

from library.models import Shelf


class Command(BaseCommand):
    help = "Create shelf codes like A1..A6, B1..B6 ... (default sections A-E, 6 rows each). Safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument("--sections", default="ABCDE", help="Bookcase letters, e.g. ABCDE")
        parser.add_argument("--rows", type=int, default=6, help="Shelves per bookcase")

    def handle(self, *args, **options):
        created = 0
        for letter in options["sections"].upper():
            for row in range(1, options["rows"] + 1):
                _, was_created = Shelf.objects.get_or_create(code=f"{letter}{row}")
                created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Shelves ready. {created} new, {Shelf.objects.count()} total."))
