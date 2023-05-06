import os
import cv2
from PIL import Image
from django.urls import reverse
from django.db import models
from projects.models import Project, StorageMaxSize, Folder, File
from . import utils
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import numpy as np


class ProjectService:
    obj: Project = None

    def __init__(self, obj_project: Project):
        self.obj = obj_project

    def get_absolute_url(self):
        return reverse('project_detail', kwargs={"pk": self.obj.pk})

    def save(self, *args, **kwargs):
        size = self.obj.files.aggregate(total=models.Sum('size'))['total']
        self.obj.size = size if size else 0
        if not self.obj.slug:
            self.obj.slug = utils.unique_slug_generator(self.obj)

        super().save(*args, **kwargs)

    def get_public_link(self):
        url = None
        if self.obj.slug:
            url = reverse('project_detail_slug', kwargs={"slug": self.obj.slug})
        return url

    @staticmethod
    def used_space():
        projects = Project.objects.all()
        size = projects.aggregate(total=models.Sum('size'))['total'] if projects.exists() else 0
        return size

    def used_space_percent(self):
        size = self.used_space()

        if not StorageMaxSize.objects.all().exists():
            size_obj = StorageMaxSize.objects.create(max_size=settings.DEFAULT_STORAGE_SIZE).size
        elif StorageMaxSize.objects.count() > 1:
            size_obj = StorageMaxSize.objects.all()[0]
        else:
            size_obj = StorageMaxSize.objects.get()
        max_size = size_obj.max_size

        try:
            percents = size * 100 // max_size
        except ZeroDivisionError:
            percents = 100
        percents = percents if percents <= 100 else 100
        return percents

    @staticmethod
    def get_max_size():
        return StorageMaxSize.get_object().max_size

    @property
    def is_empty(self):
        return not self.obj.folders.exists() and not self.obj.files.exists()


class FolderService:
    obj: Folder = None

    def __init__(self, obj_folder: Folder):
        self.obj = obj_folder

    def get_absolute_url(self):
        return reverse('folder_detail', kwargs={"project_id": self.obj.project_id, "pk": self.obj.pk})

    def clean(self):
        if self.obj.parent_folder and self.obj.project != self.obj.parent_folder.project:
            raise ValidationError((_("Папка {folder} не принадлежит проекту {project}")).
                                  format(folder=self.obj.parent_folder, project=self.obj.project))

    def save(self, *args, **kwargs):
        rewrite_size = False

        size = self.obj.files.aggregate(total=models.Sum('size'))['total'] if self.obj.files.exists() else 0
        size += self.obj.folders.aggregate(total=models.Sum('size'))['total'] if self.obj.folders.exists() else 0
        if self.obj.size != size:
            rewrite_size = True

        #TODO: updated_by

        self.obj.size = size
        if not self.obj.slug:
            self.obj.slug = utils.unique_slug_generator(self.obj)
        super().save(*args, **kwargs)

        if self.obj.parent_folder:
            if rewrite_size or self.obj.is_public:
                if self.obj.is_public:
                    self.obj.parent_folder.is_public = True
                self.obj.parent_folder.save()
            self.obj.parent_folder.save()
        else:
            self.obj.project.save()

    def get_public_link(self):
        url = None
        if self.obj.slug:
            url = reverse('folder_detail_slug', kwargs={"project_id": self.obj.project.slug, "slug": self.obj.slug})
        return url

    def get_public_download_link(self):
        url = None
        if self.obj.slug:
            if self.obj.parent_folder:
                url = reverse('file_pub_download',
                              kwargs={"slug": self.obj.project.slug, "folder_id": self.obj.parent_folder.slug})
            else:
                url = reverse('file_pub_download', kwargs={"slug": self.obj.project.slug})
            url += f'?dir={self.obj.slug}'
        return url

    def get_full_path(self):
        path = ''
        if self.obj.parent_folder:
            path = os.path.join(self.obj.parent_folder.get_full_path(), str(self.obj.id))
        else:
            path = os.path.join(str(self.obj.project_id), str(self.obj.id))

        return path

    def get_norm_path(self):
        path = ''
        if self.obj.parent_folder:
            path = os.path.join(self.obj.parent_folder.get_norm_path(), str(self.obj.name))
        else:
            path = os.path.join(str(self.obj.project.name), str(self.obj.name))

        return path

    def check_shared(self):
        shared = all([file.is_public for file in self.obj.files.all()])
        if self.obj.folders:
            shared = shared and all(folder.check_shared() for folder in self.obj.folders.all())

        return shared

    @property
    def is_empty(self):
        return not self.obj.folders.exists() and not self.obj.files.exists()


class FileService:
    obj: File = None

    def __init__(self, obj_file: File):
        self.obj = obj_file

    def clean(self):
        if self.obj.folder and self.obj.project != self.obj.folder.project:
            raise ValidationError((_("Папка {folder} не принадлежит проекту {project}")).
                                  format(folder=self.obj.folder, project=self.obj.project))

    def save(self, *args, **kwargs):
        proj = self.obj.project
        self.obj.size = self.obj.file.size  # copy filesize in separate field
        if not self.obj.slug:
            self.obj.slug = utils.unique_slug_generator(self.obj)  # generating public link
        super().save(*args, **kwargs)

        if self.obj.is_public:
            proj.is_public = True
        elif not proj.files.filter(is_public=True).exists():
            proj.is_public = False

        proj.updated_by = self.obj.updated_by
        proj.save()

        folder = self.obj.folder
        if folder:
            folder.updated_by = self.obj.updated_by
            if self.obj.is_public:
                folder.is_public = True
            elif not folder.files.filter(is_public=True).exists() and \
                    not folder.folders.filter(is_public=True).exists():
                self.obj.folder.is_public = False

            folder.save()

    def get_absolute_url(self):
        if self.obj.folder:
            url = reverse('folder_detail', kwargs={"project_id": self.obj.project_id, "pk": self.obj.folder_id})
        else:
            url = reverse('project_detail', kwargs={"pk": self.obj.project_id})
        return url

    def get_public_link(self):
        url = None
        if self.obj.slug:
            if self.obj.folder:
                url = reverse('file_pub_download',
                              kwargs={"slug": self.obj.project.slug, "folder_id": self.obj.folder.slug})
            else:
                url = reverse('file_pub_download', kwargs={"slug": self.obj.project.slug})
            url += f'?obj={self.obj.slug}'
        return url

    @staticmethod
    def _create_preview_from_im(img, video=False):
        cut_to_width, cut_to_height = 20, 20
        im = Image.open(img) if not video else Image.fromarray(img)
        width, height = im.size
        left = (width - height) // 2 if width > height else 0
        top = (height - width) // 2 if height > width else 0
        right = width - left if width > height else width
        bottom = height - top if height > width else height
        new_im = im.crop((left, top, right, bottom))
        new_im.thumbnail((20, 20))
        if video:
            static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
            ico_path = os.path.join('images', 'content_type')
            video_ico = os.path.join(static_dir, ico_path, 'video.png')

            play_img = Image.open(video_ico)
            width_play, height_play = play_img.size
            start_w, start_h = (cut_to_width - width_play)//2, (cut_to_height - height_play)//2

            new_im.paste(play_img, (start_w, start_h), play_img)

        return new_im

    def image_preview_create(self, path):
        static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
        # im = Image.open(self.file.path)
        im = self._create_preview_from_im(self.obj.file)

        path = os.path.join(static_dir, path)
        preview_dir = os.path.split(path)[0]
        if not os.path.exists(preview_dir):
            os.makedirs(preview_dir)

        im.save(path, 'png')

        return path

    def vid_preview_create(self, path):
        static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
        # im = Image.open(self.file.path)

        vidcap = cv2.VideoCapture(self.obj.file.url)
        # success, image = vidcap.read()
        # length = int(vidcap.get(cv2.CAP_PROP_FRAME_COUNT))
        # print(length)
        ret, frame = vidcap.read()

        if ret and frame is not None:
            im = self._create_preview_from_im(frame, video=True)
        else:
            im = self._create_preview_from_im(np.zeros((512, 512, 3), np.uint8), video=True)

        path = os.path.join(static_dir, path)
        preview_dir = os.path.split(path)[0]
        if not os.path.exists(preview_dir):
            os.makedirs(preview_dir)
        im.save(path, 'png')

        # count = 0
        # success = True
        # while success:
        #     cv2.imwrite("frame%d.jpg" % count, image)  # save frame as JPEG file
        #     success, image = vidcap.read()
        #     count += 1
        #     vidcap.set(cv2.CAP_PROP_POS_FRAMES, count * 10)

        return path

    def get_ico(self):
        static_dir = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATIC_DIR
        ico_path = os.path.join('images', 'content_type')
        default_ico = os.path.join(ico_path, 'unknown.png')
        extension = self.get_ext()

        if extension in ('jpg', 'jpeg', 'png', ):
            file_path = os.path.join(ico_path, "preview", f"{self.obj.id}_ico.png")
            if not os.path.exists(os.path.join(static_dir, file_path)):
                self.image_preview_create(file_path)
            ico = file_path
        elif extension in ('avi', 'asf', 'mp4', 'm4v', 'mov', 'mpg', 'mpeg', 'wmv'):
            file_path = os.path.join(ico_path, "preview", f"{self.obj.id}_ico.png")
            if not os.path.exists(os.path.join(static_dir, file_path)):
                self.vid_preview_create(file_path)

            if not os.path.exists(os.path.join(static_dir, file_path)):
                ico = os.path.join(ico_path, 'Video_icon.png')
            else:
                ico = file_path
            # ico = os.path.join(ico_path, 'Video_icon.png')
        else:
            ico = os.path.join(ico_path, self.obj.EXT_ICO.get(extension)) if self.obj.EXT_ICO.get(extension) else default_ico

        return ico

    def get_norm_path(self):
        if self.obj.folder:
            path = os.path.join(self.obj.folder.get_norm_path(), self.obj.name)
        else:
            path = os.path.join(self.obj.project.name, self.obj.name)

        return path

    def get_norm_url(self):
        url = self.obj.file.url

        return url.split('?')[0]

    def get_ext(self):
        extension = self.obj.name.split('.')[-1].lower() if len(self.obj.name.split('.')) > 1 else None

        return extension

    @property
    def has_preview(self):

        return self.get_ext() in self.obj.preview_ext
