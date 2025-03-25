# Generated by Django 4.0.3 on 2025-03-25 16:38

import cloudinary.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('email', models.EmailField(db_index=True, max_length=100, unique=True)),
                ('avatar', cloudinary.models.CloudinaryField(blank=True, default='', max_length=255, null=True, verbose_name='avatar')),
                ('phone_number', models.CharField(blank=True, max_length=20)),
                ('date_of_birth', models.DateTimeField(null=True)),
                ('gender', models.PositiveIntegerField(choices=[(0, 'Male'), (1, 'Female'), (2, 'Secret')], default=0)),
                ('title', models.CharField(blank=True, default='', max_length=20)),
                ('is_admin', models.BooleanField(default=False)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('name', models.CharField(max_length=254, unique=True)),
            ],
            options={
                'verbose_name_plural': 'Categories',
            },
        ),
        migrations.CreateModel(
            name='CommonCity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name='CommonDistrict',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=50)),
                ('city', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mainApp.commoncity')),
            ],
        ),
        migrations.CreateModel(
            name='Diagnosis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('sign', models.CharField(max_length=254)),
                ('diagnosed', models.CharField(max_length=254)),
            ],
            options={
                'verbose_name_plural': 'Diagnosis',
            },
        ),
        migrations.CreateModel(
            name='DoctorSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('session', models.CharField(choices=[('morning', 'morning'), ('afternoon', 'afternoon')], max_length=10)),
                ('is_off', models.BooleanField(default=False)),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Medicine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('name', models.CharField(max_length=254, unique=True)),
                ('effect', models.CharField(blank=True, max_length=254, null=True)),
                ('contraindications', models.CharField(blank=True, max_length=254, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='MedicineUnit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('price', models.FloatField()),
                ('in_stock', models.IntegerField()),
                ('image', cloudinary.models.CloudinaryField(default='', max_length=255, null=True, verbose_name='medicineImage')),
                ('packaging', models.CharField(max_length=50, null=True)),
                ('category', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.category')),
                ('medicine', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mainApp.medicine')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Prescribing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('diagnosis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mainApp.diagnosis')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('active', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='TimeSlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('is_available', models.BooleanField(default=True)),
                ('schedule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mainApp.doctorschedule')),
            ],
        ),
        migrations.CreateModel(
            name='PrescriptionDetail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('quantity', models.IntegerField()),
                ('uses', models.CharField(max_length=100)),
                ('medicine_unit', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.medicineunit')),
                ('prescribing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='mainApp.prescribing')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Patient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('first_name', models.CharField(blank=True, max_length=150)),
                ('last_name', models.CharField(blank=True, max_length=150)),
                ('phone_number', models.CharField(max_length=20)),
                ('email', models.CharField(max_length=254, unique=True)),
                ('gender', models.PositiveIntegerField(choices=[(0, 'Male'), (1, 'Female'), (2, 'Secret')], default=0)),
                ('date_of_birth', models.DateTimeField(null=True)),
                ('address', models.CharField(max_length=255, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Examination',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('wage', models.FloatField(default=20000)),
                ('mail_status', models.BooleanField(default=False, null=True)),
                ('reminder_email', models.BooleanField(default=False, null=True)),
                ('description', models.CharField(max_length=254)),
                ('patient', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='mainApp.patient')),
                ('time_slot', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.timeslot')),
                ('user', models.ForeignKey(blank=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-id'],
            },
        ),
        migrations.CreateModel(
            name='DoctorAvailability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField()),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='diagnosis',
            name='examination',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='mainApp.examination'),
        ),
        migrations.AddField(
            model_name='diagnosis',
            name='patient',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.patient'),
        ),
        migrations.AddField(
            model_name='diagnosis',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='CommonLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('address', models.CharField(max_length=255)),
                ('lat', models.FloatField()),
                ('lng', models.FloatField()),
                ('city', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.commoncity')),
                ('district', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.commondistrict')),
            ],
        ),
        migrations.CreateModel(
            name='Bill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('updated_date', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('amount', models.FloatField()),
                ('prescribing', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.prescribing')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='user',
            name='location',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.commonlocation'),
        ),
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mainApp.userrole'),
        ),
        migrations.AddField(
            model_name='user',
            name='user_permissions',
            field=models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions'),
        ),
    ]
