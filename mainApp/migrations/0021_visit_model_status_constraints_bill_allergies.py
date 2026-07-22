# S2 visit model: optional description + status + cardinality + bill + allergies.
# Order: alter/add fields → backfill status → cleanup dups → constraints → bill paid → allergies.

from django.db import migrations, models


def backfill_examination_status(apps, schema_editor):
    Examination = apps.get_model("mainApp", "Examination")
    Examination.objects.filter(mail_status=True).update(status="confirmed")
    Examination.objects.exclude(mail_status=True).update(status="pending")


def cleanup_duplicate_active(apps, schema_editor):
    Diagnosis = apps.get_model("mainApp", "Diagnosis")
    Prescribing = apps.get_model("mainApp", "Prescribing")

    seen_exam = set()
    for d in Diagnosis.objects.filter(active=True).order_by("-id").iterator():
        eid = d.examination_id
        if eid is None:
            continue
        if eid in seen_exam:
            d.active = False
            d.save(update_fields=["active"])
        else:
            seen_exam.add(eid)

    seen_dx = set()
    for p in Prescribing.objects.filter(active=True).order_by("-id").iterator():
        did = p.diagnosis_id
        if did in seen_dx:
            p.active = False
            p.save(update_fields=["active"])
        else:
            seen_dx.add(did)


def backfill_bill_paid(apps, schema_editor):
    Bill = apps.get_model("mainApp", "Bill")
    for bill in Bill.objects.all().iterator():
        bill.status = "paid"
        if bill.paid_at is None:
            bill.paid_at = bill.created_date
        bill.save(update_fields=["status", "paid_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("mainApp", "0020_timeslot_uniq_timeslot_schedule_start_end"),
    ]

    operations = [
        migrations.AlterField(
            model_name="examination",
            name="description",
            field=models.CharField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="examination",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "pending"),
                    ("confirmed", "confirmed"),
                    ("in_progress", "in_progress"),
                    ("completed", "completed"),
                    ("cancelled", "cancelled"),
                    ("no_show", "no_show"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_examination_status, migrations.RunPython.noop),
        migrations.RunPython(cleanup_duplicate_active, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="diagnosis",
            constraint=models.UniqueConstraint(
                condition=models.Q(active=True),
                fields=("examination",),
                name="uniq_active_diagnosis_per_examination",
            ),
        ),
        migrations.AddConstraint(
            model_name="prescribing",
            constraint=models.UniqueConstraint(
                condition=models.Q(active=True),
                fields=("diagnosis",),
                name="uniq_active_prescribing_per_diagnosis",
            ),
        ),
        migrations.AddField(
            model_name="bill",
            name="status",
            field=models.CharField(
                choices=[
                    ("unpaid", "unpaid"),
                    ("paid", "paid"),
                    ("void", "void"),
                ],
                db_index=True,
                default="unpaid",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="bill",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_bill_paid, migrations.RunPython.noop),
        migrations.AddField(
            model_name="patient",
            name="allergies",
            field=models.TextField(blank=True, default=""),
        ),
    ]
