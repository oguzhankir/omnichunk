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
