def write():
    
    click.echo("Fantastic. Let's get started. ")
    title = click.prompt("What's the title?")

    # Make sure that title doesn't exist.
    url = slugify(title)
    url = click.prompt("What's the URL?", default=url)

    # Make sure that title doesn't exist.
    click.echo("Got it. Creating %s..." % url)
    scaffold_piece(title, url)
