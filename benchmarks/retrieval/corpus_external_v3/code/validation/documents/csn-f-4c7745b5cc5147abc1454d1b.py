def find_apps(self, templates=None):
        

        all_apps = OrderedDict()

        if not templates:
            all_files = self.discover_templates()
            for tpl_name, fp in all_files:
                # this is the most performant - a testcase that used the loader with tpl_name
                # was about 8x slower for a project with ~5 apps in different templates :(
                with io.open(fp, 'r', encoding=settings.FILE_CHARSET) as template_file:
                    src_data = template_file.read()

                for t in Lexer(src_data).tokenize():
                    if t.token_type == TOKEN_BLOCK:
                        imatch = SYSTEMJS_TAG_RE.match(t.contents)
                        if imatch:
                            all_apps.setdefault(tpl_name, [])
                            all_apps[tpl_name].append(imatch.group('app'))
        else:
            for tpl_name in templates:
                try:
                    template = loader.get_template(tpl_name)
                except TemplateDoesNotExist:
                    raise CommandError('Template \'%s\' does not exist' % tpl_name)
                import_nodes = template.template.nodelist.get_nodes_by_type(SystemImportNode)
                for node in import_nodes:
                    app = node.path.resolve(RESOLVE_CONTEXT)
                    if not app:
                        self.stdout.write(self.style.WARNING(
                            '{tpl}: Could not resolve path with context {ctx}, skipping.'.format(
                                tpl=tpl_name, ctx=RESOLVE_CONTEXT)
                        ))
                        continue
                    all_apps.setdefault(tpl_name, [])
                    all_apps[tpl_name].append(app)

        return all_apps
