"""Create a 'Librarian' group with the day-to-day permissions."""

from django.db import migrations

LIBRARIAN_PERMS = [
    ("library", "book", ["add", "change", "view"]),
    ("library", "loan", ["add", "change", "view"]),
    ("library", "shelf", ["add", "change", "view"]),
    ("library", "category", ["add", "change", "view"]),
]


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group, _ = Group.objects.get_or_create(name="Librarian")
    for app_label, model, actions in LIBRARIAN_PERMS:
        ct, _ = ContentType.objects.get_or_create(app_label=app_label, model=model)
        for action in actions:
            perm, _ = Permission.objects.get_or_create(
                content_type=ct,
                codename=f"{action}_{model}",
                defaults={"name": f"Can {action} {model}"},
            )
            group.permissions.add(perm)


def remove_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name="Librarian").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_group, remove_group)]
