import mimetypes
import os
import zipfile
from datetime import time
from wsgiref.util import FileWrapper
from django.core.files.storage import default_storage
from io import BytesIO

from django.conf import settings
from hashlib import md5

from django.http import HttpResponse, StreamingHttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.utils.http import urlquote
from google.cloud import storage
from google.oauth2 import service_account
# from projects.models import File, Project, Folder


def pack_files(archive_name, file_path_list, default_path):
    from projects.models import Project

    has_dirs = False
    project_names = {}
    if file_path_list and os.path.split(os.path.relpath(file_path_list[0], default_path))[0]:
        has_dirs = True

        for path in file_path_list:
            proj_dir = os.path.split(os.path.relpath(path, default_path))[0]
            if not project_names.get(proj_dir):
                project_names[proj_dir] = Project.objects.get(id=int(proj_dir)).name

    with zipfile.ZipFile(archive_name, 'w') as zip:
        for file in file_path_list:
            filename = os.path.relpath(file, default_path)
            if has_dirs:
                proj_dir = os.path.split(os.path.relpath(file, default_path))[0]
                new_file_name = filename.replace(proj_dir, project_names.get(proj_dir), 1)
            else:
                new_file_name = filename

            zip.write(file,
                      new_file_name,
                      compress_type=zipfile.ZIP_DEFLATED)
    return


def pack_gcp_files(archive_name, urls_list, parent):
    from projects.models import Project

    # has_dirs = False
    # project_names = {}
    # if urls_list and os.path.split(os.path.relpath(urls_list[0], default_url))[0]:
    #     has_dirs = True
    #
    #     for url in urls_list:
    #         proj_dir = os.path.dirname(os.path.relpath(url, settings.MEDIA_URL)).split(os.sep)[0]
    #         # proj_dir = os.path.split(os.path.relpath(url, default_url))[0]
    #         if not project_names.get(proj_dir):
    #             project_names[proj_dir] = Project.objects.get(id=int(proj_dir)).name

    with zipfile.ZipFile(archive_name, 'w') as zip:
        for file in urls_list:
            # filename = os.path.relpath(file[0], default_url)
            # if has_dirs:
            #     # proj_dir = os.path.split(os.path.relpath(file, default_url))[0]
            #     proj_dir = os.path.dirname(os.path.relpath(file, settings.MEDIA_URL)).split(os.sep)[0]
            #     new_file_name = filename.replace(proj_dir, project_names.get(proj_dir), 1)
            # else:
            #     new_file_name = filename

            pack_file = zipfile.ZipInfo()
            pack_file.filename = os.path.relpath(file[1], parent) if parent else file[1]
            if file[1].replace(os.sep, '') == parent:
                pack_file.filename = 'empty_folder'
                # TODO: do something with empty folders

            pack_file.compress_type = zipfile.ZIP_DEFLATED
            if file[0][-1] != os.sep:
                pack_file.date_time = file[-1].timetuple()[:6]
                filedata = default_storage.open(os.path.relpath(file[0], settings.MEDIA_URL), "rb").read()
            else:
                if pack_file.filename[-1] != os.sep:
                    pack_file.filename += os.sep
                filedata = ''

            zip.writestr(pack_file, filedata)

    return


def get_project_files(project_id, files_path_list=None):
    if files_path_list is None:
        files_path_list = []
    from .models import Project
    proj = Project.objects.filter(pk=project_id)

    if proj.exists():
        proj = proj.get()

    for file in proj.files.all():
        files_path_list.append(file.file.path)

    return files_path_list


def get_project_urls(project_id, urls=None):
    if urls is None:
        urls = []
    from .models import Project
    proj = Project.objects.filter(pk=project_id)

    if proj.exists():
        proj = proj.get()

    if proj.is_empty:
        urls.append((str(project_id) + os.sep, proj.name + os.sep))

    else:
        for file in proj.files.all():
            urls.append((file.get_norm_url(), file.get_norm_path(), file.updated_at))

        for folder in proj.folders.all():
            if folder.is_empty:
                urls.append((folder.get_full_path() + os.sep, folder.get_norm_path() + os.sep), folder.updated_at)

    return urls


def get_folder_urls(folder_id, urls=None):
    if urls is None:
        urls = []

    from projects.models import Folder
    folder = Folder.objects.filter(pk=folder_id)

    if folder.exists():
        folder = folder.get()

    if folder.is_empty:
        urls.append((folder.get_full_path() + os.sep, folder.get_norm_path() + os.sep))
    else:
        for file in folder.files.all():
            urls.append((file.get_norm_url(), file.get_norm_path(), file.updated_at))

        for folder in folder.folders.all():
            if folder.is_empty:
                urls.append((folder.get_full_path() + os.sep, folder.get_norm_path() + os.sep), folder.updated_at)
            else:
                get_folder_urls(folder.id, urls)

    return urls


def get_file_response(file_path, filename):
    chunk_size = 8192
    response = StreamingHttpResponse(FileWrapper(open(file_path, 'rb'), chunk_size),
                                     content_type=mimetypes.guess_type(file_path)[0])
    response['Content-Length'] = os.path.getsize(file_path)
    response['Content-Disposition'] = f"attachment; filename={urlquote(filename)}"
    return response


def get_archive_response(file_path, default_path, file_name):
    response = HttpResponse(content_type='application/zip')
    pack_files(response, file_path, default_path)
    response['Content-Disposition'] = f'attachment; filename={urlquote(file_name)}'
    return response


def get_gcp_file_response(file):
    # chunk_size = 8192
    chunk_size = settings.GS_BLOB_CHUNK_SIZE
    blob = file.file.storage.bucket.blob(file.file.name)

    f_size = file.file.size
    byte_list = [i * chunk_size if i * chunk_size < f_size else f_size for i in range(f_size // chunk_size + 2)]
    blob_bytes_gen = (blob.download_as_bytes(start=byte_list[i], end=byte_list[i + 1]) for i in
                      range(len(byte_list) - 1))

    response = StreamingHttpResponse(blob_bytes_gen,
                                     content_type=mimetypes.guess_type(file.file.url)[0])
    # response = HttpResponse(content_type=mimetypes.guess_type(file.file.url)[0])
    # response = StreamingHttpResponse(file.file.chunks(chunk_size=chunk_size),
    #                                  content_type=mimetypes.guess_type(file.file.url)[0])

    # blob.download_to_filename(response)
    response['Content-Length'] = f_size
    response['Content-Disposition'] = f"attachment; filename={urlquote(file.name)}"

    return response


def get_gcp_file_response_background(file):
    f_size = file.file.size
    filedata = default_storage.open(os.path.relpath(file.file.url, settings.MEDIA_URL), "rb").read()
    response = HttpResponse(content=filedata, content_type=mimetypes.guess_type(file.file.url)[0])
    response['Content-Length'] = f_size
    # response['Content-Disposition'] = f"attachment; filename={file.name}"
    response['Content-Disposition'] = f"attachment; filename={urlquote(file.name)}"

    return response


def get_gcp_archive_response(urls, parent, file_name):
    response = HttpResponse(content_type='application/zip')
    pack_gcp_files(response, urls, parent)
    response['Content-Disposition'] = f'attachment; filename={urlquote(file_name)}'

    return response


def unique_slug_generator(instance):
    TRUNC_SYMBOLS = 20
    slug = md5((instance.name + str(instance.id)).encode()).hexdigest()[:TRUNC_SYMBOLS]

    while instance.__class__.objects.filter(slug=slug).exists():
        slug = md5((instance.name + str(instance.id) + slug).encode()).hexdigest()[:TRUNC_SYMBOLS]

    return slug


def change_file_public_status(inst, first_file_flag=False, set_all_public=False):
    from projects.models import Project

    def _change_status(instance, ff_flag, public):
        parent = None if isinstance(instance, Project) else instance

        if instance.files.filter(folder=parent).exists():
            for file in instance.files.filter(folder_id=parent):
                if ff_flag:
                    file.is_public = True
                    ff_flag = False
                else:
                    file.is_public = public
                file.save()

        if instance.folders.exists():
            # print(parent, instance)
            for folder in instance.folders.filter(parent_folder=parent):
                new_ff_flag = _change_status(folder, ff_flag, public)

                if ff_flag:
                    folder.is_public = not new_ff_flag
                    ff_flag = new_ff_flag
                else:
                    folder.is_public = public

                folder.save()

        return ff_flag

    first_file_flag = _change_status(inst, first_file_flag, set_all_public)

    if first_file_flag and inst.folders.exists():
        folder = inst.folders[0]
        folder.is_public = True
        folder.save()


def files_transfer(namefiles, project_from_id, folder_from_id, project_to_id, folder_to_id):

    from projects.models import File, Project, Folder

    credentials = service_account.Credentials.from_service_account_file(
        filename=os.path.join(settings.BASE_DIR, 'config/credentials.json'),
        scopes=['https://www.googleapis.com/auth/devstorage.full_control'],
    )
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(settings.GS_BUCKET_NAME)

    project_from = get_object_or_404(Project, id=project_from_id) if project_from_id else None
    folder_from = get_object_or_404(Folder, id=folder_from_id) if folder_from_id else None
    project_to = get_object_or_404(Project, id=project_to_id) if project_to_id else None
    folder_to = get_object_or_404(Folder, id=folder_to_id) if folder_to_id else None

    # if project_from and project_to and project_from == project_to:
    #     return Response({'status': 'error', 'message': 'Нельзя переместить в тот же проект'}, status=400)

    if project_to:
        for filename in namefiles:
            file = File.objects.filter(name=filename, project=project_from, folder=folder_from)

            if file.exists():
                # file = file.first()
                #
                # if folder_to:
                #     path_from = folder_from.get_full_path()
                #     path_from = path_from.replace('\\', '/')
                # else:
                #     path_from = f'{project_from_id}'
                # path_from = f'{path_from}/{filename}'
                #
                # blob = bucket.blob(path_from)
                #
                # path_to = f'{project_to_id}'
                # if folder_to:
                #     path_to = folder_to.get_full_path()
                #     path_to = path_to.replace('\\', '/')
                # path_to = f'{path_to}/{filename}'
                #
                # bucket.rename_blob(blob, path_to)
                #
                # file.project = project_to
                # if folder_to:
                #     file.folder = folder_to
                #
                # file.save()
                file_processing(filename, file, bucket, folder_to, project_to, folder_from, project_from_id,
                                project_to_id)


def files_transfer1(files, project_to_id, folder_to_id):
    from projects.models import File, Project, Folder

    credentials = service_account.Credentials.from_service_account_file(
        filename=os.path.join(settings.BASE_DIR, 'config/credentials.json'),
        scopes=['https://www.googleapis.com/auth/devstorage.full_control'],
    )
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(settings.GS_BUCKET_NAME)

    project_to = get_object_or_404(Project, id=project_to_id) if project_to_id else None
    folder_to = get_object_or_404(Folder, id=folder_to_id) if folder_to_id else None

    # if project_from and project_to and project_from == project_to:
    #     return Response({'status': 'error', 'message': 'Нельзя переместить в тот же проект'}, status=400)

    if project_to:
        for file in files:
            # path_from = file.get_full_path()
            # path_from = path_from.replace('\\', '//')

            # blob = bucket.get_blob(file.file)
            # ------------------------------------------------------
            # blob = file.file.storage.bucket.get_blob(file.file.name)
            #
            # path_to = f'{project_to_id}'
            # if folder_to:
            #     path_to = folder_to.get_full_path()
            #     path_to = path_to.replace('\\', '/')
            # path_to = f'{path_to}/{file.name}'
            #
            # bucket.rename_blob(blob, path_to)
            #
            # file.file = path_to
            # file.project = project_to
            #
            # file.folder = folder_to
            #
            # file.save()
            file_processing_short(file, folder_to, project_to, project_to_id, bucket)


def file_processing(filename, file, bucket, folder_to, project_to, folder_from, project_from_id, project_to_id):
    file = file.first()

    if folder_to:
        path_from = folder_from.get_full_path()
        path_from = path_from.replace('\\', '/')
    else:
        path_from = f'{project_from_id}'
    path_from = f'{path_from}/{filename}'

    blob = bucket.blob(path_from)

    path_to = f'{project_to_id}'
    if folder_to:
        path_to = folder_to.get_full_path()
        path_to = path_to.replace('\\', '/')
    path_to = f'{path_to}/{filename}'

    bucket.rename_blob(blob, path_to)

    file.project = project_to
    if folder_to:
        file.folder = folder_to

    file.save()


def file_processing_short(file, folder_to, project_to, project_to_id, bucket):
    blob = file.file.storage.bucket.get_blob(file.file.name)

    path_to = f'{project_to_id}'
    if folder_to:
        path_to = folder_to.get_full_path()
        path_to = path_to.replace('\\', '/')
    path_to = f'{path_to}/{file.name}'

    bucket.rename_blob(blob, path_to)

    file.file = path_to
    file.project = project_to

    file.folder = folder_to

    file.save()