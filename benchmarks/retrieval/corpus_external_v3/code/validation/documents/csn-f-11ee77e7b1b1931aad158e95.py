def measure_string(self, str):
        
        style = bacon.text.Style(self)
        run = bacon.text.GlyphRun(style, str)
        glyph_layout = bacon.text.GlyphLayout([run], 0, 0)
        return glyph_layout.content_width
