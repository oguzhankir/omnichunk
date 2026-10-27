def publish():
    
    try:
        build_site(dev_mode=False, clean=True)
        click.echo('Deploying the site...')
        # call("firebase deploy", shell=True)
        call("rsync -avz -e ssh --progress %s/ %s" % (BUILD_DIR, CONFIG["scp_target"],), shell=True)
        if "cloudflare" in CONFIG and "purge" in CONFIG["cloudflare"] and CONFIG["cloudflare"]["purge"]:
            do_purge()
    except (KeyboardInterrupt, SystemExit):
        raise
        sys.exit(1)
