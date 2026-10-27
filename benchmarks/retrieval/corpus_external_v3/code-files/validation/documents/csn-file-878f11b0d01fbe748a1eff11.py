
from __future__ import unicode_literals

from PIL import Image

from django.core.files.uploadedfile import InMemoryUploadedFile

from ..settings import QUAL, VERSATILEIMAGEFIELD_PROGRESSIVE_JPEG
from ..utils import get_image_metadata_from_file_ext

EXIF_ORIENTATION_KEY = 274


class ProcessedImage(object):
    

    name = None
    url = None

    def __init__(self, path_to_image, storage, create_on_demand,
                 placeholder_image=None):
        
        self.path_to_image = path_to_image
        self.storage = storage
        self.create_on_demand = create_on_demand
        self.placeholder_image = placeholder_image

    def process_image(self, image, image_format, **kwargs):
        
        raise NotImplementedError(
            'Subclasses MUST provide a `process_image` method.'
        )

    def preprocess(self, image, image_format):
        
        save_kwargs = {'format': image_format}

        # Ensuring image is properly rotated
        if hasattr(image, '_getexif'):
            exif_datadict = image._getexif()  # returns None if no EXIF data
            if exif_datadict is not None:
                exif = dict(exif_datadict.items())
                orientation = exif.get(EXIF_ORIENTATION_KEY, None)
                if orientation == 3:
                    image = image.transpose(Image.ROTATE_180)
                elif orientation == 6:
                    image = image.transpose(Image.ROTATE_270)
                elif orientation == 8:
                    image = image.transpose(Image.ROTATE_90)

        # Ensure any embedded ICC profile is preserved
        save_kwargs['icc_profile'] = image.info.get('icc_profile')

        if hasattr(self, 'preprocess_%s' % image_format):
            image, addl_save_kwargs = getattr(
                self,
                'preprocess_%s' % image_format
            )(image=image)
            save_kwargs.update(addl_save_kwargs)

        return image, save_kwargs

    def preprocess_GIF(self, image, **kwargs):
        
        if 'transparency' in image.info:
            save_kwargs = {'transparency': image.info['transparency']}
        else:
            save_kwargs = {}
        return (image, save_kwargs)

    def preprocess_JPEG(self, image, **kwargs):
        
        save_kwargs = {
            'progressive': VERSATILEIMAGEFIELD_PROGRESSIVE_JPEG,
            'quality': QUAL
        }
        if image.mode != 'RGB':
            image = image.convert('RGB')
        return (image, save_kwargs)

    def retrieve_image(self, path_to_image):
        
        image = self.storage.open(path_to_image, 'rb')
        file_ext = path_to_image.rsplit('.')[-1]
        image_format, mime_type = get_image_metadata_from_file_ext(file_ext)

        return (
            Image.open(image),
            file_ext,
            image_format,
            mime_type
        )

    def save_image(self, imagefile, save_path, file_ext, mime_type):
        
        file_to_save = InMemoryUploadedFile(
            imagefile,
            None,
            'foo.%s' % file_ext,
            mime_type,
            imagefile.tell(),
            None
        )
        file_to_save.seek(0)
        self.storage.save(save_path, file_to_save)
