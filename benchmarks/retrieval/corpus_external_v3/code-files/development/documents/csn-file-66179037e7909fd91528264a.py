import requests
import pprint
import json
import xmltodict
import xml.etree.ElementTree as ET
import sys
import time
import pandas as pd
from pandas.io.json import json_normalize
from sfquery import *

def get_reliabledictionary_list(client, application_name, service_name):
    
    cluster = Cluster.from_sfclient(client)
    service = cluster.get_application(application_name).get_service(service_name)
    for dictionary in service.get_dictionaries():
        print(dictionary.name)

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
    
def get_reliabledictionary_type_schema(client, application_name, service_name, dictionary_name, type_name, output_file=None):
    
    cluster = Cluster.from_sfclient(client)
    dictionary = cluster.get_application(application_name).get_service(service_name).get_dictionary(dictionary_name)
    result = json.dumps(dictionary.get_complex_type(type_name), indent=4)
    
    if (output_file == None):
        output_file = "{}-{}-{}-{}-type-output.json".format(application_name, service_name, dictionary_name, type_name)
    
    with open(output_file, "w") as output:
        output.write(result)
    print('Printed schema information to: ' + output_file)
    print(result)

def query_reliabledictionary(client, application_name, service_name, dictionary_name, query_string, partition_key=None, partition_id=None, output_file=None):
    
    cluster = Cluster.from_sfclient(client)
    dictionary = cluster.get_application(application_name).get_service(service_name).get_dictionary(dictionary_name)
    
    
    start = time.time()
    if (partition_id != None):
        result = dictionary.query(query_string, PartitionLookup.ID, partition_id)
    elif (partition_key != None):
        result = dictionary.query(query_string, PartitionLookup.KEY, partition_key)
    else:
        result = dictionary.query(query_string)
    
    if type(result) is str:
        print(result)
        return
    else:
        result = json.dumps(result.get("value"), indent=4)
    
    print("Query took " + str(time.time() - start) + " seconds")
    
    if (output_file == None):
        output_file = "{}-{}-{}-query-output.json".format(application_name, service_name, dictionary_name)
    
    with open(output_file, "w") as output:
        output.write(result)
    print()
    print('Printed output to: ' + output_file)
    print(result)
    
def execute_reliabledictionary(client, application_name, service_name, input_file):
    

    cluster = Cluster.from_sfclient(client)
    service = cluster.get_application(application_name).get_service(service_name)

    # call get service with headers and params
    with open(input_file) as json_file:
        json_data = json.load(json_file)
        service.execute(json_data)
    return
