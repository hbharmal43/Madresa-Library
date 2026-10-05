# Madresa Burhaniyah Dallas – Library

A small Django app for checking library books in and out. One record per
physical book (its barcode sticker), shelf locations, and a loan history that
records who borrowed what and when. The whole UI is the Django admin styled with
[django-unfold](https://unfoldadmin.com/), plus two scanner-friendly pages for
**Check out** and **Check in**.

## What it does

- **Books** – add, edit, search (scan a barcode into the search box), filter by
  status / category / shelf. Change a book's shelf straight from the list.
  "Remove" keeps the record and its history; hard delete is superuser-only.
- **Check out** – scan a barcode, type the borrower's name (phone optional),
  pick 7 / 14 / 21 / 30 days. Refuses books that are already out, lost or removed.
- **Check in** – scan a barcode. Tells you who had it, whether it was late, and
  which shelf it goes back on.
- **Loans** – full history, filter by checked out / overdue / returned, check in
  from the row.
- **Shelves** – A1–A6 … E1–E6 by default (`seed_shelves`), each showing how many
  books it holds.
- **Dashboard** – counts, overdue list, due soon, recent activity.
- **Excel export** – same column layout as the original spreadsheet plus shelf,
  status and borrower.
- **Excel import** – `import_books` loads the spreadsheet and can be re-run safely.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # defaults are fine for local SQLite

python manage.py migrate
python manage.py seed_shelves             # A1..E6
python manage.py import_books data/library_data.xlsx
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ and log in. Give librarians a user with
**Staff status** and the **Librarian** group (created automatically).

### Spreadsheet import notes

The import matches on barcode, so running it again updates titles and authors
but never changes a book's shelf or status. It reports rows it skips. The
current sheet has three such rows: barcode 535489 and 535504 each appear twice
with different titles (the first occurrence is kept), and barcode 535375 has no
title. Fix those in the admin after import.

### Using Postgres locally (optional)

```bash
docker compose up -d db
# in .env:
DATABASE_URL=postgres://library:library@localhost:5432/library
python manage.py migrate
```

## Deploy on EC2 (Ubuntu) with Postgres

1. `sudo apt install python3-venv postgresql nginx`
2. Create the database:
   ```bash
   sudo -u postgres psql -c "CREATE USER library WITH PASSWORD 'choose-a-password';"
   sudo -u postgres psql -c "CREATE DATABASE library OWNER library;"
   ```
3. Clone to `/srv/madresa-library`, create `.venv`, `pip install -r requirements.txt`.
4. Create `.env`:
   ```
   SECRET_KEY=<long random string>
   DEBUG=False
   ALLOWED_HOSTS=your-ec2-hostname-or-domain
   CSRF_TRUSTED_ORIGINS=https://your-domain
   DATABASE_URL=postgres://library:choose-a-password@localhost:5432/library
   ```
5. `python manage.py migrate && python manage.py collectstatic --noinput`
   then `seed_shelves`, `import_books`, `createsuperuser`.
6. Copy `deploy/gunicorn.service` to `/etc/systemd/system/madresa-library.service`
   and `deploy/nginx.conf` to `/etc/nginx/sites-available/madresa-library`
   (symlink into `sites-enabled`). Enable and start both.
7. Add HTTPS with `certbot --nginx` once a domain points at the instance.
8. Put `deploy/backup.sh` in cron for nightly dumps.

## Project layout

```
config/         settings, urls, wsgi
library/
  models.py     Category, Shelf, Book, Loan
  services.py   checkout() / checkin() rules
  admin.py      Unfold admin for every model, row actions, Excel export
  views.py      Check out / Check in pages
  dashboard.py  numbers and lists for the admin home page
  exports.py    Excel writer
  management/commands/  seed_shelves, import_books
  tests.py
templates/admin/        dashboard + checkout/checkin templates
data/library_data.xlsx  the original spreadsheet
deploy/                 gunicorn, nginx, backup script
```

## Tests

```bash
python manage.py test
```
