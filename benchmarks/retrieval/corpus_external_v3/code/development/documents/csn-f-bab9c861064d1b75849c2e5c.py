def get_reliabledictionary_schema(client, application_name, service_name, dictionary_name, output_file=None):
    
    cluster = Cluster.from_sfclient(client)
    dictionary = cluster.get_application(application_name).get_service(service_name).get_dictionary(dictionary_name)

    result = json.dumps(dictionary.get_information(), indent=4)

    if (output_file == None):
        output_file = "{}-{}-{}-schema-output.json".format(application_name, service_name, dictionary_name)

    with open(output_file, "w") as output:
        output.write(result)
    print('Printed schema information to: ' + output_file)
    print(result)
