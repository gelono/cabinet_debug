import threading
import time

import django
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from imap_tools import MailBox, UidRange, A
from rest_framework import status, viewsets, permissions
from rest_framework.authentication import TokenAuthentication, BasicAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.decorators import action, permission_classes, api_view

from eml.forms import MessageForm, MessageTransferForm
from eml.models import Message, EmailAddress
from eml.permissions import IsOwner, IsMembers
from eml.serializers import MessageSerializer
from eml.templatetags.eml_tag import get_messages_folder
from eml.utils import EmailMessageUtils, create_files, create_files1, msg_processing
from profile_app.models import AppUser
from projects.models import Project, File, Folder
from projects.permissions import ProjectCustomPermissionMixin
from projects.utils import files_transfer, files_transfer1
from prozorro_parser.start_parse import start_parse_prozorro
from vr.parser_bd_storeg import parser_bd

TASK_THREAD = None


class SendEmailView(ProjectCustomPermissionMixin, generic.FormView):
    one_of_permission = ('admin', 'designer')
    template_name = 'emails/send_email.html'
    form_class = MessageForm
    success_url = reverse_lazy('send_email')

    def get_initial(self):
        initial = super().get_initial()
        initial['email_from'] = self.request.user.email

        # TODO: Удалить когда будет создана база EmailAddress из существующих пользователей
        # emails = EmailAddress.objects.all()
        # if not emails.exists():
        #     users = AppUser.objects.all()
        #     for user in users:
        #         EmailAddress.objects.get_or_create(email=user.email)

        # Message.objects.all().delete()
        # qs = File.objects.filter(folder__name='Почта файлы')
        # qs.delete()

        # self.load_emails()
        return initial

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Сообщение отправлено')
        return redirect('send_email')

    def load_emails(self):
        def get_emails(is_incoming):

            uid = 1
            uids = Message.objects.filter(is_incoming=is_incoming)
            uids = list(uids.values_list('uid_host', flat=True))
            if len(uids) > 0:
                uid = max(uids)
                uid += 1

            # uds = mailbox.uids()
            # uid = uds[-1]

            messages = mailbox.fetch(A(uid=UidRange(uid, '*')))
            for msg in messages:
                try:
                    uid_host = int(msg.uid)
                    if uid_host not in uids:
                        # if uid_host not in uds:
                        eml = Message()
                        eml.is_incoming = is_incoming
                        # eml.email_from = msg.from_
                        if msg.headers.get('x-google-original-from'):
                            eml.email_from = msg.headers['x-google-original-from']
                        else:
                            eml.email_from = msg.from_
                        eml.topic = msg.subject
                        eml.text = msg.text
                        eml.html = msg.html
                        eml.created = msg.date
                        eml.uid_host = int(msg.uid)
                        eml.save()

                        for to in msg.to:
                            adr = EmailAddress.objects.filter(email=to)
                            if adr:
                                eml.email_to.add(adr[0])
                            else:
                                adr = EmailAddress(email=to)
                                adr.save()
                                eml.email_to.add(adr)
                            # eml.email_to.add(EmailAddress.objects.get(email=to))

                        # fold = Folder.objects.filter(name='Почта файлы').first()
                        # fold = Folder.objects.get(pk=459)
                        # fold = Folder.objects.get(pk=8)
                        # proj = Project.objects.get(pk=fold.project_id)

                        user = AppUser.objects.filter(email=eml.email_from)
                        if user.exists():
                            user = user[0]
                        else:
                            user = AppUser.objects.get(username='info@grand.engineering')
                            # user = AppUser.objects.get(username='admin')

                        fold = None
                        proj = None
                        proj_folder_id = eml.topic.rsplit('~&', 1)
                        if len(proj_folder_id) == 2:
                            proj_folder_id = proj_folder_id[1].split('.')
                            if len(proj_folder_id) == 2:
                                project_id = proj_folder_id[0]
                                folder_id = proj_folder_id[1]
                                proj = Project.objects.get(pk=project_id)
                                fold = Folder.objects.get(pk=folder_id)
                            else:
                                project_id = proj_folder_id[0]
                                proj = Project.objects.get(pk=project_id)
                        else:
                            project = Project.objects.filter(members__in=[user]).first()
                            if project:
                                proj = project
                            else:
                                proj = Project.objects.get(pk=35)
                                fold = Folder.objects.get(pk=461)

                        if proj:
                            eml.project = proj
                        if fold:
                            eml.folder = fold

                        for file in msg.attachments:
                            if file.filename != '' and not file.filename.startswith('icon'):
                                fl = File()
                                fl.project = proj
                                fl.folder = fold
                                fl.name = file.filename
                                files = File.objects.filter(name=file.filename, folder=fold, project=proj)
                                if files.exists():
                                    filename = file.filename.rsplit('.', 1)
                                    if len(filename) == 1:
                                        fl.name = f'{filename[0]}_{msg.uid}'
                                    else:
                                        fl.name = f'{filename[0]}_{msg.uid}.{filename[1]}'
                                fl.owner = self.request.user
                                fl.updated_by = self.request.user
                                fl.updated_at = msg.date
                                myfile = ContentFile(file.payload)
                                fl.file.save(file.filename, myfile)
                                fl.save()
                                eml.files.add(fl)

                        eml.save()
                except Exception as e:
                    print(e)

        with MailBox('imap.gmail.com').login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD,
                                             'INBOX') as mailbox:

            get_emails(True)
            # mailbox.folder.set('[Gmail]/Надіслані')
            mailbox.folder.set('[Gmail]/Отправленные')
            get_emails(False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['task_thread'] = TASK_THREAD
        return context


def reload_folders_view(request):
    context = {}
    project_id = request.POST["project_id"]
    context["folder"] = [
        {'id': -1, 'name': '---------'}
    ]
    context["file_list"] = [
        {'id': -1, 'name': '---------'}
    ]

    folders = Folder.objects.filter(project_id=project_id).values("id", "name")
    if folders:
        context["folder"].extend(list(folders))
        folder = folders[0]
        files = File.objects.filter(folder_id=folder["id"]).values("id", "name")
        if files:
            context["file_list"].extend(list(files))
    else:
        files = File.objects.filter(project_id=project_id).values("id", "name")
        if files:
            context["file_list"].extend(list(files))

    return JsonResponse(context)


def reload_files_view(request):
    context = {}
    folder_id = request.POST["folder_id"]
    context["file_list"] = [
        {'id': -1, 'name': '---------'}
    ]

    files = File.objects.filter(folder_id=folder_id).values("id", "name")
    if files:
        context["file_list"].extend(list(files))

    return JsonResponse(context)


def reload_messages_view(request):
    context = {}
    project_id = request.POST["project_id"]
    folder_id = request.POST["folder_id"]

    # if project_id == '':
    #     project_id = None
    # if folder_id == '':
    #     folder_id = None
    elements = [project_id, folder_id]
    for i in range(len(elements)):
        elements[i] = None if elements[i] == '' else elements[i]

    project_id, folder_id = elements
    project = Project.objects.filter(id=project_id)
    folder = None
    if project:
        project = project.first()
        folder = Folder.objects.filter(id=folder_id)
        if folder:
            folder = folder.first()

    x = get_messages_folder(project, folder)
    # x1 = render(request, 'emails/tags/message_list.html', x)
    response = render_to_string('emails/tags/message_list.html', x)

    return JsonResponse({"messages": response})


class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer

    # permission_classes = [IsAuthenticated, IsMembers]

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsMembers])
    def set_topic(self, request, pk=None):
        message = self.get_object()
        message.topic += 'added'
        # message.save()
        return Response({'status': status.HTTP_200_OK, 'message': 'topic added'})


class MessageListView(ProjectCustomPermissionMixin, generic.ListView):
    one_of_permission = ('admin', 'designer')
    template_name = 'emails/messages.html'

    # context_object_name = 'messages'

    def get_queryset(self):
        return Message.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # context['is_incoming'] = self.request.GET.get('is_incoming', 'True')
        context.update({'is_incoming': self.request.GET.get('is_incoming', 'True')})
        is_incoming = self.kwargs.get('is_incoming', 'in')
        # if is_incoming == 'in':
        #     context['is_incoming'] = True
        # else:
        #     context['is_incoming'] = False
        context.update({'is_incoming': True if is_incoming == 'in' else False})
        messages = []
        for msg in Message.objects.filter(is_incoming=context['is_incoming']):
            email_to_list = msg.email_to.all().values_list('email', flat=True)
            email_to_list = ', '.join(email_to_list)
            files = msg.files.all().values_list('name', flat=True)
            files = ', '.join(files)
            msg1 = {
                'email_from': msg.email_from,
                'topic': msg.topic,
                'text': msg.text,
                'created': msg.created,
                'files': files,
                'email_to': email_to_list,
                'uid': msg.uid_host,

            }
            messages.append(msg1)
        messages.sort(key=lambda x: x['created'], reverse=True)
        # context['messages1'] = messages
        context.update({'messages1': messages})
        return context


class MessageListTransferView(ProjectCustomPermissionMixin, generic.ListView):
    one_of_permission = ('admin', 'designer')
    template_name = 'emails/transfer_messages.html'
    model = Message

    # context_object_name = 'messages'

    # def get_queryset(self):
    #     # project_id = self.kwargs.get('project_id')
    #     # folder_id = self.kwargs.get('folder_id')
    #     # return Message.objects.filter(project_id=-1, folder_id=-1)

    def post(self, request, *args, **kwargs):
        project_id = request.POST.get('project_from')
        folder_id = request.POST.get('folder_from')
        project_id_to = request.POST.get('project_to')
        folder_id_to = request.POST.get('folder_to')
        inp_messages = request.POST.getlist('inp_messages')

        # if project_id == '' or project_id == '-1':
        #     project_id = None
        # if folder_id == '' or folder_id == '-1':
        #     folder_id = None
        # if project_id_to == '' or project_id_to == '-1':
        #     project_id_to = None
        # if folder_id_to == '' or folder_id_to == '-1':
        #     folder_id_to = None
        elements = [project_id, folder_id, project_id_to, folder_id_to]
        for i in range(len(elements)):
            elements[i] = None if elements[i] == '' or elements[i] == '-1' else elements[i]

        project_id, folder_id, project_id_to, folder_id_to = elements
        project_to = Project.objects.filter(id=project_id_to)
        folder_to = Folder.objects.filter(id=folder_id_to)

        if project_to:
            project_to = project_to.first()
            if folder_to:
                folder_to = folder_to.first()
            else:
                folder_to = None

            for msg_id in inp_messages:
                # msg = Message.objects.filter(id=msg_id)
                # if msg:
                #     msg = msg.first()
                #     msg.project = project_to
                #     msg.folder = folder_to
                #     msg.save()
                #
                #     files = msg.files.all()
                #     if files:
                #         files_transfer1(files, project_id_to, folder_id_to)
                msg_processing(msg_id, project_to, folder_to, project_id_to, folder_id_to)

        if folder_id:
            return redirect('folder_detail', project_id=project_id, pk=folder_id)
        if project_id:
            return redirect('project_detail', pk=project_id)
        return redirect('projects')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        project_id = self.request.GET.get('project_id')
        folder_id = self.request.GET.get('folder_id')

        # if project_id == '':
        #     project_id = None
        # if folder_id == '':
        #     folder_id = None
        elements = [project_id, folder_id]
        for i in range(len(elements)):
            elements[i] = None if elements[i] == '' else elements[i]

        project_id, folder_id = elements

        project = Project.objects.filter(id=project_id)
        folder = None
        if project:
            project = project.first()
            context.update({'project': project,
                            'url': reverse('project_detail', kwargs={'pk': project_id})})

            folder = Folder.objects.filter(id=folder_id)
            if folder:
                folder = folder.first()
                context.update({'folder': folder,
                                'url': reverse('folder_detail', kwargs={'project_id': project_id, 'pk': folder_id})})
            else:
                context.update({'folder': None})
        else:
            context.update({'project': None,
                            'folder': None})

        form = MessageTransferForm()
        if project:
            form.fields['project_from'].initial = project
            form.fields['folder_from'].queryset = Folder.objects.filter(project_id=project_id)
        if folder:
            form.fields['folder_from'].initial = folder
        context.update({'form': form})

        return context


def send_eml(request):
    user = request.user
    project_id = request.POST.get('project_id', None)
    folder_id = request.POST.get('folder_id', None)
    txt = request.POST.get('txt', None)
    topic = ''
    suffix = '~&'
    if project_id:
        project = Project.objects.get(pk=project_id)
        topic = f'{project.name}'
        suffix += project_id
    if folder_id:
        folder = Folder.objects.get(pk=folder_id)
        topic += f'. {folder.name}'
        suffix += f'.{folder_id}'
    topic += suffix

    email_to = list(Project.objects.get(pk=project_id).members.all().values_list('email', flat=True))
    email_from = user.email
    email_to.remove(email_from)

    msg = EmailMessageUtils(topic=topic, text=txt, email_from=email_from, email_to=email_to)
    msg.send()

    SendEmailView(request=request).load_emails()

    if folder_id:
        return redirect("folder_detail", project_id=project_id, pk=folder_id)
    if project_id:
        return redirect("project_detail", pk=project_id)
    return redirect("project_detail", pk=35)


def _load_emails(request):
    em = SendEmailView()
    em.request = request

    while True:
        em.load_emails()
        # print('[TASK] load emails - ok      sleep 60 sec')
        time.sleep(60)


def task_thread(request):
    global TASK_THREAD
    TASK_THREAD = True

    # user = AppUser.objects.filter(username='admin')[0]
    # # project = Project.objects.create(name='GoogleDriveTransfer1', owner=user, updated_by=user, is_public=True)
    # # project_id = project.id
    #
    # project_id = 7
    # project = Project.objects.get(pk=project_id)
    #
    # folder = Folder.objects.create(name='Ci', owner=user, project=project, updated_by=user, parent_folder=None, is_public=True)
    # folder_id = folder.id
    #
    # folder1 = Folder.objects.create(name='MT5', owner=user, project=project, updated_by=user, parent_folder=folder,  is_public=True)

    t = threading.Thread(target=parser_bd)
    t.start()

    t1 = threading.Thread(target=_load_emails, args=(request,))
    t1.start()

    # t2 = threading.Thread(target=create_files, args=(request, ['ТЕХВАГОНМАШ', 'Транспроект', 'ФРАКДЖЕТ-ТУЛЗ', 'ФосАгро']))
    # t2.start()
    #
    # t3 = threading.Thread(target=create_files, args=(request, ['Холодный склад', 'Чайка Лаб', 'Читинские ключи', 'Юрист UA']))
    # t3.start()

    return redirect("send_email")


def task_thread2(request):
    create_files1(request)
    return redirect("send_email")


def task_thread1(request):
    global TASK_THREAD
    TASK_THREAD = True

    # set_messages_proj_fold()

    t = threading.Thread(target=parser_bd)
    t.start()

    t1 = threading.Thread(target=_load_emails, args=(request,))
    t1.start()

    # t2 = threading.Thread(target=start_parse_prozorro)
    # t2.start()

    return redirect("send_email")


def set_messages_proj_fold():
    messages = Message.objects.all()
    for eml in messages:
        user = AppUser.objects.filter(email=eml.email_from)
        if user.exists():
            user = user[0]
        else:
            user = AppUser.objects.get(username='info@grand.engineering')
            # user = AppUser.objects.get(username='admin')

        fold = None
        proj = None
        proj_folder_id = eml.topic.rsplit('~&', 1)
        if len(proj_folder_id) == 2:
            proj_folder_id = proj_folder_id[1].split('.')
            if len(proj_folder_id) == 2:
                project_id = proj_folder_id[0]
                folder_id = proj_folder_id[1]
                proj = Project.objects.get(pk=project_id)
                fold = Folder.objects.get(pk=folder_id)
            else:
                project_id = proj_folder_id[0]
                proj = Project.objects.get(pk=project_id)
        else:
            project = Project.objects.filter(members__in=[user]).first()
            if project:
                proj = project
            else:
                proj = Project.objects.get(pk=35)
                fold = Folder.objects.get(pk=461)

        if proj:
            eml.project = proj
        if fold:
            eml.folder = fold
        eml.save()
