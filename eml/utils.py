import io
import os

import pandas as pd
from django.core.mail import send_mail, EmailMessage
from django.core.files.base import ContentFile
from io import StringIO

import re

from google.cloud import storage
from google.oauth2 import service_account

from config import settings
from profile_app.models import AppUser
from projects.models import Folder, Project, File
from projects.utils import files_transfer1
from .models import EmailBlock
from eml.models import Message


def check_email(email):
    # block_list = ["rigdong.online", "overdeau.online", "clergent.online", 'mail.ru']
    block_list = EmailBlock.objects.filter(is_active=True).values_list('email', flat=True)
    for block in block_list:
        if re.search(block, email):
            return False
    # if email.split('@')[1] in block_list:
    #     return False
    # if email.rsplit('.', 1)[1] in ['online', ]:
    #     return False
    return True


class EmailMessageUtils:
    def __init__(self, topic, text, email_from, email_to, html='', files=None):
        self.topic = topic
        self.text = text
        self.email_from = email_from
        self.email_to = email_to
        self.html = html
        self.files = files
        self.is_sent = False

    def send(self):
        text = self.text
        if self.html != '':
            text = self.html
        email = EmailMessage(self.topic, text, self.email_from, self.email_to)

        if self.files:
            for f in self.files.all():
                email.attach(f.name, f.file.read())

        if self.html != '':
            email.content_subtype = "html"

        self.is_sent = email.send()

        return self.is_sent


def get_client():
    # Google Storage
    credentials_storage = service_account.Credentials.from_service_account_file(
        filename=os.path.join(settings.BASE_DIR, 'config/credentials.json'),
        scopes=['https://www.googleapis.com/auth/devstorage.full_control'],
    )
    client = storage.Client(credentials=credentials_storage)
    bucket = client.get_bucket('cabinet_bucket')

    return bucket


def create_files(request, ls_folder):
    bucket = get_client()
    files = [blob.name for blob in bucket.list_blobs(prefix='GoogleDriveTransfer/') if not blob.name.endswith('/')]
    files = [x for x in files if x.split('/')[1] in ls_folder]

    # ds_path = {}
    ds_path = set_ds_path(bucket, ls_folder)

    print(f'{ls_folder}  -  files: {len(files)}, ds_path: {len(ds_path)}')

    for file in files:
        try:
            create_file(request, bucket, file, ds_path)
        except Exception as e:
            print(e)

def create_files1(request):
    bucket = get_client()
    # ds_path = set_ds_path(bucket)
    # print(ds_path)


def create_file(request, bucket, path, ds_path):
    ls_path = path.split('/')
    file = ls_path[-1]
    ls_folder = ls_path[1:-1]

    ls_folder_id = ['GoogleDriveTransfer']
    folder_path_current = 'GoogleDriveTransfer'

    user = request.user
    project_id = 36
    project = Project.objects.get(pk=project_id)

    for folder_name in ls_folder:
        folder_path_current += '/' + folder_name
        ls_folder_id_current = ds_path.get(folder_path_current)
        if not ls_folder_id_current:
            if len(ls_folder_id) > 1:
                parent_folder = Folder.objects.get(pk=int(ls_folder_id[-1]))
            else:
                parent_folder = None
            folder = Folder.objects.create(name=folder_name, owner=user, project=project, updated_by=user,
                                           parent_folder=parent_folder, is_public=False)
            ls_folder_id_current = ls_folder_id[:]
            ls_folder_id_current.append(str(folder.pk))
            ds_path[folder_path_current] = ls_folder_id_current

        ls_folder_id = ls_folder_id_current[:]

    path_new = str(project_id) + '/' + '/'.join(ls_folder_id_current[1:]) + '/' + file

    blob = bucket.get_blob(path)
    bucket.rename_blob(blob, path_new)

    parent_folder = Folder.objects.get(pk=int(ls_folder_id[-1]))
    file_old = File.objects.filter(name=file, folder=parent_folder)
    if not file_old:
        file_new = File.objects.create(name=file, file=path_new, owner=user, project=project, updated_by=user,
                                   folder=parent_folder, is_public=False)
    else:
        print('file exist: ', file_old.name, parent_folder.name)


def set_ds_path(bucket, ls_folder):
    ds_path = {}
    ls1 = []

    try:
        # paths_transfer = [blob.name for blob in bucket.list_blobs(prefix='GoogleDriveTransfer/') if not blob.name.endswith('/')]
        # paths_transfer = [x for x in paths_transfer if x.split('/')[1] in ls_folder]
        # paths_transfer = [x.split('/')[1] for x in paths_transfer]
        # paths_transfer = list(set(paths_transfer))


        paths = [blob.name for blob in bucket.list_blobs(prefix='36/') if not blob.name.endswith('/')]
        paths = [x.split('/')[1:-1] for x in paths]


        for path in paths:
            folder = Folder.objects.get(pk=int(path[0]))
            if folder.name in ls_folder:
                if folder.name not in ls1:
                    ls1.append(folder.name)
                ls = ['GoogleDriveTransfer']
                folder_path_current = 'GoogleDriveTransfer'
                for folder_id in path:
                    folder = Folder.objects.get(pk=int(folder_id))
                    ls.append(folder_id)
                    folder_path_current += '/' + folder.name
                    if folder_path_current not in ds_path:
                        ds_path[folder_path_current] = ls[:]
    except Exception as e:
        print(e)

    print(ls1)

    return ds_path


def msg_processing(msg_id, project_to, folder_to, project_id_to, folder_id_to):
    msg = Message.objects.filter(id=msg_id)
    if msg:
        msg = msg.first()
        msg.project = project_to
        msg.folder = folder_to
        msg.save()

        files = msg.files.all()
        if files:
            files_transfer1(files, project_id_to, folder_id_to)
