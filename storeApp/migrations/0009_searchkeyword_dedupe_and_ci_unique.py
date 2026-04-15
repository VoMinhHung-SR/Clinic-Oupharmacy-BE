from django.db import migrations, models
import unicodedata


def dedupe_search_keywords(apps, schema_editor):
    SearchKeyword = apps.get_model("storeApp", "SearchKeyword")
    db_alias = schema_editor.connection.alias

    rows = list(SearchKeyword.objects.using(db_alias).all().order_by("id").values(
        "id", "keyword", "hit_count", "last_searched_at"
    ))

    grouped = {}
    duplicate_ids = []

    for row in rows:
        display_keyword = " ".join(
            unicodedata.normalize("NFKC", (row.get("keyword") or "")).strip().split()
        )
        lookup_keyword = display_keyword.casefold()
        if not lookup_keyword:
            duplicate_ids.append(row["id"])
            continue

        existing = grouped.get(lookup_keyword)
        if not existing:
            grouped[lookup_keyword] = {
                "id": row["id"],
                "keyword": display_keyword,
                "hit_count": row.get("hit_count") or 0,
                "last_searched_at": row.get("last_searched_at"),
            }
            continue

        existing["hit_count"] += row.get("hit_count") or 0
        existing_last = existing.get("last_searched_at")
        current_last = row.get("last_searched_at")
        if (current_last is not None) and (existing_last is None or current_last > existing_last):
            existing["last_searched_at"] = current_last
        duplicate_ids.append(row["id"])

    for data in grouped.values():
        SearchKeyword.objects.using(db_alias).filter(id=data["id"]).update(
            keyword=data["keyword"],
            keyword_lookup=data["keyword"].casefold(),
            hit_count=data["hit_count"],
            last_searched_at=data["last_searched_at"],
        )

    if duplicate_ids:
        SearchKeyword.objects.using(db_alias).filter(id__in=duplicate_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("storeApp", "0008_alter_notification_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="searchkeyword",
            name="keyword_lookup",
            field=models.CharField(
                blank=True,
                db_column="keyword_lookup",
                db_index=True,
                max_length=120,
                null=True,
            ),
        ),
        migrations.RunPython(dedupe_search_keywords, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="searchkeyword",
            name="keyword_lookup",
            field=models.CharField(
                db_column="keyword_lookup",
                db_index=True,
                max_length=120,
                unique=True,
            ),
        ),
    ]
