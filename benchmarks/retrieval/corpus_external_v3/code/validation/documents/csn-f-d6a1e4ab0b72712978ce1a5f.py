def  add_markup( self ):
        
        if self.markup and self.markup_lines:

            # get rid of last line of markup if it's empty
            marks = self.markup_lines
            if len( marks ) > 0 and not string.strip( marks[-1] ):
                self.markup_lines = marks[:-1]

            m = DocMarkup( self.markup, self.markup_lines )

            self.markups.append( m )

            self.markup       = None
            self.markup_lines = []
