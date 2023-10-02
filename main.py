import os
import json

WORKING_PATH = os.path.dirname(__file__)
ARTIFACTS_PATH = os.path.join(WORKING_PATH, r'artifactsToPush')
PROPERTIES_FILES_PATH = os.path.join(WORKING_PATH, r'propertiesFiles')
MIGRATE_FROM = "https://ip-10-101-11-241"
MIGRATE_TO = "https://debian-pingfed"


def intake_artifacts():
    artifactsDict = {}
    for filename in os.listdir(ARTIFACTS_PATH):
        if not os.path.isdir(filename) and filename.endswith('.json'):
            current_artifact = json.load(open(os.path.join(ARTIFACTS_PATH, rf'{filename}')))
            artifactsDict[filename.split('.')[0]] = current_artifact
    return artifactsDict


def intake_properties_file():
    propertiesDict = {}
    for filename in os.listdir(PROPERTIES_FILES_PATH):
        if not os.path.isdir(filename) and filename.endswith('.json'):
            current_properties_file = json.load(open(os.path.join(PROPERTIES_FILES_PATH, rf'{filename}')))
            propertiesDict[filename.split('.')[0]] = current_properties_file
    return propertiesDict

# This function identifies and stores the variables that are to be replaced.
def identify_replacement_variables(artifactsList):
    apiCalls = json.load(open('apiCalls.json'))
    replacement_variables_dict = {}
    identifiers = {}
    for key, value in apiCalls["artifacts"].items():
        if key in artifactsList.keys():
            replacement_variables_dict[key] = apiCalls["artifacts"][key]['replacement_env_fields']
            identifiers[key] = apiCalls["artifacts"][key]['identifier']
    return replacement_variables_dict, identifiers


# This function builds out the basic file structure that the ENV file follows using the replacement fields as well
# as the basic data from the artifact to construct the ENV file artifact passed in.
def build_env_file_structure(artifact, replacement_fields, identifier):
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

    data_build = replace_location_recursive(data_build, MIGRATE_FROM, MIGRATE_TO)

    return json.dumps(data_build, indent=2)


# This function will find occurrences of the "location" field and replace with a replacement pulled from the properties
# file to properly reference the correct environment(using MIGRATE_FROM variable) and "location" in the properties file.
def replace_location_recursive(data, target_substring, replacement):
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


# Finds the paths to a certain element within the nested JSON structure and returns the path to it in a list of lists,
# each of which contains the elements that you'd index into to reach that key/value in the nested structure.
def find_all_paths(json_structure, key_or_value):
    paths = []

    def find_all_paths_helper(json_structure, path, key_or_value, paths):
        if isinstance(json_structure, dict):
            for key, value in json_structure.items():
                if key == key_or_value or value == key_or_value:
                    paths.append(path + [key])
                    break  # Stop searching for paths after a match is found
                else:
                    find_all_paths_helper(value, path + [key], key_or_value, paths)
        elif isinstance(json_structure, list):
            for i, element in enumerate(json_structure):
                find_all_paths_helper(element, path + [i], key_or_value, paths)
        elif json_structure == key_or_value:
            paths.append(path)

    find_all_paths_helper(json_structure, [], key_or_value, paths)
    return paths


def replace_element_using_path(orig_dict, path_list, new_value, special_paths=None):
    """
    Function that will take in a dictionary and modify it based on the path and value passed in.
    :param orig_dict: The dictionary data that is to be modified
    :param path_list: The path(in the form of a list) containing the keys/list indices in order to access the desired
    element to be replaced.
    :param new_value: The value to go at the key of the path_list.
    :return: Return true if the element was found/dictionary was modified.
    """
    current = orig_dict
    if list(path_list) in special_paths:
        print(f"THE PATH {list(path_list)} IS IN SPECIAL PATHS: {special_paths}")
    for key in path_list[:-1]:
        try:
            key = int(key)  # Convert to int if it's an integer index
        except ValueError:
            pass  # Ignore if it's not an integer
        except TypeError:
            pass  # Ignore if type list

        if isinstance(current, list) and 0 <= key < len(current):
            current = current[key]
        elif isinstance(current, dict):
            current = current.get(key, None)
        else:
            # Handle the case where the path is not valid
            return False

    last_key = path_list[-1]

    if isinstance(current, list):
        try:
            last_key = int(last_key)
        except ValueError:
            return False

    if isinstance(current, list) and 0 <= last_key < len(current):
        current[last_key] = new_value
    elif isinstance(current, dict):
        current[last_key] = new_value

    return True

def replace_multiple_elements_using_paths(data_dict, value_path_pairs, special_paths=None):
    for path_list, new_value in value_path_pairs.items():
        print(f"Path list: {path_list}")
        print(f"New Value: {new_value}")
        replace_element_using_path(data_dict, path_list, new_value, special_paths)

    return data_dict


def associate_paths_with_properties(data, properties_data, key_to_find, special_case=False, special_key=""):
    paths_found = [find_all_paths(data, key) for key in key_to_find]
    special_case_paths = []
    path_to_value_mapping = {}

    for idx, key_path_list in enumerate(paths_found):
        for key_path in key_path_list:
            for key, value in properties_data.items():
                for k, v in value.items():
                    if k == key_path[0]:
                        if isinstance(v, dict) and v is not None:
                            nested_data = v
                            if isinstance(key_to_find[idx], str):  # Check if key_to_find is a string
                                if nested_data.get(key_to_find[idx]) is None:
                                    print("None")
                                    for k1,v1 in nested_data.items():
                                        if k1 == 'configuration':
                                            if isinstance(v1.get(key_to_find[idx]), dict):
                                                temp = key_path.index('rows') + 1
                                                var = v1.get(key_to_find[idx])
                                                path_temp = key_path[temp]
                                                replacement_value = var[str(path_temp)]
                                            else:
                                                replacement_value = v1.get(key_to_find[idx])
                                        else:
                                            continue
                                else:
                                    replacement_value = nested_data.get(key_to_find[idx], "ERROR") if special_case else nested_data.get(key_to_find[idx])#properties_data[key][k][key_to_find][idx])
                                if replacement_value is not None:
                                    key_path[-1] = special_key if special_case else key_path[-1]
                                    special_case_paths.append(key_path) if special_case else special_case_paths
                                    path_to_value_mapping[tuple(key_path)] = replacement_value
                            elif isinstance(key_to_find[idx], int):  # Check if key_to_find is an integer
                                if special_case:
                                    key_path[-1] = special_key
                                    special_case_paths.append(key_path)
                                path_to_value_mapping[tuple(key_path)] = nested_data[key_to_find[idx]]
                        elif isinstance(v, list):
                            path_to_value_mapping[tuple(key_path)] = v
                        else:
                            path_to_value_mapping[tuple(key_path)] = v

    return path_to_value_mapping, special_case_paths



if __name__ == '__main__':
    artifacts_list = intake_artifacts()
    replacement_variables_dict, identifiers = identify_replacement_variables(artifacts_list)
    properties_files = intake_properties_file()
    # Below builds the basic structure of the ENV files, creating a JSON object with the artifact's
    # replacement_env_fields from "artifactsToPush" using the identifier as the top level key, with these values to be
    # replaced later when writing to the file.
    env_files = {}
    for file in properties_files:
        load = json.loads(build_env_file_structure(artifacts_list[file], replacement_variables_dict[file],
                                                   identifiers[file]))
        env_files[file] = load
    # These calls will associate the paths with the new values to replace them with, to be used in the
    # replace_multiple_elements_using_paths function afterward.
    clients_path_value_mapping, clients_special_cases = associate_paths_with_properties(env_files["oauthClients"], properties_files["oauthClients"], ["redirectUris"])
    atm_path_value_mapping, atm_special_cases = associate_paths_with_properties(env_files["accessTokenManagers"], properties_files["accessTokenManagers"], ["JWKS Endpoint Path"],
                                                             special_case=True, special_key="value")
    # This is a weird case, will require some fiddling to handle the fact that "Username" appears multiple times across
    # different rows, which is a bit different than how the special case of access token managers works.
    pcv_path_value_mapping, pcv_special_cases = associate_paths_with_properties(env_files["passwordCredentialValidators"], properties_files["passwordCredentialValidators"], ["Username"],
                                                             special_case=True, special_key="value")
    datastores_path_value_mapping, datastores_special_cases = associate_paths_with_properties(env_files["datastores"], properties_files["datastores"],
                                                                    list(properties_files["datastores"]["test"]["ProvisionerDS"].keys()))
    oauthServerSettings_path_value_mapping, oauthServerSettings_special_cases = associate_paths_with_properties(env_files["oauthServerSettings"], properties_files["oauthServerSettings"], ["allowedOrigins", "registeredAuthorizationPath"])
    print(f"OAuth Server Settings Path mapping: {oauthServerSettings_path_value_mapping}")
    print(f"Data Stores Path Mapping: {datastores_path_value_mapping}")
    print(f"PCV Path Mapping: {pcv_path_value_mapping}")
    print(f"PCV Special Case Paths: {pcv_special_cases}")
    print(f"OAuth Clients Path Mapping:{clients_path_value_mapping}")
    clients_build = replace_multiple_elements_using_paths(env_files["oauthClients"], clients_path_value_mapping, clients_special_cases)
    atm_build = replace_multiple_elements_using_paths(env_files["accessTokenManagers"], atm_path_value_mapping, atm_special_cases)
    datastores_build = replace_multiple_elements_using_paths(env_files["datastores"], datastores_path_value_mapping, datastores_special_cases)
    oauthserversettings_build = replace_multiple_elements_using_paths(env_files["oauthServerSettings"], oauthServerSettings_path_value_mapping, oauthServerSettings_special_cases)
    pcv_build = replace_multiple_elements_using_paths(env_files["passwordCredentialValidators"], pcv_path_value_mapping, pcv_special_cases)
    if not os.path.exists("ENV Files"):
        os.makedirs("ENV Files")
    with open(f'ENV Files/oauthClients.json', 'w+') as file:
        file.write(json.dumps(clients_build, indent=2))
    with open(f'ENV Files/passwordCredentialValidators.json', 'w+') as file:
        file.write(json.dumps(pcv_build, indent=2))
    with open(f'ENV Files/datastores.json', 'w+') as file:
        file.write(json.dumps(datastores_build, indent=2))
    with open(f'ENV Files/oauthServerSettings.json', 'w+') as file:
        file.write(json.dumps(oauthserversettings_build, indent=2))
