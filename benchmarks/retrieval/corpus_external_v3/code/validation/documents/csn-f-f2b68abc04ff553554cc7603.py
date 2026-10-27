def publish(msg="checkpoint: publish package"):
    
    test = check()
    if test.succeeded:
        # clean()
        # push(msg)
        sdist = local("python setup.py sdist")
        if sdist.succeeded:
            build = local(
                'python setup.py build && python setup.py bdist_egg')
            if build.succeeded:
                upload = local("twine upload dist/*")
                if upload.succeeded:
                    tag()
