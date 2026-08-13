# Generated manually for P9 / D-21–D-22 (slot taxonomy + carousel-ready values).

from django.db import migrations, models


SLOT_RENAMES = (
    ("HOME_PROMO_LEFT", "HOME_SECONDARY"),
    ("HOME_STRIP", "HOME_NOTICE_TOP"),
    ("HOME_PROMO_RIGHT", "HOME_NOTICE_BOTTOM"),
)


def rename_placement_slots(apps, schema_editor):
    CampaignPlacement = apps.get_model("storeApp", "CampaignPlacement")
    db = schema_editor.connection.alias
    for old, new in SLOT_RENAMES:
        CampaignPlacement.objects.using(db).filter(slot=old).update(slot=new)


def revert_placement_slots(apps, schema_editor):
    CampaignPlacement = apps.get_model("storeApp", "CampaignPlacement")
    db = schema_editor.connection.alias
    for old, new in SLOT_RENAMES:
        CampaignPlacement.objects.using(db).filter(slot=new).update(slot=old)


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0016_order_campaign_id"),
    ]

    operations = [
        migrations.RunPython(rename_placement_slots, revert_placement_slots),
        migrations.AlterField(
            model_name="campaignplacement",
            name="slot",
            field=models.CharField(
                choices=[
                    ("HOME_HERO", "Banner chính (Hero)"),
                    ("HOME_SECONDARY", "Banner phụ (Secondary)"),
                    ("HOME_NOTICE_TOP", "Thông báo phải — trên"),
                    ("HOME_NOTICE_BOTTOM", "Thông báo phải — dưới"),
                    ("CATEGORY_BANNER", "Category banner"),
                    ("SEARCH_BANNER", "Search banner"),
                ],
                db_column="slot",
                db_index=True,
                max_length=40,
            ),
        ),
    ]
