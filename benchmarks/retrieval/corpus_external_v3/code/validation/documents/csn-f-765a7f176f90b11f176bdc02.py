def  make_html_code( self, lines ):
        
        line = code_header + '\n'
        for l in lines:
            line = line + html_quote( l ) + '\n'

        return line + code_footer
