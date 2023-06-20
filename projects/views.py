import io
import json
import os
import shutil

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
from django.http import HttpResponse, Http404, JsonResponse, HttpResponseRedirect, HttpResponseServerError
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import generic
from django.core.cache import cache
from django.views.decorators.cache import never_cache
from django.views.generic.detail import BaseDetailView
from google.cloud import storage
from google.oauth2 import service_account
from rest_framework import viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from storages.utils import clean_name

from eml.models import EmailAddress
from eml.permissions import IsAdminUser
from profile_app.models import AppUser, Activity
from profile_app.permissions import UserCustomPermissionMixin
from . import utils
from .forms import FileUploadForm, MultiEmailForm, FileRenameForm, ProjectCreateForm, FolderCreateForm
from .models import Project, File, StorageMaxSize, Folder, get_upload_path
from .permissions import ProjectCustomPermissionMixin

from profile_app.models import AppUser
from .serializers import FolderSerializer, ProjectSerializer, FileSerializer
from .utils import files_transfer


class SearchMixin:
    """Миксин поиск файлов, проектов"""
    search = False

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        if self.request.GET.get('s'):
            self.search = True

    def update_queryset(self, queryset):
        search = self.request.GET.get('s')
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset


class JsonValidateResponseMixin:
    get_redirect_to_home = True
    no_success_redirect = False

    def form_valid(self, form):
        super().form_valid(form)
        success_url = self.get_success_url()

        response_dict = {"status": "ok", "success_url": success_url}
        if self.no_success_redirect:
            response_dict.update({'no_redirect': True})
        response = JsonResponse(response_dict, safe=False)

        return response

    def form_invalid(self, form):
        errors = {field_name: value[0] for field_name, value in form.errors.items()}

        return JsonResponse({"status": "error", "errors": errors}, safe=False)

    def get(self, request, *args, **kwargs):
        if self.get_redirect_to_home:
            response = HttpResponseRedirect(reverse_lazy('projects'))
        else:
            response = super().get(request, *args, **kwargs)

        return response


class ProjectListView(ProjectCustomPermissionMixin, SearchMixin, generic.ListView):
    """Отображение списка проектов"""
    required_permission = ('is_authenticated',)
    model = Project

    def get_queryset(self):
        # TODO: Удалить когда будет создана база EmailAddress из существующих пользователей
        # emails = EmailAddress.objects.all()
        # if not emails.exists():
        #     users = AppUser.objects.all()
        #     for user in users:
        #         EmailAddress.objects.get_or_create(email=user.email)

        # if emails.exists():
        #     for email in emails:
        #         email.delete()

        if self.request.path == reverse_lazy('my_projects'):
            queryset = self.request.user.project_created.all()
        elif self.request.user.role in ('admin', 'designer'):
            queryset = self.model.objects.all()
        else:
            queryset = self.request.user.projects.all()
        queryset = self.update_queryset(queryset)
        return queryset


class ProjectDetailView(ProjectCustomPermissionMixin, SearchMixin, generic.DetailView):
    """Отображение списка файлов проекта"""
    one_of_permission = ('public', 'is_member', 'admin', 'employee', 'designer')
    model = Project

    def get_allowed_objects(self, mdl='File'):
        user = self.request.user
        proj = self.get_object()
        # files = proj.files.filter(folder=None)
        # TODO: getattr

        if mdl == 'File':
            objects = proj.files.all() if getattr(self, 'search', None) else proj.files.filter(folder=None)
        elif mdl == 'Folder':
            objects = proj.folders.all() if getattr(self, 'search', None) else proj.folders.filter(parent_folder=None)

        if user.is_authenticated and (user.role in self.one_of_permission or user in proj.members.all()):
            objects = objects.all()
        elif proj.is_public:
            objects = objects.filter(is_public=True)
            self.extra_context = {"guest": True}
        else:
            objects = objects.none()

        return objects

    def get_context_data(self, **kwargs):
        # if self.request.user.is_authenticated and user.role :
        files = self.get_allowed_objects('File')
        dirs = self.get_allowed_objects('Folder')
        files = self.update_queryset(files)
        dirs = self.update_queryset(dirs)
        context = super().get_context_data(**kwargs)
        context['files'] = files
        context['dirs'] = dirs

        return context


class ProjectCreateView(ProjectCustomPermissionMixin, JsonValidateResponseMixin, generic.CreateView):
    """Создание проекта"""
    one_of_permission = ('admin', 'employee', 'executor', 'designer')
    model = Project
    # fields = ("name", )
    form_class = ProjectCreateForm
    success_url = reverse_lazy('projects')

    def form_valid(self, form):
        user = self.request.user
        form.instance.owner = form.instance.updated_by = user
        response = super().form_valid(form)
        self.object.members.add(user)

        if not self.request.user.is_anonymous and self.request.user.role != 'admin':
            Activity.objects.create(user=user, action="create_proj", name=form.instance.name)

        return response


class FileCreateView(ProjectCustomPermissionMixin, generic.CreateView):
    """Создание объекта"""
    one_of_permission = ('admin', 'employee', 'is_owner', 'designer', 'executor_member')
    model = File
    form_class = FileUploadForm

    def get_object(self, queryset=None):
        return Project.objects.get(id=self.kwargs.get('pk'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'project_pk': self.kwargs.get('pk')})
        return context

    def form_valid(self, form):
        user = self.request.user

        form.instance.owner = form.instance.updated_by = user
        form.instance.name = form.instance.file.name

        proj = Project.objects.get(id=self.kwargs.get('pk'))
        folder = Folder.objects.filter(id=self.request.POST.get('folder'))
        form.instance.project = proj
        if folder.exists():
            form.instance.folder = folder.get()
        form.instance.is_public = proj.is_public and not proj.files.filter(is_public=True).exists()

        if not self.request.user.is_anonymous and self.request.user.role != 'admin':
            Activity.objects.create(user=user, action="upload_file", name=form.instance.name)

        return super().form_valid(form)

    def get_form(self, form_class=None):
        """Return an instance of the form to be used in this view."""
        if form_class is None:
            form_class = self.get_form_class()

        kwargs = self.get_form_kwargs()
        forms_list = []
        # print(kwargs['data'])
        # data = {'project': kwargs['data'].get('project')}
        # if kwargs['data'].get('parent'):
        #     data.update({'folder': kwargs['data'].get('parent')})
        fl = kwargs.get('files')

        if fl:
            for file in kwargs['files'].getlist('file'):
                new_kwargs = {
                    'data': kwargs['data'],
                    'files': {'file': file}
                }
                forms_list.append(form_class(**new_kwargs))
        else:
            raise Http404()

        return forms_list

    def post(self, request, *args, **kwargs):
        self.object = None
        # print(self.request.FILES)

        form_list = self.get_form()
        uploaded = {}
        errors = {}
        bad_form = None

        for form in form_list:
            if form.is_valid():
                self.form_valid(form)
                uploaded[form.instance.name] = "ok"
            else:
                errors[form.files.get('file').name] = form.errors.get('file')
                bad_form = form

        status = "ok" if not bad_form else "error"
        result_dict = {
            "status": status,
        }

        if errors:
            result_dict.update({"errors": errors})
        if uploaded:
            result_dict.update({"uploaded": uploaded})

        return JsonResponse(result_dict, safe=False)


class ProjectDeleteView(ProjectCustomPermissionMixin, generic.DeleteView):
    """Удаление проектов"""
    one_of_permission = ('admin', 'employee', 'is_owner_list', 'designer')
    model = Project
    success_url = reverse_lazy('projects')

    def get_queryset(self):
        queryset = super().get_queryset()

        filter_list = self.request.GET.get('obj').split(',')
        queryset = queryset.filter(id__in=filter_list)

        return queryset

    def get_object(self, queryset=None):
        """returns queryset for multidelete"""
        if queryset is None:
            queryset = self.get_queryset()

        id_list = self.request.GET.get('obj').split(',')

        if queryset.exists():
            return queryset
        else:
            raise Http404(f"Projects with id {id_list} are not found")


class ObjectsDeleteView(ProjectCustomPermissionMixin, generic.DeleteView):
    """Удаление объектов"""
    one_of_permission = ('admin', 'employee', 'is_owner_list', 'designer')
    model = File
    template_name = 'projects/project_confirm_delete.html'
    id_list = []

    def get_success_url(self):
        files = self.request.GET.get('obj')
        dirs = self.request.GET.get('dir')

        querysets, urls = [], []
        if files:
            file_set = File.objects.filter(id__in=files.split(','))
            for file in file_set:
                urls.append(file.get_absolute_url())
        elif dirs:
            folder_set = Folder.objects.filter(id__in=dirs.split(','))
            for folder in folder_set:
                parent_folder = folder.parent_folder
                urls.append(
                    parent_folder.get_absolute_url() if parent_folder else folder.project.get_absolute_url())

        urls = list(set(urls))
        url = urls[0] if len(urls) == 1 else reverse_lazy('project_detail', kwargs=self.kwargs)

        return url

    def get_queryset(self):
        proj = Project.objects.get(**self.kwargs)
        queryset = self.model.objects.filter(project_id=proj.id)
        queryset = queryset.filter(id__in=self.id_list)

        return queryset

    def get_objects(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()

        if queryset.exists():
            return queryset
        else:
            raise Http404(f"Objects with id {self.id_list}  are not found")

    def delete(self, request, *args, **kwargs):
        # self.object = self.get_object()
        success_url = self.get_success_url()
        files = self.request.GET.get('obj')
        dirs = self.request.GET.get('dir')

        querysets = []
        if files:
            self.id_list = files.split(',')
            self.model = File
            querysets.append(self.get_objects())
        if dirs:
            self.id_list = dirs.split(',')
            self.model = Folder
            querysets.append(self.get_objects())

        for queryset in querysets:
            queryset.delete()
            # for object in queryset:
            #     if object:
            #         print(object)
            #         object.delete()

        return HttpResponseRedirect(success_url)


class ProjectRenameView(ProjectCustomPermissionMixin, JsonValidateResponseMixin, generic.UpdateView):
    """Переименование проекта"""
    one_of_permission = ('admin', 'employee', 'designer', 'is_owner')
    # fields = ('name',)
    form_class = ProjectCreateForm
    model = Project
    success_url = reverse_lazy('projects')
    # template_name = 'projects/project_rename.html'


class FileRenameView(ProjectCustomPermissionMixin, JsonValidateResponseMixin, generic.UpdateView):
    """Переименование файла"""
    one_of_permission = ('admin', 'employee', 'designer', 'is_owner')
    # fields = ('name',)
    form_class = FileRenameForm
    model = File

    # template_name = 'projects/project_rename.html'

    def get_success_url(self):
        proj_pk = File.objects.get(pk=self.kwargs['pk']).project_id
        return reverse_lazy('project_detail', kwargs={'pk': proj_pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        cur_file = self.get_object()
        # abs_path = os.path.dirname(cur_file.file.path)
        # min_path = os.path.relpath(abs_path, start=settings.MEDIA_ROOT)
        # new_name = form.instance.name
        # initial_path = cur_file.file.path
        #
        # cur_file.file.name = os.path.join(min_path, new_name).replace('\\', '/')
        # os.rename(initial_path, os.path.join(abs_path, new_name))
        cur_file.updated_by = self.request.user

        # TODO :
        #  psycopg2.errors.StringDataRightTruncation: ПОМИЛКА:  значення занадто довге для типу character varying(100)

        bucket = cur_file.file.storage.bucket
        blob = bucket.blob(cur_file.file.name)
        file_dir = os.path.split(os.path.relpath(cur_file.file.url, settings.MEDIA_URL))[0]  # TODO: remake
        new_name = os.path.join(file_dir, form.instance.name)
        new_name = cur_file.file.storage._normalize_name(clean_name(new_name))
        bucket.rename_blob(blob, new_name)
        cur_file.file.name = new_name
        cur_file.save()

        return response


class MembersEditView(ProjectCustomPermissionMixin, generic.UpdateView):
    """Переименование проекта"""
    one_of_permission = ('admin', 'employee', 'is_owner', 'designer')
    fields = ('members',)
    model = Project

    def form_valid(self, form):
        response = super().form_valid(form)
        proj = self.object
        proj.members.add(proj.owner)
        return response

    def get_form(self, form_class=None):
        # print(self.request.POST)
        form = super().get_form()
        proj_owner_id = self.get_object().owner.id
        users_query = AppUser.objects.exclude(Q(role="admin") | Q(id=proj_owner_id))
        form['members'].field.queryset = users_query
        return form

    # widgets = {
    #     'members': CheckboxSelectMultiple,
    # }

    # def get_form_class(self):
    #     return models.modelform_factory(self.model, fields=self.fields, widgets=self.widgets)


class ChangeMemberStatus(ProjectCustomPermissionMixin, generic.View):
    one_of_permission = ('admin', 'employee', 'designer')

    def post(self, request, *args, **kwargs):
        proj = Project.objects.get(id=kwargs['project_id'])
        user = AppUser.objects.get(id=kwargs['user_id'])
        if user in proj.members.all() and user != proj.owner:
            proj.members.remove(user)
        else:
            proj.members.add(user)
        return HttpResponse(status=201)


class DownloadProjectZip(ProjectCustomPermissionMixin, generic.View):
    """Скачка проекта"""
    one_of_permission = ('admin', 'employee', 'is_member', 'designer')
    file_type = '.zip'

    def get_object(self):
        return Project.objects.get(**self.kwargs)  # for permissions

    def get(self, request, *args, **kwargs):
        additional = request.GET.get('add')
        proj = Project.objects.get(id=kwargs['pk'])
        # default_path = settings.MEDIA_ROOT if additional else os.path.join(settings.MEDIA_ROOT, str(kwargs['pk']))
        parent = None if additional else proj.name

        # file_path = utils.get_project_files(kwargs['pk'])
        urls = utils.get_project_urls(kwargs['pk'])
        if additional:
            for proj_id in additional.split(','):
                # utils.get_project_files(int(proj_id), file_path)
                utils.get_project_urls(int(proj_id), urls)

        file_name = f"{proj.name if not additional else 'projects'}{self.file_type}"

        response = utils.get_gcp_archive_response(urls, parent, file_name)

        return response


class TransferFile(ProjectCustomPermissionMixin, generic.View):
    """Перемещение объекта"""
    one_of_permission = ('admin', 'employee', 'is_member', 'designer')

    def post(self, request):
        data = request.POST
        # files = data['files']
        # project_from_id = data['project_from_id']
        # folder_from_id = data['folder_from_id']
        # project_to_id = data['project_to_id']
        # folder_to_id = data['folder_to_id']

        # files_transfer(files, project_from_id, folder_from_id, project_to_id, folder_to_id)
        files_transfer(namefiles=data['files'],
                       project_from_id=data['project_from_id'],
                       folder_from_id=data['folder_from_id'],
                       project_to_id=data['project_to_id'],
                       folder_to_id=data['folder_to_id'])

        return Response({'status': 'ok'}, status=201)


class DownloadFile(ProjectCustomPermissionMixin, generic.View):
    """Скачка объекта"""
    one_of_permission = ('admin', 'employee', 'is_member', 'designer', 'public')
    archive_type = '.zip'

    def get_querysets_dict(self):
        querysets = {}
        files = self.request.GET.get('obj')
        dirs = self.request.GET.get('dir')

        if files:
            files_id_list = files.split(',')
            are_slug = not all(i.isdigit() for i in files_id_list)
            if are_slug:
                querysets['File'] = File.objects.filter(slug__in=[i for i in files_id_list])
            else:
                querysets['File'] = File.objects.filter(id__in=[int(i) for i in files_id_list])
        if dirs:
            dir_list = dirs.split(',')
            are_slug = not all(i.isdigit() for i in dir_list)
            if are_slug:
                querysets['Folder'] = Folder.objects.filter(slug__in=[i for i in dir_list])
            else:
                querysets['Folder'] = Folder.objects.filter(id__in=[int(i) for i in dir_list])

        return querysets

    def get_object(self):
        # for permissions. If 1 of objects is not public, returns that

        vr = self.request.GET.get('vr')
        if self.request.user.is_anonymous and vr == 'true':
            user = authenticate(username='alermar17@gmail.com', password='vvvv032969')
            self.request.user = user

        querysets = self.get_querysets_dict()
        files = querysets.get('File')
        folders = querysets.get('Folder')

        obj = files.filter(is_public=False) if files else folders.filter(is_public=False)
        if obj.exists():
            obj = obj.get()
        else:
            obj = files.filter(is_public=True)[0] if files else folders.filter(is_public=True)[0]

        return obj

    # @staticmethod
    # def get_folder_files_id(dir_id):
    #     folder = Folder.objects.get(id=dir_id)
    #     id_list = list(folder.files.values_list('id', flat=True)) if folder.files.exists() else []
    #     if folder.folders.exists():
    #         for directory in folder.folders.all():
    #             id_list += (DownloadFile.get_folder_files_id(directory.id))
    #
    #     return id_list

    def get(self, request, *args, **kwargs):
        querysets = self.get_querysets_dict()
        files = querysets.get('File')
        folders = querysets.get('Folder')

        background = self.request.GET.get('background')

        urls = []
        if files:
            urls = [(file.get_norm_url(), file.get_norm_path()) for file in files]
        if folders:
            dir_list = folders.values_list('id', flat=True)
            for dir_id in dir_list:
                urls = utils.get_folder_urls(dir_id, urls)

        # additional = request.GET.get('add')

        # cur_file = self.get_object()
        # filename = cur_file.name
        # file_path = [cur_file.file.path, ]
        # urls = [cur_file.file.url, ]
        filename = ''

        if background:
            cur_file = files[0]
            filename = cur_file.name
            response = utils.get_gcp_file_response_background(cur_file)
        else:
            if len(urls) == 1 and not folders:
                # response = utils.get_file_response(file_path[0], filename)
                cur_file = files[0]
                filename = cur_file.name
                response = utils.get_gcp_file_response(cur_file)
            else:
                if self.kwargs.get('project_id'):
                    proj = Project.objects.get(id=self.kwargs.get('project_id'))
                    folder = Folder.objects.filter(id=self.kwargs.get('folder_id'))
                else:
                    proj = Project.objects.get(slug=self.kwargs.get('slug'))
                    folder = Folder.objects.filter(slug=self.kwargs.get('folder_id'))

                parent = folder.get() if folder.exists() and not request.GET.get('s') else proj
                parent_path = parent.get_norm_path() if isinstance(parent, Folder) else parent.name
                # default_path = os.path.join(settings.MEDIA_ROOT, str(proj.id))
                # default_url = urljoin(settings.MEDIA_URL, parent_path)

                # for file_id in id_list:
                #     try:
                #         if isinstance(file_id, int):
                #             file = proj.files.get(id=file_id)
                #         else:
                #             file = proj.files.get(slug=file_id)
                #     except File.DoesNotExist:
                #         raise Http404()
                #     # file_path.append(file.file.path)
                #     urls.append(file.file.url)
                #     filename += f', {file.name}'
                #
                # print(urls, default_url)
                response = utils.get_gcp_archive_response(urls, parent_path, f'{parent.name}{self.archive_type}')

        if not request.user.is_anonymous and request.user.role != 'admin':
            Activity.objects.create(user=request.user, action="download_file", name=filename)

        return response


class PublicLinkView(ProjectCustomPermissionMixin, generic.TemplateView):
    one_of_permission = ('admin', 'employee', 'is_member_list', 'designer')
    post_perm = ('admin', 'employee', 'is_owner_list', 'designer')
    model = Project
    template_name = 'projects/public_link.html'

    # @staticmethod
    # def change_file_public_status(proj, first_file_flag=False, set_all_public=False):
    #     for file in proj.files.all():
    #         if first_file_flag:
    #             file.is_public = True
    #             first_file_flag = False
    #         else:
    #             file.is_public = set_all_public
    #         file.save()

    def get_queryset(self):
        try:
            req_id = self.request.GET.get('pr').split(',') if self.request.GET.get('pr') else \
                json.loads(self.request.POST.get('id_list'))
            id_list = [int(num) for num in req_id]
        except (ValueError, AttributeError):
            raise Http404()

        queryset = self.model.objects.filter(id__in=id_list)
        if not queryset.exists():
            raise Http404()

        return queryset

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        shared = all(not inst.files.filter(is_public=False, folder=None).exists() for inst in queryset)
        for inst in queryset:
            shared = shared and all(folder.check_shared() for folder in inst.folders.filter(parent_folder=None))
        count = any(inst.files.count() for inst in queryset)
        are_public = queryset.filter(is_public=True).count() == queryset.count()
        edit_allowed = request.user.role in self.one_of_permission or all(request.user == pr.owner for pr in queryset)

        protocol = "https" if settings.SECURE_CONNECTION else "http"
        address = get_current_site(request)

        context = {'projects': queryset,
                   'all_files_shared': shared and count,
                   'are_public': are_public,
                   'id_list': list(queryset.values_list('id', flat=True)),
                   'last_pr': queryset.reverse()[0],
                   'edit_allowed': edit_allowed,
                   "protocol": protocol,
                   "address": address,
                   }
        self.extra_context = context

        response = super().get(request, *args, **kwargs)

        if not request.user.is_anonymous and request.user.role != 'admin' and all(inst.is_public for inst in queryset):
            name = ', '.join(queryset.values_list('name', flat=True))
            Activity.objects.create(user=request.user, action="share_pr_link", name=name)
        return response

    def post(self, request, *args, **kwargs):
        # response = super().post(request, *args, **kwargs)
        # post_dict examples:
        # 'id_list': ['[43, 42]'] if all checkboxes disabled
        # 'id_list': ['[43, 42]'], 'is_public': ['None'] if clicked public checkbox
        # 'id_list': ['[43, 42]'], 'all_files_shared': ['share'], 'all_files_shared_checkbox': ['True'],
        #           'is_public': ['True'] if checked share checkbox
        # 'id_list': ['[43, 42]'], 'all_files_shared_checkbox': ['True'], 'is_public': ['True']
        #           if unchecked share checkbox

        # unexpected options:
        # 'id_list': ['[43, 42]'], 'all_files_shared': ['share'], 'all_files_shared_checkbox': ['True']
        #       if checked share when is_public was unchecked
        # 'id_list': ['[43, 42]'], 'all_files_shared_checkbox': ['True'] if unchecked share when is_public was unchecked

        post_dict = request.POST

        id_list = json.loads(post_dict.get('id_list'))
        queryset = self.model.objects.filter(id__in=id_list)

        public_checkbox = not post_dict.get('all_files_shared_checkbox')
        share = bool(post_dict.get('all_files_shared'))
        are_public = bool(post_dict.get('is_public'))

        first_file_flag = True if (public_checkbox and are_public) or (not public_checkbox and not share) else False
        set_all_public = True if (not public_checkbox and share) else False

        for obj in queryset:
            if obj.is_public != are_public:
                obj.is_public = are_public
                obj.save()
            utils.change_file_public_status(obj, first_file_flag=first_file_flag, set_all_public=set_all_public)

        return HttpResponse(status=201)


class ObjectLinkView(ProjectCustomPermissionMixin, generic.TemplateView):
    one_of_permission = ('admin', 'employee', 'is_member_list', 'designer')
    post_perm = ('admin', 'employee', 'is_owner_list', 'designer')
    model = File
    template_name = 'projects/file_pub_link.html'
    files_id_list = []
    folders_id_list = []

    def get_querysets_list(self):
        try:
            if not self.files_id_list and not self.folders_id_list:
                files = self.request.GET.get('obj')
                folders = self.request.GET.get('dir')
                self.files_id_list = [int(num) for num in files.split(',')] if files else []
                self.folders_id_list = [int(num) for num in folders.split(',')] if folders else []
            if not self.files_id_list and not self.folders_id_list:
                raise AttributeError
        except (ValueError, AttributeError):
            raise Http404()

        querysets = []
        parent_set = set()

        if self.files_id_list:
            queryset = File.objects.filter(id__in=self.files_id_list)
            for file in queryset:
                f_parent = file.folder if file.folder else file.project
                parent_set.add(f_parent)

            querysets.append(queryset)

        if self.folders_id_list:
            queryset = Folder.objects.filter(id__in=self.folders_id_list)

            for folder in queryset:
                f_parent = folder.parent_folder if folder.parent_folder else folder.project
                parent_set.add(f_parent)

            querysets.append(queryset)

        self.parent_set = parent_set

        return querysets

    def get_queryset(self, many=False):
        if self.request.POST:
            post_dict = self.request.POST
            files_id_list = post_dict.get('files_id_list')
            folders_id_list = post_dict.get('folders_id_list')

            self.files_id_list = json.loads(files_id_list) if files_id_list else None
            self.folders_id_list = json.loads(folders_id_list) if folders_id_list else None

        querysets = self.get_querysets_list()
        queryset = querysets[0]
        if not queryset.exists():
            raise Http404()

        return queryset if not many else querysets

    def get(self, request, *args, **kwargs):
        querysets = self.get_queryset(many=True)

        are_public = all(not (queryset.filter(is_public=False).exists()) for queryset in querysets)
        user = request.user
        first_el = list(self.parent_set)[0]
        # print(first_el)
        proj = first_el.project if isinstance(first_el, Folder) else first_el
        parent = proj if len(self.parent_set) > 1 else first_el

        edit_allowed = user.role in self.one_of_permission or user == proj.owner

        protocol = "https" if settings.SECURE_CONNECTION else "http"
        address = get_current_site(request)
        all_files_shared = False

        for queryset in querysets:
            if isinstance(queryset[0], Folder):
                all_files_shared = all(folder.check_shared() for folder in queryset)

        context = {'parent': parent,
                   'are_public': are_public,
                   'files_id_list': self.files_id_list,
                   'folders_id_list': self.folders_id_list,
                   # 'last_f': queryset.reverse()[0],
                   'edit_allowed': edit_allowed,
                   'all_files_shared': all_files_shared,
                   "protocol": protocol,
                   "address": address,
                   }
        self.extra_context = context

        response = super().get(request, *args, **kwargs)

        if not request.user.is_anonymous and request.user.role != 'admin' and are_public:
            names_list = []
            for queryset in querysets:
                names_list += list(queryset.values_list('name', flat=True))

            name = ', '.join(names_list)
            Activity.objects.create(user=request.user, action="share_ob_link", name=name)

        return response

    def post(self, request, *args, **kwargs):
        post_dict = request.POST
        # print(post_dict)

        querysets = self.get_queryset(many=True)

        public_checkbox = not post_dict.get('all_files_shared_checkbox')
        share = bool(post_dict.get('all_files_shared'))
        are_public = bool(post_dict.get('is_public'))

        for queryset in querysets:
            if isinstance(queryset[0], File):

                for file in queryset:
                    file.is_public = are_public
                    file.save()

            elif isinstance(queryset[0], Folder):
                first_file_flag = True if (public_checkbox and are_public) or (
                        not public_checkbox and not share) else False
                set_all_public = True if (not public_checkbox and share) else False

                for obj in queryset:
                    if obj.is_public != are_public:
                        obj.is_public = are_public
                        obj.save()
                    utils.change_file_public_status(obj, first_file_flag=first_file_flag, set_all_public=set_all_public)

        return HttpResponse(status=201)


class ClearCacheView(UserCustomPermissionMixin, generic.View):
    required_permission = 'admin',

    def post(self, request, *args, **kwargs):
        static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
        ico_path = os.path.join('images', 'content_type')
        preview_dir = os.path.join(static_dir, ico_path, "preview")
        try:
            if os.path.exists(preview_dir):
                shutil.rmtree(preview_dir)
            status = "ok"
            cache.clear()
        except Exception:
            status = "error"  # TODO: what kind?
        return JsonResponse({"status": status}, safe=False)


class AddMembersMail(ProjectCustomPermissionMixin, generic.View):
    one_of_permission = ('admin', 'employee', 'is_owner_list', 'designer')

    def get_queryset(self):
        try:
            id_list = [int(item) for item in self.request.POST.get('selected_items').split(',')]
        except (ValueError, AttributeError):
            raise Http404()
        return Project.objects.filter(id__in=id_list)

    def post(self, request, *args, **kwargs):
        # print(request.POST)

        # TODO: json response {mail: status}
        address, protocol = get_current_site(request), "https" if settings.SECURE_CONNECTION else "http"
        initial = {
            "address": address,
            "protocol": protocol,
        }

        form = MultiEmailForm(request.POST, initial=initial)

        if form.is_valid():
            # emails = form.cleaned_data.get("emails")
            form.save()
            queryset = self.get_queryset()
            if queryset.count() == 1:
                success_url = reverse_lazy('project_detail', kwargs={'pk': queryset.get().id})
            else:
                success_url = reverse_lazy('projects')
            response = JsonResponse({"status": "ok", "success_url": success_url}, safe=False)
        else:
            response = self.form_invalid(form)

        return response

    def form_invalid(self, form):
        errors = {field_name: value[0] for field_name, value in form.errors.items()}
        return JsonResponse({"status": "error", "errors": errors}, safe=False)


class FolderDetailView(ProjectCustomPermissionMixin, SearchMixin, generic.DetailView):
    """Отображение списка файлов папки"""
    one_of_permission = ('public', 'is_member', 'admin', 'employee', 'designer')
    model = Folder
    template_name = "projects/project_detail.html"

    def get_queryset(self):
        p_id = self.kwargs.get('project_id')
        queryset = Folder.objects.filter(project_id=p_id) if str(p_id).isdigit() \
            else Folder.objects.filter(project__slug=p_id)

        return queryset

    def get_allowed_objects(self, mdl='File'):
        user = self.request.user
        folder = self.get_object()
        proj = folder.project
        # TODO: getattr
        if mdl == 'File':
            objects = proj.files.all() if getattr(self, 'search', None) else folder.files.all()
        elif mdl == 'Folder':
            objects = proj.folders.all() if getattr(self, 'search', None) else folder.folders.all()

        if user.is_authenticated and (user.role in self.one_of_permission or user in folder.project.members.all()):
            objects = objects.all()
        elif folder.is_public:
            objects = objects.filter(is_public=True)
            self.extra_context = {"guest": True}
        else:
            objects = objects.none()

        return objects

    def get_context_data(self, **kwargs):
        # if self.request.user.is_authenticated and user.role :
        files = self.get_allowed_objects('File')
        dirs = self.get_allowed_objects('Folder')
        files = self.update_queryset(files)
        dirs = self.update_queryset(dirs)
        context = super().get_context_data(**kwargs)
        context['files'] = files
        context['dirs'] = dirs
        context['project'] = self.get_object().project
        return context


class FolderCreateView(ProjectCustomPermissionMixin, JsonValidateResponseMixin, generic.CreateView):
    """Создание папки"""
    one_of_permission = ('admin', 'employee', 'is_owner', 'designer', 'executor_member')
    model = Folder
    # fields = ("name", )
    form_class = FolderCreateForm

    # success_url = reverse_lazy('projects')

    def get_object(self, queryset=None):
        return Project.objects.get(id=self.kwargs.get('pk'))

    def form_valid(self, form):
        user = self.request.user
        form.instance.owner = form.instance.updated_by = user

        proj = Project.objects.get(id=self.kwargs.get('pk'))
        folder = Folder.objects.filter(id=self.request.POST.get('folder'))
        form.instance.project = proj
        if folder.exists():
            form.instance.parent_folder = folder.get()
        form.instance.is_public = proj.is_public and not proj.files.filter(is_public=True).exists()

        response = super().form_valid(form)

        if not self.request.user.is_anonymous and self.request.user.role != 'admin':
            Activity.objects.create(user=user, action="create_obj", name=form.instance.name)

        return response


class FolderRenameView(ProjectCustomPermissionMixin, JsonValidateResponseMixin, generic.UpdateView):
    """Переименование папки"""
    one_of_permission = ('admin', 'employee', 'designer', 'is_owner')
    # fields = ('name',)
    form_class = FolderCreateForm
    model = Folder

    # success_url = reverse_lazy('projects')
    # template_name = 'projects/project_rename.html'

    def get_success_url(self):
        obj = self.get_object()
        if obj.parent_folder:
            folder_id = obj.parent_folder_id
            url = reverse_lazy('folder_detail', kwargs={'project_id': obj.project_id, 'pk': folder_id})
        else:
            url = reverse_lazy('project_detail', kwargs={'pk': obj.project_id})

        return url


class PdfPreview(ProjectCustomPermissionMixin, generic.DetailView):
    one_of_permission = ('admin', 'employee', 'is_member', 'designer', 'public')
    model = File

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        ext = self.object.get_ext()
        # with open(self.object.file.url, 'rb') as pdf_document:
        if ext == 'pdf':
            pdf = self.object.file.read()
        elif ext in ('doc', 'docx'):
            pass

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = 'inline;filename=pdf_file.pdf'

        return response


class ObjectMoveView(ProjectCustomPermissionMixin, BaseDetailView):
    one_of_permission = ('admin', 'employee', 'designer')
    # TODO: исполнитель может перемещать папки, файлы, созданными им, в папки, которые создал.
    model = Project

    def get_querysets_dict(self):
        querysets = {}
        files = self.request.POST.get('moved_files')
        dirs = self.request.POST.get('moved_folders')

        if files:
            files_id_list = files.split(',')
            querysets['File'] = File.objects.filter(id__in=[int(i) for i in files_id_list])
        if dirs:
            dir_list = dirs.split(',')
            querysets['Folder'] = Folder.objects.filter(id__in=[int(i) for i in dir_list])

        return querysets

    def relocate_file_gcp(self, file):
        pass

    def get_dir_files(self, folder):
        pass

    def post(self, request, *args, **kwargs):
        dst = request.POST.get('destination_folder')
        dest_folder = Folder.objects.get(id=int(dst)) if dst else None
        dest_project = Project.objects.get(id=int(request.POST.get('destination_project')))
        querysets = self.get_querysets_dict()

        files = querysets.get('File')
        folders = querysets.get('Folder')

        if files:
            for file in files:
                file.folder = dest_folder
                file.project = dest_project
                self.relocate_file_gcp(file)
                file.save()
        if folders:
            for folder in folders:
                folder.parent_folder = dest_folder
                folder.project = dest_project
                folder.save()
                folder_files = self.get_dir_files(folder)
                for file in folder_files:
                    self.relocate_file_gcp(file)


# class AjaxValidation(generic.FormView):
#     form_dict = {
#         'create_proj': modelform_factory(ProjectCreateView.model, fields=ProjectCreateView.fields),
#         'rename_proj': modelform_factory(ProjectRenameView.model, fields=ProjectRenameView.fields),
#     }
#
#     def get(self, request, *args, **kwargs):
#         return HttpResponseRedirect('/')
#
#     def form_invalid(self, form):
#         data = []
#         errors = {field_name: value[0] for field_name, value in form.errors.items()}
#         response = JsonResponse({"status": "error", "errors": errors}, safe=False)
#         # for k, v in form._errors.iteritems():
#         #     text = {
#         #         'desc': ', '.join(v),
#         #     }
#         #     if k == '__all__':
#         #         text['key'] = '#%s' % self.request.POST.get('form')
#         #     else:
#         #         text['key'] = '#id_%s' % k
#         #     data.append(text)
#         return response
#
#     def form_valid(self, form):
#         return HttpResponse("ok")
#
#     def get_form_class(self):
#         # return self.form_dict[self.request.POST.get('form')]
#         # return self.form_dict['create_proj']
#         return self.form_dict['rename_proj']


def recalculate_size(request):
    """Пересчет размера файлов, проектов"""
    for file in File.objects.all():
        file.save()
    return HttpResponse("ok", status=201)


def create_folders(request):
    user = request.user
    if user.is_authenticated and user.role == 'admin':
        project = Project.objects.create(name='Тест удаления', owner=user, updated_by=user)
        project.members.add(user)
        project.save()
        folder1 = Folder.objects.create(name='папка1', project=project, owner=user, updated_by=user)
        folder2 = Folder.objects.create(name='папка2', project=project, owner=user, updated_by=user)
        folder3 = Folder.objects.create(name='папка_внутри', project=project, parent_folder=folder1, owner=user,
                                        updated_by=user)
        folder2.parent_folder = folder3
        folder2.save()

    return HttpResponse("ok", status=201)


# def relocate_files(request):
#     files = File.objects.all().exclude(id=210)
#     # cur_file = File.objects.get(id=210)
#
#
#
#     for file in files:
#         file.delete()
#     # bucket = files[0].file.storage.bucket
#     # blob = bucket.blob(cur_file.file.name)
#     # file_dir = os.path.split(os.path.relpath(cur_file.file.url, settings.MEDIA_URL))[0]  # TODO: remake
#     # new_name = os.path.join(file_dir, cur_file.name)
#     # new_name = cur_file.file.storage._normalize_name(clean_name(new_name))
#     # bucket.rename_blob(blob, new_name)
#     # cur_file.file.name = new_name
#     # cur_file.save()
#     return HttpResponse("ok", status=201)


def upload_progress(request):
    """
    A view to report back on upload progress.
    Return JSON object with information about the progress of an upload.

    Copied from:
    http://djangosnippets.org/snippets/678/

    See upload.py for file upload handler.
    """
    # import ipdb
    # ipdb.set_trace()

    progress_id = ''
    if 'X-Progress-ID' in request.GET:
        progress_id = request.GET['X-Progress-ID']
    elif 'X-Progress-ID' in request.META:
        progress_id = request.META['X-Progress-ID']
    if progress_id:
        cache_key = "%s_%s" % (request.META['REMOTE_ADDR'], progress_id)
        # print(cache_key)
        data = cache.get(cache_key)
        if data and data['length'] <= data['uploaded']:
            cache.delete(cache_key)
            # print('delete')

        return HttpResponse(json.dumps(data))


class ProjectBlogView(ProjectCustomPermissionMixin, SearchMixin, generic.DetailView):
    """Отображение списка файлов папки"""
    one_of_permission = ('public', 'is_member', 'admin', 'employee', 'designer')
    model = Project
    template_name = "projects/blog.html"

    def get_allowed_objects(self, mdl='File'):
        user = self.request.user
        proj = self.get_object()
        # files = proj.files.filter(folder=None)
        # TODO: getattr

        if mdl == 'File':
            objects = proj.files.all() if getattr(self, 'search', None) else proj.files.filter(folder=None)
        elif mdl == 'Folder':
            objects = proj.folders.all() if getattr(self, 'search', None) else proj.folders.filter(parent_folder=None)

        if user.is_authenticated and (user.role in self.one_of_permission or user in proj.members.all()):
            objects = objects.all()
        elif proj.is_public:
            objects = objects.filter(is_public=True)
            self.extra_context = {"guest": True}
        else:
            objects = objects.none()

        return objects

    def get_context_data(self, **kwargs):
        # if self.request.user.is_authenticated and user.role :
        files = self.get_allowed_objects('File')
        dirs = self.get_allowed_objects('Folder')
        files = self.update_queryset(files)
        dirs = self.update_queryset(dirs)
        context = super().get_context_data(**kwargs)
        context['files'] = files
        context['dirs'] = dirs

        return context


# API

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    # def get_queryset(self):
    #     user = self.request.user
    #     if user.is_authenticated and user.role in ('admin', 'employee', 'designer'):
    #         return Project.objects.all()
    #     return Project.objects.filter(is_public=True)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def get_permissions(self):
        # check the action and return the permission class accordingly
        if self.action == 'create':
            self.permission_classes = [IsAdminUser, ]

        return super().get_permissions()


class FolderViewSet(viewsets.ModelViewSet):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def get_permissions(self):
        # check the action and return the permission class accordingly
        if self.action == 'create':
            self.permission_classes = [IsAdminUser, ]

        return super().get_permissions()


class FileViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = File.objects.all()
    serializer_class = FileSerializer


class FileGetIdAPIView(APIView):

    def get(self, request):
        path = request.GET.get('path')
        path_ls = path.split('/')
        project = Project.objects.filter(name=path_ls[0])
        if project:
            project = project[0]
            files = File.objects.filter(name=path_ls[-1], project=project)
            if files:
                if len(files) == 1:
                    file = files[0]
                else:
                    for f in files:
                        path_file = f.get_norm_path()
                        path_file = path_file.replace('\\', '/')
                        if path_file == path:
                            file = f
                            break
            if file:
                return Response({'id': file.id})
        return None


class FileDownloadAPIView(APIView):

    def get(self, request, id):
        cur_file = get_object_or_404(File, id=id)
        response = utils.get_gcp_file_response_background(cur_file)
        return response


class FileUploadAPIView(APIView):

    def post(self, request):
        user = request.user

        data = request.data
        file = data['file']
        project_id = data['project_id']
        folder_id = data['folder_id']

        project = get_object_or_404(Project, id=project_id) if project_id else None
        folder = get_object_or_404(Folder, id=folder_id) if folder_id else None

        file_cabinet = File.objects.filter(name=file.name, folder=folder, project=project)
        if file_cabinet.exists():
            file_cabinet = file_cabinet.first()
            credentials = service_account.Credentials.from_service_account_file(
                filename=os.path.join(settings.BASE_DIR, 'config/credentials.json'),
                scopes=['https://www.googleapis.com/auth/devstorage.full_control'],
            )
            client = storage.Client(credentials=credentials)
            bucket = client.bucket(settings.GS_BUCKET_NAME)
            if folder:
                path = folder.get_full_path()
                path = path.replace('\\', '/')
            else:
                path = f'{project_id}'
            path = f'{path}/{file.name}'
            blob = bucket.blob(path)
            blob.upload_from_file(file)
            file_cabinet.save()
        else:
            File.objects.create(name=file.name, file=file, owner=user, project=project, updated_by=user, folder=folder,
                                is_public=False)

        return Response({'status': 'ok'}, status=201)
