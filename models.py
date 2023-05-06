import os
import numpy as np
import cv2

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from . import utils


def get_upload_path(instance, filename):
    path = ''
    if getattr(settings, 'BUCKET_ROOT', None):
        path = settings.BUCKET_ROOT

    if instance.folder:
        path = os.path.join(path, instance.folder.get_full_path(), filename)
    else:
        path = os.path.join(path, str(instance.project_id), filename)

    return path


class AbstractFileModel(models.Model):
    name = models.CharField(_("Название"), max_length=255)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,
                              on_delete=models.SET_NULL,
                              null=True,
                              related_name="%(class)s_created")
    updated_at = models.DateTimeField(_("Дата последнего изменения"), auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.SET_NULL,
                                   null=True,
                                   blank=True,
                                   related_name="%(class)s_last_updated",
                                   )
    slug = models.SlugField(_("Публичная ссылка"), null=True, blank=True, db_index=True)
    is_public = models.BooleanField(_("Доступен неавторизированным"), default=True)
    size = models.PositiveBigIntegerField(_('Размер'), default=0)

    def __str__(self):
        return f"{self.name}"

    class Meta:
        abstract = True


class Project(AbstractFileModel):
    name = models.CharField(_("Название"), max_length=255, unique=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL,
                                     blank=True,
                                     related_name="projects", )

    class Meta:
        verbose_name = _('Проект')
        verbose_name_plural = _('Проекты')
        ordering = ['name']

    # def get_absolute_url(self):
    #     return reverse('project_detail', kwargs={"pk": self.pk})
    #
    # def save(self, *args, **kwargs):
    #     size = self.files.aggregate(total=models.Sum('size'))['total']
    #     self.size = size if size else 0
    #     if not self.slug:
    #         self.slug = utils.unique_slug_generator(self)
    #
    #     super().save(*args, **kwargs)
    #
    # def get_public_link(self):
    #     url = None
    #     if self.slug:
    #         url = reverse('project_detail_slug', kwargs={"slug": self.slug})
    #     return url
    #
    # @classmethod
    # def used_space(cls):
    #     projects = cls.objects.all()
    #     size = projects.aggregate(total=models.Sum('size'))['total'] if projects.exists() else 0
    #     return size
    #
    # @classmethod
    # def used_space_percent(cls):
    #     size = cls.used_space()
    #
    #     if not StorageMaxSize.objects.all().exists():
    #         size_obj = StorageMaxSize.objects.create(max_size=settings.DEFAULT_STORAGE_SIZE).size
    #     elif StorageMaxSize.objects.count() > 1:
    #         size_obj = StorageMaxSize.objects.all()[0]
    #     else:
    #         size_obj = StorageMaxSize.objects.get()
    #     max_size = size_obj.max_size
    #
    #     try:
    #         percents = size * 100 // max_size
    #     except ZeroDivisionError:
    #         percents = 100
    #     percents = percents if percents <= 100 else 100
    #     return percents
    #
    # @staticmethod
    # def get_max_size():
    #     return StorageMaxSize.get_object().max_size

    # @property
    # def is_empty(self):
    #     return not self.folders.exists() and not self.files.exists()


class Folder(AbstractFileModel):
    parent_folder = models.ForeignKey('self', on_delete=models.CASCADE, related_name="folders", null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="folders", null=True)

    class Meta:
        verbose_name = _('Папка')
        verbose_name_plural = _('Папки')
        ordering = ['name']
        unique_together = (('project', 'parent_folder', 'name'),)

    # def get_absolute_url(self):
    #     return reverse('folder_detail', kwargs={"project_id": self.project_id, "pk": self.pk})
    #
    # def clean(self):
    #     if self.parent_folder and self.project != self.parent_folder.project:
    #         raise ValidationError((_("Папка {folder} не принадлежит проекту {project}")).
    #                               format(folder=self.parent_folder, project=self.project))
    #
    # def save(self, *args, **kwargs):
    #     rewrite_size = False
    #
    #     size = self.files.aggregate(total=models.Sum('size'))['total'] if self.files.exists() else 0
    #     size += self.folders.aggregate(total=models.Sum('size'))['total'] if self.folders.exists() else 0
    #     if self.size != size:
    #         rewrite_size = True
    #
    #     #TODO: updated_by
    #
    #     self.size = size
    #     if not self.slug:
    #         self.slug = utils.unique_slug_generator(self)
    #     super().save(*args, **kwargs)
    #
    #     if self.parent_folder:
    #         if rewrite_size or self.is_public:
    #             if self.is_public:
    #                 self.parent_folder.is_public = True
    #             self.parent_folder.save()
    #         self.parent_folder.save()
    #     else:
    #         self.project.save()
    #
    # def get_public_link(self):
    #     url = None
    #     if self.slug:
    #         url = reverse('folder_detail_slug', kwargs={"project_id": self.project.slug, "slug": self.slug})
    #     return url
    #
    # def get_public_download_link(self):
    #     url = None
    #     if self.slug:
    #         if self.parent_folder:
    #             url = reverse('file_pub_download',
    #                           kwargs={"slug": self.project.slug, "folder_id": self.parent_folder.slug})
    #         else:
    #             url = reverse('file_pub_download', kwargs={"slug": self.project.slug})
    #         url += f'?dir={self.slug}'
    #     return url
    #
    # def get_full_path(self):
    #     path = ''
    #     if self.parent_folder:
    #         path = os.path.join(self.parent_folder.get_full_path(), str(self.id))
    #     else:
    #         path = os.path.join(str(self.project_id), str(self.id))
    #
    #     return path
    #
    # def get_norm_path(self):
    #     path = ''
    #     if self.parent_folder:
    #         path = os.path.join(self.parent_folder.get_norm_path(), str(self.name))
    #     else:
    #         path = os.path.join(str(self.project.name), str(self.name))
    #
    #     return path
    #
    # def check_shared(self):
    #     shared = all([file.is_public for file in self.files.all()])
    #     if self.folders:
    #         shared = shared and all(folder.check_shared() for folder in self.folders.all())
    #
    #     return shared

    # @property
    # def is_empty(self):
    #     return not self.folders.exists() and not self.files.exists()


class File(AbstractFileModel):
    EXT_ICO = {
        'xls': 'Excel_icon.png',
        'xlsx': 'Excel_icon.png',
        'doc': 'Word_icon.png',
        'docx': 'Word_icon.png',
        'zip': 'Zip, rar icon.png',
        'rar': 'Zip, rar icon.png',
        '7z': 'Zip, rar icon.png',
        'pdf': 'pdf.png',
        'txt': 'txt.png',
    }

    preview_ext = [
        'pdf',
    ]

    file = models.FileField(_("Файл"), upload_to=get_upload_path)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="files")
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name="files", null=True, blank=True)

    class Meta:
        verbose_name = _('Файл')
        verbose_name_plural = _('Файлы')
        ordering = ['name']
        unique_together = (('project', 'folder', 'name'),)

    # def clean(self):
    #     if self.folder and self.project != self.folder.project:
    #         raise ValidationError((_("Папка {folder} не принадлежит проекту {project}")).
    #                               format(folder=self.folder, project=self.project))
    #
    # def save(self, *args, **kwargs):
    #     proj = self.project
    #     self.size = self.file.size  # copy filesize in separate field
    #     if not self.slug:
    #         self.slug = utils.unique_slug_generator(self)  # generating public link
    #     super().save(*args, **kwargs)
    #
    #     if self.is_public:
    #         proj.is_public = True
    #     elif not proj.files.filter(is_public=True).exists():
    #         proj.is_public = False
    #
    #     proj.updated_by = self.updated_by
    #     proj.save()
    #
    #     folder = self.folder
    #     if folder:
    #         folder.updated_by = self.updated_by
    #         if self.is_public:
    #             folder.is_public = True
    #         elif not folder.files.filter(is_public=True).exists() and \
    #                 not folder.folders.filter(is_public=True).exists():
    #             self.folder.is_public = False
    #
    #         folder.save()
    #
    # def get_absolute_url(self):
    #     if self.folder:
    #         url = reverse('folder_detail', kwargs={"project_id": self.project_id, "pk": self.folder_id})
    #     else:
    #         url = reverse('project_detail', kwargs={"pk": self.project_id})
    #     return url
    #
    # def get_public_link(self):
    #     url = None
    #     if self.slug:
    #         if self.folder:
    #             url = reverse('file_pub_download',
    #                           kwargs={"slug": self.project.slug, "folder_id": self.folder.slug})
    #         else:
    #             url = reverse('file_pub_download', kwargs={"slug": self.project.slug})
    #         url += f'?obj={self.slug}'
    #     return url
    #
    # @staticmethod
    # def _create_preview_from_im(img, video=False):
    #     cut_to_width, cut_to_height = 20, 20
    #     im = Image.open(img) if not video else Image.fromarray(img)
    #     width, height = im.size
    #     left = (width - height) // 2 if width > height else 0
    #     top = (height - width) // 2 if height > width else 0
    #     right = width - left if width > height else width
    #     bottom = height - top if height > width else height
    #     new_im = im.crop((left, top, right, bottom))
    #     new_im.thumbnail((20, 20))
    #     if video:
    #         static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
    #         ico_path = os.path.join('images', 'content_type')
    #         video_ico = os.path.join(static_dir, ico_path, 'video.png')
    #
    #         play_img = Image.open(video_ico)
    #         width_play, height_play = play_img.size
    #         start_w, start_h = (cut_to_width - width_play)//2, (cut_to_height - height_play)//2
    #
    #         new_im.paste(play_img, (start_w, start_h), play_img)
    #
    #     return new_im
    #
    # def image_preview_create(self, path):
    #     static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
    #     # im = Image.open(self.file.path)
    #     im = self._create_preview_from_im(self.file)
    #
    #     path = os.path.join(static_dir, path)
    #     preview_dir = os.path.split(path)[0]
    #     if not os.path.exists(preview_dir):
    #         os.makedirs(preview_dir)
    #
    #     im.save(path, 'png')
    #
    #     return path
    #
    # def vid_preview_create(self, path):
    #     static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
    #     # im = Image.open(self.file.path)
    #
    #     vidcap = cv2.VideoCapture(self.file.url)
    #     # success, image = vidcap.read()
    #     # length = int(vidcap.get(cv2.CAP_PROP_FRAME_COUNT))
    #     # print(length)
    #     ret, frame = vidcap.read()
    #
    #     if ret and frame is not None:
    #         im = self._create_preview_from_im(frame, video=True)
    #     else:
    #         im = self._create_preview_from_im(np.zeros((512, 512, 3), np.uint8), video=True)
    #
    #     path = os.path.join(static_dir, path)
    #     preview_dir = os.path.split(path)[0]
    #     if not os.path.exists(preview_dir):
    #         os.makedirs(preview_dir)
    #     im.save(path, 'png')
    #
    #     # count = 0
    #     # success = True
    #     # while success:
    #     #     cv2.imwrite("frame%d.jpg" % count, image)  # save frame as JPEG file
    #     #     success, image = vidcap.read()
    #     #     count += 1
    #     #     vidcap.set(cv2.CAP_PROP_POS_FRAMES, count * 10)
    #
    #     return path
    #
    # def get_ico(self):
    #     static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
    #     ico_path = os.path.join('images', 'content_type')
    #     default_ico = os.path.join(ico_path, 'unknown.png')
    #     extension = self.get_ext()
    #
    #     if extension in ('jpg', 'jpeg', 'png', ):
    #         file_path = os.path.join(ico_path, "preview", f"{self.id}_ico.png")
    #         if not os.path.exists(os.path.join(static_dir, file_path)):
    #             self.image_preview_create(file_path)
    #         ico = file_path
    #     elif extension in ('avi', 'asf', 'mp4', 'm4v', 'mov', 'mpg', 'mpeg', 'wmv'):
    #         file_path = os.path.join(ico_path, "preview", f"{self.id}_ico.png")
    #         if not os.path.exists(os.path.join(static_dir, file_path)):
    #             self.vid_preview_create(file_path)
    #
    #         if not os.path.exists(os.path.join(static_dir, file_path)):
    #             ico = os.path.join(ico_path, 'Video_icon.png')
    #         else:
    #             ico = file_path
    #         # ico = os.path.join(ico_path, 'Video_icon.png')
    #     else:
    #         ico = os.path.join(ico_path, self.EXT_ICO.get(extension)) if self.EXT_ICO.get(extension) else default_ico
    #
    #     return ico
    #
    # def get_norm_path(self):
    #     if self.folder:
    #         path = os.path.join(self.folder.get_norm_path(), self.name)
    #     else:
    #         path = os.path.join(self.project.name, self.name)
    #
    #     return path
    #
    # def get_norm_url(self):
    #     url = self.file.url
    #
    #     return url.split('?')[0]
    #
    # def get_ext(self):
    #     extension = self.name.split('.')[-1].lower() if len(self.name.split('.')) > 1 else None
    #
    #     return extension

    # @property
    # def has_preview(self):
    #
    #     return self.get_ext() in self.preview_ext


class StorageMaxSize(models.Model):
    max_size = models.PositiveBigIntegerField(_("Размер хранилища"))

    @classmethod
    def get_object(cls):
        if not cls.objects.all().exists():
            obj = cls.objects.create(max_size=settings.DEFAULT_STORAGE_SIZE)
        elif cls.objects.count() > 1:
            obj = cls.objects.all()[0]
        else:
            obj = cls.objects.get()
        return obj


@receiver(post_delete,  sender=File)
def delete_file_hook(sender, instance, using, **kwargs):
    # storage, path = instance.file.storage, instance.file.path
    # storage.delete(path)
    storage = instance.file.storage
    if storage.exists(instance.file.name):
        storage.delete(instance.file.name)
        instance.project.save()

    if instance.folder_id and Folder.objects.filter(id=instance.folder_id).exists():
        instance.folder.save()


@receiver(post_delete, sender=Folder)
def delete_folder_hook(sender, instance, using, **kwargs):
    if instance.parent_folder_id and Folder.objects.filter(id=instance.parent_folder_id).exists():
        instance.parent_folder.save()
