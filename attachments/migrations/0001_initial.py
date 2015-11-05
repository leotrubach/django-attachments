# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import attachments.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attachment',
            fields=[
                ('id', models.AutoField(primary_key=True, auto_created=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('attachment_file', models.FileField(verbose_name='attachment', upload_to=attachments.models.Attachment.attachment_upload)),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='created')),
                ('modified', models.DateTimeField(verbose_name='modified', auto_now=True)),
                ('content_type', models.ForeignKey(to='contenttypes.ContentType')),
                ('creator', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='created_attachments', verbose_name='creator')),
            ],
            options={
                'permissions': (('delete_foreign_attachments', 'Can delete foreign attachments'),),
                'ordering': ['-created'],
            },
        ),
    ]
