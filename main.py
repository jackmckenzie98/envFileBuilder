import os
import json

WORKING_PATH = os.path.dirname(__file__)
ARTIFACTS_PATH = os.path.join(WORKING_PATH, r'artifacts')
PROPERTIES_FILES_PATH = os.path.join(WORKING_PATH, r'propertiesFiles')
# This variable specifies the environment to pair each hostname with, will be used to build "location" variables for
# each ENV file properly.
environments = {
    "dev": "dev-hostname",
    "test": "test-hostname",
    "int": "int-hostname",
    "prod": "prod-hostname"
}

# Below builds the basic structure of the ENV files, creating a JSON object with the artifact's
# replacement_env_fields from "artifacts" using the identifier as the top level key, with these values to be
# replaced later when writing to the file if not empty.  Otherwise, the value of the replacement variable will
# be filled with the values from the artifact, with any "location" references replaced.
env_files = {}

# General artifacts that will have one or more variables with some form of deep nesting, where
nest_cases = ["accessTokenManagers", "authenticationSelectors", "idpAdapter", "passwordCredentialValidators",
              "datastores", "samlIDPConnections", "samlSPConnections", "oauthClients"]

# List of artifacts where specifically the "configuration" variable has fields that will require replacing.
config_nested = ["accessTokenManagers", "authenticationSelectors", "datastores", "idpAdapter",
                 "passwordCredentialValidators"]

# Variables that have some level of nesting to them beyond the first level key:value replacement.  Additional
# variables can be specified by adding to the list below in the format {"artifact": "variable name"}
unique_nesting = [{"oauthClients": "clientAuth"}, {"samlIDPConnections": "idpBrowserSso"},
                  {"samlIDPConnections": "additionalAllowedEntitiesConfiguration"},
                  {"samlSPConnections": "spBrowserSso"}]


def intake_artifacts():
    """
    Takes in artifacts files and outputs a dictionary
    :return: A dictionary representation of the artifact JSON.
    """
    artifactsDict = {}
    for filename in os.listdir(ARTIFACTS_PATH):
        if not os.path.isdir(filename) and filename.endswith('.json'):
            current_artifact = json.load(open(os.path.join(ARTIFACTS_PATH, rf'{filename}')))
            artifactsDict[filename.split('.')[0]] = current_artifact
    return artifactsDict


def intake_properties_file():
    """
    Open the properties files, stores them in a dictionary
    :return: Return dictionary file as a dictionary object.
    """
    propertiesDict = {}
    for filename in os.listdir(PROPERTIES_FILES_PATH):
        if not os.path.isdir(filename) and filename.endswith('.json'):
            current_properties_file = json.load(open(os.path.join(PROPERTIES_FILES_PATH, rf'{filename}')))
            propertiesDict[filename.split('.')[0]] = current_properties_file
    return propertiesDict


def identify_replacement_variables(artifactsList):
    """
    This function identifies variables to be replaced from the artifacts as specified by apiCalls.json
    :param artifactsList: List of artifacts to check
    :return: Returns a dictionary of variables that will be included in the ENV file, as well as the identifiers of each
    object/artifact type.
    """
    apiCalls = json.load(open('apiCalls.json'))
    replacement_variables_dict = {}
    identifiers = {}
    for key, value in apiCalls["artifacts"].items():
        if key in artifactsList.keys():
            replacement_variables_dict[key] = apiCalls["artifacts"][key]['replacement_env_fields']
            identifiers[key] = apiCalls["artifacts"][key]['identifier']
    return replacement_variables_dict, identifiers


# This function builds out the basic file structure that the ENV file follows using the replacement fields as well
# as the basic data from the artifact to construct the ENV file artifact passed
def build_env_file_structure(artifact, replacement_fields, identifier):
    """
    Function builds out basic ENV file structure using replacement fields dictionary as well as artifact data to
    construct an ENV file for each artifact type.
    :param artifact: Artifact data to pull from
    :param replacement_fields: Replacement fields to populate the ENV file with
    :param identifier: Identifier to follow the Accenture specified format of "id" : { variables }
    :return: Returns a dictionary of the artifact type in the basic ENV structure.
    """
    data_build = {}
    if identifier not in ["null", "na"] or isinstance(artifact.get("items"), list):
        for item in range(0, len(artifact.get("items", []))):
            for key, value in artifact.get('items', [])[item].items():
                if key in identifier:
                    for field in range(0, len(replacement_fields)):
                        if replacement_fields[field] in artifact['items'][item]:
                            if field == 0 or data_build.get(artifact['items'][item][key]) is None:
                                data_build[artifact['items'][item][key]] = {
                                    replacement_fields[field]: artifact['items'][item][replacement_fields[field]]}
                            else:
                                data_build[artifact['items'][item][key]].update(
                                    {replacement_fields[field]: artifact['items'][item][replacement_fields[field]]})
                        else:
                            continue
    else:
        try:
            if artifact.get('items') is not None:
                for key, value in artifact.get('items'):
                    for field in range(0, len(replacement_fields)):
                        if replacement_fields[field] in artifact['items']:
                            if field == 0 or data_build.get(artifact['items'][key]) is None:
                                data_build[artifact['items'][key]] = {
                                    replacement_fields[field]: artifact['items'][replacement_fields[field]]}
                            # Have to figure out why I'm hitting this at field 2 and never before, think it's something to do
                            # with how I'm checking replacement fields, may need an elif?
                            else:
                                data_build[artifact['items'][key]].update(
                                    {replacement_fields[field]: artifact['items'][replacement_fields[field]]})
                        else:
                            continue
            else:
                # NEED TO FIND RIGHT WAY TO ITERATE HERE, NESTED LISTS AND DICTS ARE A PAIN
                for key, value in artifact.items():
                    for field in range(0, len(replacement_fields)):
                        if replacement_fields[field] in key:
                            if field == 0 or data_build.get(replacement_fields[field]) is None:
                                data_build[key] = value
                            else:
                                data_build[artifact[key]].update(value)
                        else:
                            continue
        except Exception as e:
            print(f"Error Reached for artifact {artifact}:\n{e}")

    new_dict = {}
    for key, value in environments.items():
        if key not in new_dict:
            new_dict[key] = data_build
            new_dict[key] = replace_location_recursive(new_dict[key], "https://ip-10-101-11-241", value)

    return json.dumps(new_dict, indent=2)


# This function will find occurrences of the "location" field and replace with a replacement pulled from the properties
# file to properly reference the correct environment(using MIGRATE_FROM variable) and "location" in the properties file.
def replace_location_recursive(data, target_substring, replacement):
    """
    This function returns a dictionary where all instances of the "location" variable is replaced with an environment
    specific location reference, preserving all IDs, etc.
    :param data: Data is the data to pass in and replace upon
    :param target_substring: string we are targeting for replacement, likely the host name of the migrated from
    environment
    :param replacement: What to replace the target_substring with, likely the host name of the environment we
     are migrating to.
    :return: Return a dictionary with the same data, just with all instances of the target_substring replaced with
    "replacement".
    """
    if isinstance(data, str):
        return data.replace(target_substring, replacement)
    elif isinstance(data, list):
        return [replace_location_recursive(item, target_substring, replacement) for item in data]
    elif isinstance(data, dict):
        new_dict = {}
        for key, value in data.items():
            new_dict[key] = replace_location_recursive(value, target_substring, replacement)
        return new_dict
    else:
        return data


def find_key_in_structure(nested_dict, target_key):
    """
    Finds data at a target key in a deeply nested dictionary, primarily used for finding paths/values in properties file
    :param nested_dict: The nested dictionary to search through
    :param target_key: Key to find in the nested dictionary
    :return: return the data at the target key
    """
    instances = []
    if isinstance(nested_dict, dict):
        for key, value, in nested_dict.items():
            if key == target_key:
                if value is not None:
                    instances.append(value)

            result = find_key_in_structure(value, target_key)
            instances.extend(result)

    elif isinstance(nested_dict, list):
        for item in nested_dict:
            result = find_key_in_structure(item, target_key)
            instances.extend(result)

    return instances


def replace_into_given_path(json_data, path, replacement_data):
    """
    This function is specially coded for variables with deeply nested replacements, with all other data preserved.
    :param json_data: Data to look into.  Usually going to be the basic ENV file structure built by one of the
    prior functions
    :param path: The path to the variable to be replaced, in the format ["objectIdentifier, top level variableName, path
    to "sub-object" after the variable name.
    :param replacement_data: Value to replace with at the path passed in.
    :return: Returns the original ENV dictionary with replacements of "replacement_data" at the "path" passed in.
    """
    current = json_data
    for key in path[:-1]:
        if isinstance(current, list):
            key = int(key)
        try:
            current = current[key]
        except (KeyError, IndexError, TypeError):
            return None

    last_key = path[-1]
    if isinstance(current, list):
        last_key = int(last_key)

    try:
        current[last_key] = replacement_data
        return json_data
    except(KeyError, IndexError, TypeError):
        print("Error replacing with replacement variable.  Try again")
        return None


def return_nested_path_and_val(properties_json, nested_attr=None):
    """
    This function will use the user created properties file to find the path to an attribute in the ENV file and its
    corresponding replacement value(s).
    :param properties_json: Properties file of the artifact we are searching through
    :param nested_attr: Attribute to search for in the existing ENV file
    :return: Returns a list of paths to an element within the JSON and another list with their corresponding values
    as specified by the properties file.
    """
    # First are the IDs(key)
    nested_paths = []
    nested_vals = []
    # This will return a list of lists of dictionaries, hence below structure
    nested_attr_return = find_key_in_structure(properties_json, nested_attr)
    for list_of_dicts in nested_attr_return:
        for key, val in list_of_dicts.items():
            if isinstance(val, list):
                for i in range(0, len(val)):
                    nested_paths.append(val[i]['propertyPath'])
                    nested_vals.append(val[i]['nestedVal'])

            else:
                print("Something went wrong, please check the formatting of your properties file")
                exit(0)
    return nested_paths, nested_vals


if __name__ == '__main__':
    # Intake the artifacts files from the "artifacts" directory
    artifacts_list = intake_artifacts()

    # This uses the apiCalls.json file at the top level of the project to identify an artifact's variables to be pulled
    # into the ENV file.  Very important the apiCalls.json file matches Accenture's here.
    replacement_variables_dict, identifiers = identify_replacement_variables(artifacts_list)

    # Simply takes in the propertiesFiles created by the user.
    properties_files = intake_properties_file()

    # Build the ENV files, perform calls to functions in order to replace values as needed.
    for file in properties_files:
        load = json.loads(build_env_file_structure(artifacts_list[file], replacement_variables_dict[file],
                                                   identifiers[file]))
        env_files[file] = load
        # This handles the base case replacement, where we are doing a straight-up replacement of a top-level key if
        # the value in the properties file is not an empty dictionary.
        if file not in nest_cases:
            for env in environments.keys():
                for key, val in env_files[file][env].items():
                    if bool(properties_files[file][env][key]) is not False and isinstance(
                            properties_files[file][env][key], dict):
                        for k, v in properties_files[file][env][key].items():
                            if bool(v) is not False:
                                env_files[file][env][key][k] = v

        # This handles the replacement of the "configuration" variable and files containing it using the path specified
        # within the properties file.  Also will deal with other variables where this artifact type is specified.
        elif file in config_nested:
            for env in environments.keys():
                property_paths, property_vals = return_nested_path_and_val(properties_files[file][env], "configuration")
                replace_dict = {}
                for item in range(0, len(property_paths)):
                    replace_dict = replace_into_given_path(env_files[file][env], property_paths[item],
                                                           property_vals[item])

                    for key, val in env_files[file][env].items():
                        if bool(properties_files[file][env][key]) is not False and isinstance(
                                properties_files[file][env][key], dict):
                            for k, v in properties_files[file][env][key].items():
                                if bool(v) is not False and k != "configuration":
                                    env_files[file][env][key][k] = v

        # This handles the replacement of any unique, non "configuration" variable with nesting(specified in
        # "unique_nesting" and files containing it using the path specified within the properties file.
        # It will also deal with other variables where this artifact type is specified.
        elif any(file in d for d in unique_nesting):
            unique_paths = []
            unique_vals = []
            for env in environments.keys():
                for i in range(0, len(unique_nesting)):
                    if file in unique_nesting[i].keys():
                        for k, v in unique_nesting[i].items():
                            paths, vals = return_nested_path_and_val(properties_files[file][env], v)
                            unique_paths.extend(paths)
                            unique_vals.extend(vals)
                for item in range(0, len(unique_paths)):
                    replace_dict = replace_into_given_path(env_files[file][env], unique_paths[item], unique_vals[item])

                for key, val in env_files[file][env].items():
                    if bool(properties_files[file][env][key]) is not False and isinstance(
                            properties_files[file][env][key], dict):
                        for k, v in properties_files[file][env][key].items():
                            if bool(v) is not False and k not in [val for dic in unique_nesting for val in
                                                                  dic.values()]:
                                env_files[file][env][key][k] = v

        else:
            print("You may have an error.  Your input files do not match any base case.  Check the formatting of "
                  "your properties file.")
            exit(0)

    # If there is not yet an ENV file directory, first, create it, then iterate through all the artifacts that have
    # newly created ENV file structures created, write it to its file with the correct name in the "ENV Files
    # directory".
    if not os.path.exists("ENV Files"):
        os.makedirs("ENV Files")
    for file in env_files:
        with open(f'ENV Files/{file}.json', 'w+') as f:
            f.write(json.dumps(env_files[file], indent=2))
    # print(f"Result of Data Stores: {json.dumps(env_files['datastores'], indent=2)}")
