def get_first():
    
    client = po.connect() # this depends on the DIGITALOCEAN_API_KEY envvar
    all_droplets = client.droplets.list()
    id = all_droplets[0]['id'] # I'm cheating because I only have one droplet
    return client.droplets.get(id)
