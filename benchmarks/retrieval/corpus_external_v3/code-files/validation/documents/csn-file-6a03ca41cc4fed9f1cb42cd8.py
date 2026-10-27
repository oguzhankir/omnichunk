from ctypes import *

from bacon.core import lib
from bacon import native
from bacon import resource
import bacon.image
import bacon.text

class FontMetrics(object):
    

    def __init__(self, ascent, descent):
        self._ascent = ascent
        self._descent = descent

    @property
    def descent(self):
        
        return self._descent

    @property
    def ascent(self):
        
        return self._ascent

class Glyph(object):
    
    def __init__(self, char, image, offset_x, offset_y, advance):
        self._char = char
        self._image = image
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._advance = advance

    @property
    def char(self):
        
        return self._char

    @property
    def image(self):
        
        return self._image

    @property
    def offset_x(self):
        
        return self._offset_x

    @property
    def offset_y(self):
        
        return self._offset_y

    @property
    def advance(self):
        
        return self._advance

class _FontFile(object):
    _font_files = {}
    _default_font_file = None

    _handle = -1

    def __init__(self, file, handle=None):
        if not handle:
            handle = c_int()
            lib.LoadFont(byref(handle), resource.get_resource_path(file).encode('utf-8'))
            self._handle = handle.value
        else:
            self._handle = handle

    def __del__(self):
        self.unload()

    def unload(self):
        if self._handle != -1:
            lib.UnloadFont(self._handle)
            self._handle = -1

    def get_metrics(self, size):
        ascent = c_int()
        descent = c_int()
        lib.GetFontMetrics(self._handle, size, byref(ascent), byref(descent))
        return FontMetrics(-ascent.value, -descent.value)

    def get_glyph(self, size, content_scale, char, flags):
        image_handle = c_int()
        offset_x = c_int()
        offset_y = c_int()
        advance = c_int()
        lib.GetGlyph(self._handle, size * content_scale, ord(char), flags,
            byref(image_handle), byref(offset_x), byref(offset_y), byref(advance))

        if image_handle.value:
            width = c_int()
            height = c_int()
            lib.GetImageSize(image_handle, byref(width), byref(height))
            image = bacon.image.Image(width = width.value / content_scale, 
                                      height = height.value / content_scale, 
                                      content_scale = content_scale,
                                      handle = image_handle.value)
        else:
            image = None

        return Glyph(char, 
                     image, 
                     round(offset_x.value) / content_scale, 
                     round(offset_y.value) / content_scale, 
                     round(advance.value) / content_scale)

    @classmethod
    def get_font_file(cls, file):
        try:
            return cls._font_files[file]
        except KeyError:
            ff = _FontFile(file)
            cls._font_files[file] = ff
            return ff

    @classmethod
    def get_default_font_file(cls):
        if not cls._default_font_file:
            handle = c_int()
            lib.GetDefaultFont(byref(handle))
            cls._default_font_file = _FontFile(file=None, handle=handle)
        return cls._default_font_file

class Font(object):
    
    def __init__(self, file, size, light_hinting=False, content_scale=None):
        if type(file) is _FontFile:
            self._font_file = file
        elif file is None:
            self._font_file = _FontFile.get_default_font_file()
        else:
            self._font_file = _FontFile.get_font_file(file)
        
        self._size = size

        if content_scale is None:
            content_scale = bacon.window.content_scale
        self._content_scale = content_scale
        
        self._glyphs = { }
        self._flags = 0

        if light_hinting:
            self._flags |= native.FontFlags.light_hinting

        self._metrics = self._font_file.get_metrics(size)

    @property
    def metrics(self):
        
        return self._metrics

    @property
    def ascent(self):
        
        return self._metrics.ascent

    @property
    def descent(self):
        
        return self._metrics.descent

    def get_glyph(self, char):
        
        try:
            return self._glyphs[char]
        except KeyError:
            glyph = self._font_file.get_glyph(self._size, self._content_scale, char, self._flags)
            self._glyphs[char] = glyph
            return glyph

    def get_glyphs(self, str):
        
        return [self.get_glyph(c) for c in str]

    def measure_string(self, str):
        
        style = bacon.text.Style(self)
        run = bacon.text.GlyphRun(style, str)
        glyph_layout = bacon.text.GlyphLayout([run], 0, 0)
        return glyph_layout.content_width