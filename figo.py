# # PYTHON_ARGCOMPLETE_OK
#!/home/gpuserver/figo/venv/bin/python

import argparse
import argcomplete
import pylxd
import subprocess
import logging
import os
import ipaddress
import yaml
import re
import socket
import json 
import cryptography.hazmat.backends
import cryptography.hazmat.primitives.serialization
import cryptography.hazmat.primitives.asymmetric.rsa
import cryptography.x509
import cryptography.x509.oid
import datetime
from urllib.parse import urlparse
import time
import paramiko
import glob

# Configuration for the WireGuard VPN server
# The following configuration is used to set up a WireGuard VPN server on a MikroTik router.
SSH_MIKROTIK_USER_NAME = "admin"  # Default SSH username
SSH_MIKROTIK_HOST = "160.80.105.2"  # Default MikroTik IP or host
#SSH_WG_HOST = "mikrotik.netgroup.uniroma2.it"  # Default MikroTik IP or host
SSH_MIKROTIK_PORT = 22  # Default SSH port
WG_INTERFACE = "wireguard2"  # Default WireGuard interface
WG_VPN_KEEPALIVE = "20s"  # Default persistent keepalive interval

SSH_LINUX_USER_NAME = "ubuntu"  # Default SSH username
SSH_LINUX_HOST = ""  # Default Linux IP or host
SSH_LINUX_PORT = 22  # Default SSH port

# Define a global dictionary for target lookups
ACCESS_ROUTER_TARGETS = {
    "mikrotik": (SSH_MIKROTIK_HOST, SSH_MIKROTIK_USER_NAME, SSH_MIKROTIK_PORT),
    "figo-2gpu": ("160.80.223.203", "ubuntu", 22),
    # Add more targets as needed
}

VPN_DEVICE_TYPES = ["mikrotik","linux"]  # Extendable list of VPN device types
DEFAULT_SSH_USER_FOR_VPN_AR = None  # Default SSH username for VPN access routers, default to None if user not provided
DEFAULT_SSH_PORT_FOR_VPN_AR = None  # Default SSH port for VPN access routers, default to None if port not provided

# Configuration of timeouts and attempts for the bash connection at VM startup.
BASH_CONNECT_TIMEOUT = 30 # seconds (total time to wait for a bash connection)
BASH_CONNECT_ATTEMPTS = 10 # number of attempts to connect to bash, interval is BASH_CONNECT_TIMEOUT/BASH_CONNECT_ATTEMPTS

import warnings
# Suppress a specific warning from the pylxd library, needed in copy_profile()
warnings.filterwarnings("ignore", message="Attempted to set unknown attribute", module="pylxd.models._model")


NET_PROFILE = "net-bridged-br-200-3"
#NAME_SERVER_IP_ADDR = "160.80.1.8"
NAME_SERVER_IP_ADDR = "8.8.8.8"
NAME_SERVER_IP_ADDR_2 = "8.8.8.4"

PROFILE_DIR = "./profiles"
USER_DIR = "./users"

# Directory that contains the remote node certificates
CERTIFICATE_DIR = "./certs"

# Base IP address to start the IP address generation for WireGuard VPN clients
BASE_IP = "10.202.1.15"

# WireGuard public key of the VPN server 
PublicKey = "rdM5suGD/hTHdStf/K1SVc4rviUcUQbKnARnw0AAwT8="

# Allowed IP addresses for the VPN server
AllowedIPs = "10.192.0.0/10"

# Endpoint of the VPN server
Endpoint = "gpunet-vpn.netgroup.uniroma2.it:13232"

FIGO_PREFIX="figo-"  

# NB: PROJECT_PREFIX cannot contain underscores
PROJECT_PREFIX = FIGO_PREFIX 

DEFAULT_LOGIN_FOR_INSTANCES = 'ubuntu'

DEFAULT_INSTANCE_SIZE = 'compute-medium'  # profile to be added to default if no profile is specified
#DEFAULT_INSTANCE_SIZE = ''  # if empty, no profile is added to defautl


DEFAULT_PREFIX_LEN = 25 # Default prefix length for IP addresses of instances

DEFAULT_VM_NIC = "enp5s0"  # Default NIC for VM instances
DEFAULT_CNT_NIC = "eth0"  # Default NIC for container instances

REMOTE_TO_IP_INFO_MAP = {
    "local": {
        "gw": "10.202.8.129",
        "prefix_len": 25,
        "base_ip": "10.202.8.150"
        },
    "eln_cloud": {
        "gw": "10.202.10.129",
        "prefix_len": 25,
        "base_ip": "10.202.10.150"
        },
    "blade3": {
        "gw": "10.202.9.129",
        "prefix_len": 25,
        "base_ip": "10.202.9.150"
        },
}

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("_")

# Suppress ws4py INFO logging
logging.getLogger('ws4py').setLevel(logging.WARNING)

#############################################
###### generic helper functions         #####
#############################################

def truncate(text, length):
    """Helper function to truncate text to a specific length with '*>' at the end if trimmed."""
    if len(text) > length:
        return f"{text[:length-2]}*>"
    return text

def add_row_to_output(COLS, list_of_values, reset_color=False):
    output_rows.append((COLS, list_of_values, reset_color))

def print_row(COLS, list_of_values, reset_color=False, column_widths=None):
    """Print the values in a row, right-trimming only the final output."""
    RESET = "\033[0m"
    truncated_values = []
    
    # Iterate over the values, truncating as necessary
    for i, value in enumerate(list_of_values):
        if not column_widths:
            truncated_value = truncate(value, COLS[i][1] )
        else:
            truncated_value = truncate(value, column_widths[i] )
        
        # Check for reset color at the end of the value
        if reset_color and value.endswith(RESET) and not truncated_value.endswith(RESET):
            truncated_value = truncated_value + RESET
        
        truncated_values.append(truncated_value)

    # Generate the formatted string and apply rstrip to trim the final output
    formatted_row = gen_format_str(COLS,given_widths=column_widths).format(*truncated_values).rstrip()
    
    print(formatted_row)

header_row = []
output_rows = []

def add_header_line_to_output(COLS):
    global header_row
    global output_rows

    output_rows = [] # Clear the output rows
    header_row = [] # Clear the header row
    header_row.append(COLS)

def evaluate_output_rows_column_width():
    column_widths = [0] * len(output_rows[0][0])
    #evaluate the width of the columns in the header row
    for i, header in enumerate(header_row[0]):
        column_widths[i] = len(header[0])

    for row in output_rows:
        for i, value in enumerate(row[1]):
            column_widths[i] = max(column_widths[i], len(value))

    return column_widths

def print_header_line(COLS, column_widths=None):
    formatted_row = gen_format_str(COLS,given_widths=column_widths).format(*gen_header_list(COLS)).rstrip()
    print(formatted_row)

def flush_output(extend=False):
    global header_row
    global output_rows

    if extend:
        column_widths = evaluate_output_rows_column_width() # Evaluate the column width based on the output rows
    else:
        column_widths = None

    print_header_line(header_row[0], column_widths=column_widths) # Print the header row

    for row in output_rows:
        print_row(*row, column_widths=column_widths) # Print the output rows

    output_rows = [] # Clear the output rows
    header_row = [] # Clear the header row



def is_valid_ip(ip):
    """Check if the provided string is a valid IPv4 address."""
    pattern = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
    if pattern.match(ip):
        octets = ip.split('.')
        if all(0 <= int(octet) <= 255 for octet in octets):
            # paranoid double check
            try:
                ipaddress.ip_address(ip)
                return True
            except ValueError:
                return False
    return False

def is_valid_cidr(cidr_str):
    """Helper function to validate if a string is a valid CIDR (IP address with prefix)."""
    try:
        ipaddress.ip_network(cidr_str, strict=False)
        return True
    except ValueError:
        return False

def is_valid_ip_prefix_len(ip_prefix):
    try:
        ip, prefix_len = ip_prefix.split('/')
        if not is_valid_ip(ip):
            return False
        prefix_len = int(prefix_len)
        if prefix_len < 1 or prefix_len > 32:
            return False
        return True
    except ValueError:
        return False

def matches(target_string, compare_string):
    # Escape all regex characters except for '*'
    compare_string = re.escape(compare_string)
    # Replace the escaped '*' with '.*' which matches any sequence of characters
    compare_string = compare_string.replace(r'\*', '.*')
    # Use full match to check if target_string matches the compare_string pattern
    return re.fullmatch(compare_string, target_string) is not None

def gen_format_str(columns, given_widths=None):
    """Generate the format string based on the given columns.
    
    The format string is used to format the values in each row.
    columns: A list of tuples with the column name and width.
    
    """
    format_str = ""
    if not given_widths:
        for _, width in columns:
            format_str += f"{{:<{width}}} "
    else:
        # Use the given widths to generate the format string
        for col_width in given_widths:
            format_str += f"{{:<{col_width}}} "
    return format_str.strip()  # Remove the trailing space

def gen_header_list(columns):
    """Generate the list of headers based on the given columns."""
    headers = [header for header, _ in columns]
    return headers

def format_ip_device_pairs(ip_device_pairs):
    """Return a string with IP addresses followed by device names in brackets."""
    formatted_pairs = [f"{ip.split('/')[0]} ({device})" for ip, device in ip_device_pairs]
    return ", ".join(formatted_pairs)

def extract_ip_addresses(ip_device_pairs):
    """Return a list of IP addresses (without the prefix length) from a list of 'ip/device'."""
    return [ip.split('/')[0] for ip, _ in ip_device_pairs]

def get_ip_string_from_ip_and_prefix(ip_address_and_prefix_len):
    """Return the IP address string from an 'ip/prefix' string."""
    return ip_address_and_prefix_len.split('/')[0]

def derive_project_from_user(user_name):
    return f"{PROJECT_PREFIX}{user_name}"

def is_l1_host(remote_name):
    return remote_name.startswith('l1-')

def get_l0_remote(l1_host_name):
    """
    Extracts the remote part from an L1 host name by splitting on the '-l0-' token.

    Parameters:
    l1_host_name (str): The L1 host name in the format 'l1-host-l0-remote'.

    Returns:
    str: The extracted 'remote' part, or None if the format is invalid.
    """
    try:
        parts = l1_host_name.split('-l0-')
        if len(parts) == 2:
            return parts[1]  # Return the part after '-l0-'
        else:
            raise ValueError("Invalid L1 host name format.")
    except Exception as e:
        logger.error(f"Error extracting remote: {e}")
        return None

def get_l1_host(remote_name):
    """
    Extracts the L1 host name from a remote name by splitting on the '-l0-' token.

    Parameters:
    remote_name (str): The remote name in the format 'l1-host-l0-remote'.

    Returns:
    str: The extracted 'l1-host' part, or None if the format is invalid.
    """
    try:
        parts = remote_name.split('-l0-')
        if len(parts) == 2:
            return parts[0]  # Return the part before '-l0-'
        else:
            raise ValueError("Invalid remote name format.")
    except Exception as e:
        logger.error(f"Error extracting L1 host: {e}")
        return None

def add_l2_ip_address(instance_object, ip_address):
    """Add an IP address to the l2 IP address list of the instance.
    
    The IP address is added only if it is not already in the list.

    return: True if the IP address was added, False otherwise.
    """
    try:
        ip_list = instance_object.config.get('user.l2_ip_list', '').split(',')
    
        if ip_address not in ip_list:
            ip_list.append(ip_address)
            instance_object.config['user.l2_ip_list'] = ','.join(filter(None, ip_list))
            instance_object.save(wait=True)
            logger.info(f"IP address {ip_address} added to l2 IP address list.")
            return True
        else:
            logger.error(f"IP address {ip_address} is already in the list.")
            return False
    except Exception as e:
        logger.error(f"Error adding IP address to l2 IP address list: {e}")
        return False


def remove_l2_ip_address(instance_object, ip_address):
    """Remove an IP address from the l2 IP address list of the instance.
    
    The IP address is removed only if it is in the list.
    
    return: True if the IP address was removed, False otherwise.
    """
    try:
        ip_list = instance_object.config.get('user.l2_ip_list', '').split(',')
        if ip_address in ip_list:
            ip_list.remove(ip_address)
            instance_object.config['user.l2_ip_list'] = ','.join(filter(None, ip_list))
            instance_object.save(wait=True)
            logger.info(f"IP address {ip_address} removed from l2 IP address list.")
            return True
        else:
            logger.error(f"IP address {ip_address} not found in the list.")
            return False
    except Exception as e:
        logger.error(f"Error removing IP address from l2 IP address list: {e}")
        return False

def get_l2_ip_address_list(instance_object):
    """Retrieve the l2 IP address list from the instance.
    
    Returns:    A list of IP addresses or None if there is an error.
    """

    try:
        ip_list = instance_object.config.get('user.l2_ip_list', '').split(',')
        return [ip for ip in ip_list if ip]  # Filter out empty strings
    except Exception as e:
        logger.error(f"Error retrieving l2 IP address list: {e}")
        return None

def clear_l2_ip_address_list(instance_object):
    """Clear all IP addresses from the l2 IP address list of the instance.
    
    Returns:    True if the IP addresses were cleared, False otherwise.
    """
    try:
        instance_object.config['user.l2_ip_list'] = ''
        instance_object.save(wait=True)
        print("All IP addresses cleared from l2 IP address list.")
        return True
    except Exception as e:
        logger.error(f"Error clearing l2 IP address list: {e}")
        return False

def get_instance_state_dict (instance):
    """Return a dictionary with the state information of the instance."""

    #TODO may be it could be replaced with incus list -f json and then filtering the instance by name
    #TODO I have removed  "created_at": instance.created_at.isoformat() if instance.created_at else None,
    #TODO I have removed  "last_used_at": instance.last_used_at.isoformat() if instance.last_used_at else None,
        
    instance_state = instance.state()  # Get instance state information
    instance_state_dict = {
        "name": instance.name,
        "status": instance.status,
        "status_code": instance_state.status_code,
        "type": instance.type,
        "architecture": instance.architecture,
        "location": instance.location,
        "config": instance.config,
        "expanded_config": instance.expanded_config,
        "devices": instance.devices,
        "expanded_devices": instance.expanded_devices,
        "state": {
            "status": instance_state.status,
            "disk": instance_state.disk,
            "memory": instance_state.memory,
            "network": instance_state.network,
            "pid": instance_state.pid,
            "processes": instance_state.processes
        }
    }
    return instance_state_dict

#############################################
###### figo instance command functions #####
#############################################

def get_incus_remotes():
    """Fetches the list of Incus remotes as a JSON object.
    
    Returns:    A dictionary of remote names and their information.
    Raises:     RuntimeError if the command fails to retrieve the JSON list
                ValueError if the JSON output cannot be parsed.
                
    """
    result = subprocess.run(['incus', 'remote', 'list', '--format', 'json'], capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to retrieve Incus remotes: {result.stderr}")

    try:
        remotes = json.loads(result.stdout)
        return remotes
    except json.JSONDecodeError:
        raise ValueError("Failed to parse JSON. The output may not be in the expected format.")

def get_projects(remote_name="local"): 
    """Fetches and returns the list of projects as a JSON object.
    
    Returns:    A list of projects as JSON objects if successful. Otherwise, returns None.
    """
    try:
        result = subprocess.run(['incus', 'project', 'list', f"{remote_name}:", '--format', 'json'], capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        #logger.error(f"Error: {e.stderr.strip()}")
        return None

    if result.returncode != 0:
        #logger.error(f"Failed to retrieve projects: {result.stderr}")
        return None

    try:
        projects = json.loads(result.stdout)
        return projects
    except json.JSONDecodeError:
        logger.error("Failed to parse JSON output.")
        return None

def run_incus_list(remote_node="local", project_name="default"):
    """Run the 'incus list -f json' command to get the instance state all the instances, optionally targeting a remote node and project.
    
    Return the output as a list of dict if successful, return None if the project does not exist.
    """
    try:
        # Check if the project exists
        command_check = ["incus", "project", "show", project_name]
        if remote_node:
            command_check = ["incus", "project", "show", f"{remote_node}:{project_name}"]

        result_check = subprocess.run(command_check, capture_output=True, text=True, check=True)

        # If the project exists, proceed to list instances
        command = ["incus", "list", "-f", "json", "--project", project_name]
        if remote_node:
            command = ["incus", "list", f"{remote_node}:", "-f", "json", "--project", project_name]

        result = subprocess.run(command, capture_output=True, text=True, check=True)

        # Parse the JSON output
        instances = json.loads(result.stdout)
        
        return instances

    except subprocess.CalledProcessError as e:
        #logger.error(f"Error: {e.stderr.strip()}")
        return None

    except json.JSONDecodeError as e:
        logger.error(f"Error: Failed to parse JSON output. {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error while running 'incus list -f json': {e}")
        return None

def get_ip_device_pairs(instance):
        # Fetch user.network-config if it exists
        network_config = instance.get("config", {}).get("user.network-config", "N/A")

        # Output the network config for debugging purposes
        #print(f"Instance '{name}' network config: {network_config}")
        #TODO (nice to have) reformat the network config to be more readable

        ip_device_pairs = []  # List to hold (ip_address, device) pairs

        # Parse and extract the addresses for each ethernet device
        if network_config != "N/A":
            try:
                # Assuming the network config is in YAML format
                network_config_parsed = yaml.safe_load(network_config)
                ethernets = network_config_parsed.get("ethernets", {})
                for device, config in ethernets.items():
                    addresses = config.get("addresses", [])
                    for ip_address in addresses:
                        ip_device_pairs.append((ip_address, device))

            except Exception as e:
                logger.error(f"Error parsing network config for instance '{instance.get('name', 'Unknown')}': {e}")

        return ip_device_pairs

def get_ip_addresses(instance):
    """Return a list of IP addresses for the instance."""
    ip_device_pairs = get_ip_device_pairs(instance)
    return extract_ip_addresses(ip_device_pairs)

def is_same_subnet(ip_address, gw_address, prefix_length):
    """Check if the IP address is in the same subnet as the gateway address."""
    ip = ipaddress.ip_interface(f"{ip_address}/{prefix_length}")
    gw = ipaddress.ip_interface(f"{gw_address}/{prefix_length}")
    return ip.network == gw.network

def iterator_over_projects(remote_node):
    """Iterate over all projects in the specified remote."""
    projects = get_projects(remote_name=remote_node)
    if projects is None:
        return

    for project in projects:
        yield project

def iterator_over_instances(remote, project_name, instance_scope=None):
    """Iterate over all instances in the specified remote and project, providing an instance state dict for each instance
    
    Optionally filter by instance name.
    """
    instance_state_list = run_incus_list(remote_node=remote, project_name=project_name)
    if instance_state_list is None:
        return

    for instance_state_dict in instance_state_list:
        name = instance_state_dict.get("name", "Unknown")
        if instance_scope and not matches(name, instance_scope):
            continue
        yield instance_state_dict

def get_and_print_instances(COLS, remote_node=None, project_name=None, instance_scope=None, full=False):
    """Get instances from the specified remote node and project and print their details.
    
    Returns:    False if fetching the instances failed, True otherwise.
    """

    RED = "\033[91m"
    GREEN = "\033[92m"
    RESET = "\033[0m"
    # Get the instances from 'incus list -f json'
    instances = run_incus_list(remote_node=remote_node, project_name=project_name)
    if instances is None:
        return False  # Exit if fetching the instances failed

    # Iterate through instances and print their details in columns
    for instance in instances:
        name = instance.get("name", "Unknown")
        if instance_scope and not matches(name, instance_scope):
            continue
        instance_type = "vm" if instance.get("type") == "virtual-machine" else "cnt"
        state = instance.get("status", "err")[:3].lower()  # Shorten the status

        # Construct the context column as remote_name:project_name
        project_name = instance.get("project", "default")
        context = f"{remote_node}:{project_name}" if remote_node else f"local:{project_name}"

        ip_device_pairs = get_ip_device_pairs(instance) # Get the IP addresses and device names

        if full:
            # Print all profiles
            profiles_str = ", ".join(instance.get("profiles", []))
            add_row_to_output(COLS, [name, instance_type, state, context, format_ip_device_pairs(ip_device_pairs), profiles_str])
        else:
            # Print only GPU profiles with color coding based on state
            gpu_profiles = [profile for profile in instance.get("profiles", []) if profile.startswith("gpu")]
            profiles_str = ", ".join(gpu_profiles)
            colored_profiles_str = f"{RED}{profiles_str}{RESET}" if state == "run" else f"{GREEN}{profiles_str}{RESET}"
            add_row_to_output(COLS, [name, instance_type, state, context, format_ip_device_pairs(ip_device_pairs), colored_profiles_str],
                      reset_color=True)
    return True
    

def list_instances(remote_node=None, project_name=None, instance_scope=None, full=False, extend=False):
    """Print profiles of all instances, either from the local or a remote Incus node.
    If full is False, prints only GPU profiles with color coding.
    """
    # Determine the header and profile type based on the 'full' flag
    if full:
        COLS = [('INSTANCE',16), ('TYPE',4), ('STATE',5), ('CONTEXT',25), ('IP ADDRESS(ES)',25), ('PROFILES',75)]
    else:
        COLS = [('INSTANCE',16), ('TYPE',4), ('STATE',5), ('CONTEXT',25), ('IP ADDRESS(ES)',25), ('GPU PROFILES',75)]

    add_header_line_to_output(COLS)

    # use a set to store the remote nodes that failed to retrieve the projects
    set_of_errored_remotes = set()
    if remote_node is None:
        #iterate over all remote nodes
        remotes = get_incus_remotes()
        for my_remote_node in remotes:
            # check to skip all the remote node of type images
            # Skipping remote node with protocol simplestreams
            if remotes[my_remote_node]["Protocol"] == "simplestreams":
                continue

            if project_name is None:
                # iterate over all projects
                projects = get_projects(remote_name=my_remote_node)
                if projects is None:
                    set_of_errored_remotes.add(my_remote_node)
                else: # projects is not None:
                    for project in projects:
                        my_project_name = project["name"]
                        result = get_and_print_instances(COLS, remote_node=my_remote_node, project_name=my_project_name,
                                                         instance_scope=instance_scope, full=full)
                        if not result:
                            set_of_errored_remotes.add(my_remote_node)
            else:
                result = get_and_print_instances(COLS, remote_node=my_remote_node, project_name=project_name,
                                                 instance_scope=instance_scope, full=full)
                if not result:
                    set_of_errored_remotes.add(my_remote_node)
    else: # remote_node is not None
        # Get instances from the specified remote node
        if project_name is None:
            # iterate over all projects
            projects = get_projects(remote_name=remote_node)
            if projects is None:
                set_of_errored_remotes.add(remote_node)
            else:  # projects is not None:
                for project in projects:
                    my_project_name = project["name"]
                    result = get_and_print_instances(COLS, remote_node=remote_node, project_name=my_project_name,
                                                     instance_scope=instance_scope, full=full)
                    if not result:
                        set_of_errored_remotes.add(remote_node)
        else: # remote_node is not None and project_name is not None
            # Get instances from the specified remote node and project
            result = get_and_print_instances(COLS, remote_node=remote_node, project_name=project_name,
                                             instance_scope=instance_scope, full=full)
            if not result:
                set_of_errored_remotes.add(remote_node)

    flush_output(extend=extend)

    if set_of_errored_remotes:
        logger.error(f"Error: Failed to retrieve projects from remote(s): {', '.join(set_of_errored_remotes)}")

def get_remote_client(remote_node, project_name='default', raise_project_not_found=False, test_project=True, show_info=True):  
    """Create a pylxd.Client instance for the specified remote node and project.

    Parameters:
    remote_node (str): The name of the remote node.
    project_name (str): The name of the project.
    raise_project_not_found (bool): If True, raise a ValueError if the project does not exist on the remote.
    test_project (bool): If True, test if the project exists on the remote.
    
    Returns:  A pylxd.Client instance for the remote node if successful, None otherwise.

    If not successful, the function logs an error message and returns None.
    If raise_project_not_found is True and the project does not exist on the remote the function raises a ValueError.
    """
    #TODO add the code to handle the case when the remote node is not reachable and return None

    if remote_node == "local":
        # Create a pylxd.Client instance for the local server
        try:
            client_instance = pylxd.Client(project=project_name)
            if test_project:
                # Test if the project exist by fetching a non-existent instance
                try:
                    client_instance.instances.get("xxxx-yyyy")
                except pylxd.exceptions.NotFound as e:
                    if "Project not found" in str(e):
                        if show_info:
                            logger.info(f"Failed to connect to remote '{remote_node}' and project '{project_name}': Project not found.")
                        if raise_project_not_found:
                            raise ValueError(f"Project not found : '{project_name}' on remote '{remote_node}'")
                        else:
                            return None 
                    else:
                        pass # continue because we expect the instance to be not found
                except Exception as e:
                    logger.error(f"Failed to connect to remote '{remote_node}' and project '{project_name}': {e}")
                    return None
            return client_instance

        except pylxd.exceptions.ClientConnectionFailed as e:
            logger.error(f"Failed to connect to remote '{remote_node}' and project '{project_name}': Client connection failed.")
            return None
        
    else:
        try :
            address = get_remote_address(remote_node)
            cert_path = get_certificate_path(remote_node)
        except FileNotFoundError:
            logger.error(f"Failed to connect to remote '{remote_node}' and project '{project_name}': Certificate not found.")
            return None
        except Exception as e:
            logger.error(f"Failed to connect to remote '{remote_node}' and project '{project_name}': {e}")
            return None

        # Create a pylxd.Client instance with SSL verification
        try:
            client_instance = pylxd.Client(endpoint=address, verify=cert_path, project=project_name)
            if test_project:
                # Test if the project exist by fetching a non-existent instance
                try:
                    client_instance.instances.get("xxxx-yyyy") 
                except pylxd.exceptions.NotFound as e:
                    if "Project not found" in str(e):
                        if show_info:
                            logger.info(f"Failed to connect to remote '{remote_node}' and project '{project_name}': Project not found.")
                        if raise_project_not_found:
                            raise ValueError(f"Project not found : '{project_name}' on remote '{remote_node}'")
                        else:
                            return None 
                    else:
                        pass # continue because we expect the instance to be not found
                except Exception as e:
                    logger.error(f"Failed to connect to remote '{remote_node}' and project '{project_name}': {e}")
                    return None
            return client_instance   
        except pylxd.exceptions.ClientConnectionFailed as e:
            logger.error(f"Failed to connect to remote '{remote_node}' and project '{project_name}': Client connection failed.")
            return None
        except ValueError as e:
            if 'Project not found' in str(e):
                raise ValueError(e)
            else:
                logger.error(f"Failed to connect to remote '{remote_node}' and project '{project_name}': {e}")
                return None
        except Exception as e:
            logger.error(f"Failed to connect to remote '{remote_node}' and project '{project_name}': {e}")
            return None

def start_instance(instance_name, remote, project):
    """Start a specific instance on a given remote and within a specific project.
    
    Returns:    True if the instance was started successfully, False otherwise.
    """
    try:
        # Connect to the specified remote and project 
        remote_client = get_remote_client(remote, project_name=project)
        if not remote_client:
            logger.error(f"Failed to connect to remote '{remote}' and project '{project}'.")
            return False
        
    except Exception as e:
        logger.error(f"Failed to connect to remote '{remote}' and project '{project}': An unexpected error occurred: {e}")
        return False
    
    try:
        instance = remote_client.instances.get(instance_name)

        # Check if the instance is already running

        if instance.status.lower() != "stopped":
            logger.error(f"Instance '{instance_name}' in project '{project}' on remote '{remote}' is not stopped.")
            return False

        # check if the instance is a vm or a container
        instance_type = instance.type

        #TODO differentiate the following code based on the instance type

        # Get GPU profiles associated with this instance
        instance_profiles = instance.profiles
        gpu_profiles_for_instance = [
            profile for profile in instance_profiles if profile.startswith("gpu-")
        ]
        
        if gpu_profiles_for_instance: # there is at least one GPU profile

            # Check GPU availability
            try:
                result = subprocess.run('lspci | grep NVIDIA', capture_output=True, text=True, shell=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Error in lspci: {e.stderr.strip()}")
                return False
            
            total_gpus = len(result.stdout.strip().split('\n'))
            
            running_instances = [
                i for i in remote_client.instances.all() if i.status == "Running"
            ]
            active_gpu_profiles = [
                profile for my_instance in running_instances for profile in my_instance.profiles
                if profile.startswith("gpu-")
            ]

            available_gpus = total_gpus - len(active_gpu_profiles)
            if len(gpu_profiles_for_instance) > available_gpus:
                logger.error(
                    f"Not enough available GPUs to start instance '{instance_name}'."
                )
                return False

            #TODO (nice to have) check error conditions in the following code
            # Resolve GPU conflicts
            conflict = False
            for gpu_profile in gpu_profiles_for_instance:
                for my_instance in running_instances:
                    if gpu_profile in my_instance.profiles:
                        conflict = True
                        logger.warning(
                            f"GPU profile '{gpu_profile}' is already in use by "
                            f"instance {my_instance.name}."
                        )
                        instance_profiles.remove(gpu_profile)
                        new_profile = [
                            p for p in remote_client.profiles.all() 
                            if p.name.startswith("gpu-") and p.name not in active_gpu_profiles
                            and p.name not in instance_profiles
                        ][0].name
                        instance_profiles.append(new_profile)
                        logger.info(
                            f"Replaced GPU profile '{gpu_profile}' with '{new_profile}' "
                            f"for instance '{instance_name}'"
                        )
                        break

            # Update profiles if needed and start the instance
            if conflict:
                instance.profiles = instance_profiles
                instance.save(wait=True)

        else: # there are no GPU profiles associated with the instance
            pass

        instance.start(wait=True)
        logger.info(f"Instance '{instance_name}' started on '{remote}:{project}'.")
        return True

    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to start instance '{instance_name}' in project '{project}' on remote '{remote}': {e}")
        return False


def stop_instance(instance_name, remote, project):
    """Stop a specific instance.
    
    Returns:    True if the instance was stopped successfully, False otherwise.
    """
    # get the specified instance in project and remote  
    remote_client = get_remote_client(remote, project_name=project)
    if not remote_client:
        logger.error(f"Failed to connect to remote '{remote}' and project '{project}'.")
        return False

    try:
        instance = remote_client.instances.get(instance_name)

        if instance.status.lower() != "running":
            logger.error(f"Instance '{instance_name}' in project '{project}' on remote '{remote}' is not running.")
            return False

        instance.stop(wait=True)
        logger.info(f"Instance '{instance_name}' stopped.")
        return True
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to stop instance '{instance_name}' in project '{project}' on remote '{remote}': {e}")
        return False

def stop_all_instances(remote_node, project_name):
    """Stop all instances in the specified remote node and project.
    
    This function is recursive.
    If remote_node is None, look for instances in all remotes.
    If project_name is None, look for instances in all projects.
    If both remote_node and project_name are None, look for instances in all remotes and projects.
    If both remote_node and project_name are specified, stop all instances on the specified remote
    in the specified project and end the recursion.

    Returns:    None
    """

    #if remote_node is None all the remotes are considered
    if remote_node is None:
        #iterate over all remote nodes
        remotes = get_incus_remotes()
        for my_remote_node in remotes:
            # check to skip all the remote node of type images
            # Skipping remote node with protocol simplestreams
            if remotes[my_remote_node]["Protocol"] == "simplestreams":
                continue

            if project_name is None:
                # iterate over all projects
                projects = get_projects(remote_name=my_remote_node)
                if projects is None:
                    continue
                else: # projects is not None:
                    for project in projects:
                        my_project_name = project["name"]
                        stop_all_instances(my_remote_node, my_project_name) # recursive call
            else:
                stop_all_instances(my_remote_node, project_name) # recursive call
    else: # remote_node is not None
        #check if the project is None
        if project_name is None:
            # iterate over all projects
            projects = get_projects(remote_name=remote_node)
            if projects is None:
                return
            else: # projects is not None:
                for project in projects:
                    my_project_name = project["name"]
                    stop_all_instances(remote_node, my_project_name) # recursive call
        else: # remote_node is not None and project_name is not None

            # Get all instances in the specified remote node and project
            instance_state_list = run_incus_list(remote_node=remote_node, project_name=project_name)
            if instance_state_list is None:
                return

            for instance_state_dict in instance_state_list:
                name = instance_state_dict.get("name", "Unknown")
                state = instance_state_dict.get("status", "err")[:3].lower()  # Shorten the status

                if state == "run":
                    logger.info(f"Stopping instance '{name}' in project '{project_name}' on remote '{remote_node}'.")
                    stop_instance(name, remote_node, project_name)  # Stop the running instance


def set_user_key(instance_name, remote, project, key_filename, login='ubuntu', folder='.users', force=False):
    """Set a public key in the specified instance in the authorized_keys file of the specified user.
    
    Args:
    - instance_name: Name of the instance.
    - remote: Remote server name.
    - project: Project name.
    - key_filename: Filename of the public key on the host.
    - login: Login name of the user (default: 'ubuntu') for which we set the key.
    - folder: Folder path where the key file is located (default: '.users').
    - force: If True, start the instance if it's not running and stop it after setting the key.

    Returns: True if the key was set successfully, False otherwise.
    """

    def exec_command(instance, command):
        """Execute a command in the instance.
        
        Returns: True if the command was successful, False otherwise.
        """
        try:
            exec_result = instance.execute(command)
            if exec_result.exit_code != 0:
                logger.error(f"Error executing command '{' '.join(command)}': {exec_result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"Exception while executing command '{' '.join(command)}': {e}")
            return False

    try:
        # Full path to the key file
        key_filepath = f"{folder}/{key_filename}"

        # Read the public key from the file
        with open(key_filepath, 'r') as key_file:
            public_key = key_file.read().strip()

        # Get the specified instance in project and remote  
        remote_client = get_remote_client(remote, project_name=project)
        if not remote_client:
            logger.error(f"Failed to connect to remote '{remote}' and project '{project}'.")
            return False
        instance = remote_client.instances.get(instance_name)

        # Check if the key already exists in authorized_keys
        try:
            existing_keys = instance.files.get(f'/home/{login}/.ssh/authorized_keys').decode('utf-8')
            logger.info(f"Fetched existing authorized_keys from /home/{login}/.ssh/authorized_keys in instance '{instance_name}'.")
            
            if public_key in existing_keys:
                logger.info(f"Public key from '{key_filepath}' is already present in /home/{login}/.ssh/authorized_keys.")
                return True  # Key already exists, no need to proceed further

        except pylxd.exceptions.NotFound:
            # No authorized_keys file exists, we can proceed
            logger.info(f"No authorized_keys file found for {login}, proceeding with adding the key.")

        was_started = False
    
        # Check if the instance is running
        if instance.status.lower() != "running":
            if force:
                # Start the instance if it is not running
                was_started = start_instance(instance.name, remote, project)
                if not was_started:
                    logger.error(f"Error: Instance '{instance_name}' failed to start")
                    return False
            else:
                logger.error(f"Error: Instance '{instance_name}' is not running.")
                return False

        # Create .ssh directory
        if not exec_command(instance, ['mkdir', '-p', f'/home/{login}/.ssh']):
            return False

        # Create authorized_keys file if not present
        if not exec_command(instance, ['touch', f'/home/{login}/.ssh/authorized_keys']):
            return False

        # Set permissions
        if not exec_command(instance, ['chmod', '600', f'/home/{login}/.ssh/authorized_keys']):
            return False
        if not exec_command(instance, ['chown', f'{login}:{login}', f'/home/{login}/.ssh/authorized_keys']):
            return False

        # Add the public key to authorized_keys
        if not exec_command(instance, ['sh', '-c', f'echo "{public_key}" >> /home/{login}/.ssh/authorized_keys']):
            return False

        logger.info(f"Public key from '{key_filepath}' added to /home/{login}/.ssh/authorized_keys in instance '{instance_name}'.")

        if force and was_started:
            # Stop the instance if we started it earlier
            result = stop_instance(instance.name, remote, project)
            if not result:
                logger.error(f"Error: Failed to stop instance '{instance_name}'")
                return False

        return True
        
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to set user key for instance '{instance_name}': {e}")
        return False
    except FileNotFoundError:
        logger.error(f"File '{key_filepath}' not found.")
        return False
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return False

def assign_ip_address(remote, mode="next"):
    """Assign a new IP address based on the highest assigned IP address or the first available hole.
    
    Used by the 'set_ip' and by the 'get_ip_and_gw' functions

    mode: "next" assigns the next available IP address,
            "hole" assigns the first available hole starting from BASE_IP

        Returns: The new IP address as a string or None if an error occurred.
    """
    
    #TODO add a check to see if the remote is a l1-host and get the IP addresses from the l0-host
    #TODO handle the case when there are no available IP addresses

    assigned_ips = retrieve_assigned_ips(remote)
    if assigned_ips is None:
        return None

    try:
        base_ip_str = REMOTE_TO_IP_INFO_MAP[remote]["base_ip"]
    except KeyError as e:
        logger.error(f"key error to get base_ip: remote '{remote}' not found in REMOTE_TO_IP_INFO_MAP.")
        return None

    base_ip = ipaddress.ip_address(base_ip_str)
    if not assigned_ips:
        new_ip = base_ip
    else:
        if mode == "next":
            highest_ip = max([ipaddress.ip_address(ip) for ip in assigned_ips])
            new_ip = highest_ip + 1
        elif mode == "hole":
            new_ip = base_ip
            while str(new_ip) in assigned_ips:
                new_ip += 1 # Increment the IP address until an available one is found
    return str(new_ip)

def retrieve_assigned_ips(remote):
    """Retrieve all assigned IP addresses for instances in the specified remote.

    If the remote is a l1-host, return the list of all IP addresses assigned in the associated l0-host
    If the instance is a l1-host the list includes all l2 IP addresses assigned in the l1-host

    Returns: A list of assigned IP addresses or None if an error occurred.
    """


    # if the remote starts with 'l1-', get the IP addresses from the l0-host
    if is_l1_host(remote):

        l0_remote = get_l0_remote(remote)
        if not l0_remote:
            logger.error(f"Error: cannot get L0 remote from L1 remote name '{remote}'.")
            return None
        
        return retrieve_assigned_ips(l0_remote) 
       
    assigned_ips = []
    for project in iterator_over_projects(remote):

        client_instance = get_remote_client(remote, project_name=project["name"])
        if not client_instance:
            logger.error(f"Failed to connect to project '{project['name']}'.")
            return None

        for instance_state_dict in iterator_over_instances(remote, project["name"]):
            ip_addresses = get_ip_addresses(instance_state_dict)
            assigned_ips.extend(ip_addresses)
            #if the instance name starts with l1- get the l2 IP addresses
            if instance_state_dict["name"].startswith("l1-"):
                #get the instance object
                instance_object = client_instance.instances.get(instance_state_dict["name"])
                l2_ip_addresses = get_l2_ip_address_list(instance_object)
                if l2_ip_addresses is None:
                    return None
                assigned_ips.extend(l2_ip_addresses)
    return assigned_ips

def get_gw_address(remote):
    """Get the gateway address for the remote.
    
    Returns: The gateway address as a string or None if an error occurred.
    """
    try:
        return REMOTE_TO_IP_INFO_MAP[remote]["gw"]
    except KeyError as e:
        logger.error(f"key error in get_gw_address: remote '{remote}' not found in REMOTE_TO_IP_INFO_MAP.")
        return None

def get_prefix_len(remote):
    """Get the prefix length for the remote.
    
    Returns: The prefix length as an integer or None if an error occurred.
    """
    try:
        return REMOTE_TO_IP_INFO_MAP[remote]["prefix_len"]
    except KeyError as e:
        logger.error(f"key error in get_prefix_len: remote '{remote}' not found in REMOTE_TO_IP_INFO_MAP.")
        return None

def set_ip(instance_name, remote, project, ip_address_and_prefix_len=None, gw_address=None, nic_device_name=None):
    """Set a static IP address and gateway for a stopped instance.

    Args: 
    - instance_name: Name of the instance.
    - remote: Remote server name.
    - project: Project name.
    - ip_address_and_prefix_len: IP address and prefix length. If None, the address is assigned automatically.
    - gw_address: Gateway address. If None, the default gateway for the remote is used.
    
    Returns: True if the IP address was set successfully, False otherwise.
    """
    
    #TODO check if the ip address is already assigned

    if ip_address_and_prefix_len:
    # Split the IP address and prefix length
        try:
            if not is_valid_ip_prefix_len(ip_address_and_prefix_len):
                logger.error(f"Error: '{ip_address_and_prefix_len}' is not a valid IP address with prefix length.")
                return False

            ip_interface = ipaddress.ip_interface(ip_address_and_prefix_len)
            ip_address = str(ip_interface.ip)
            prefix_length = ip_interface.network.prefixlen

        except ValueError as e:
            logger.error(f"Error: '{ip_address_and_prefix_len}' is not a valid IP address with prefix length: {e}")
            return False
    else: 
    #ip_address_and_prefix_len is None
        # Assign the next available IP address
        remap_remote = remote
        if is_l1_host(remote):
            remap_remote = get_l0_remote(remote)
        ip_address = assign_ip_address(remap_remote, mode="next")
        prefix_length = get_prefix_len(remap_remote)

    if ip_address is None or prefix_length is None:
        logger.error(f"Error: Failed to assign IP address for instance '{instance_name}'.")
        return False

    if gw_address :
        if not is_valid_ip(gw_address):
            logger.error(f"Error: gw address '{gw_address}' is not a valid IP address.")
            return False
    else:
        gw_address = get_gw_address(remote)

    if gw_address is None:
        logger.error(f"Error: Gateway address not found for remote '{remap_remote}'.")
        return False

    # check that gw_address is in the same subnet as ip_address
    if not is_same_subnet(ip_address, gw_address, prefix_length):
        logger.error(f"Error: gw address '{gw_address}' is not in the same subnet as ip address '{ip_address}/{prefix_length}'.")
        return False
        
    try:
        # Get the specified instance in project and remote  
        remote_client = get_remote_client(remote, project_name=project)
        if not remote_client:
            logger.error(f"Failed to connect to remote '{remote}' and project '{project}'.")
            return False
        instance = remote_client.instances.get(instance_name)

        if instance.status.lower() != "stopped":
            logger.error(f"Error: Instance '{instance_name}' is not stopped.")
            return False
        
        if not nic_device_name:
            device_name = DEFAULT_VM_NIC if instance.type == "virtual-machine" else DEFAULT_CNT_NIC
        else:
            device_name = nic_device_name # Use the specified NIC device name    
        
        # Build the network config using the extracted IP address and prefix length
        network_config = f"""
version: 2
ethernets:
  {device_name}:
    dhcp4: false
    addresses:
      - {ip_address}/{prefix_length}
    gateway4: {gw_address}
    nameservers:
      addresses:
        - {NAME_SERVER_IP_ADDR}
        - {NAME_SERVER_IP_ADDR_2}
"""
        instance.config['user.network-config'] = network_config
        instance.save(wait=True)
        logger.info(f"IP address '{ip_address}' with prefix length '{prefix_length}' and gateway '{gw_address}' assigned to instance '{instance_name}'.")
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to set IP address for instance '{instance_name}': {e}")
        return False
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return False
    return True

def get_all_profiles(client):
    """Get all available profiles."""
    return [profile.name for profile in client.profiles.all()]

def get_ip_and_gw(ip_address_and_prefix_len, gw_address, remote):
    """
    Determine the IP address and gateway for an instance based on inputs and defaults.

    Args:
    - ip_address_and_prefix_len: A string containing the IP address and prefix length (e.g., "192.168.1.10/24").
    - gw_address: The gateway address, if provided.
    - remote: The remote from which the IP address and gateway are to be assigned.

    Returns:
    A tuple containing (ip_address_with_prefix, gw_address)
    
    Raise an exception if there is an error:
    - the IP is already assigned
    - the gateway is not a valid IP address
    - the IP address is not a valid IP address
    - the IP address is not in the same subnet as the gateway
    - the gateway address is not found
    - the IP address is not found
    """
    #TODO: Implement the handling of the case when there are no available IP addresses

    remap_remote = remote
    if is_l1_host(remote):
        remap_remote = get_l0_remote(remote)

    # If IP address is not provided, assign one
    if ip_address_and_prefix_len is None:

        ip_address = assign_ip_address(remap_remote, mode="next")
        prefix_len = get_prefix_len(remap_remote)
    else:
        ip_address, prefix_len = ip_address_and_prefix_len.split('/')

        # Retrieve all assigned IP addresses
        assigned_ips = retrieve_assigned_ips(remap_remote)
        if assigned_ips is None:
            raise ValueError("Error: Failed to retrieve assigned IP addresses.")

        # Check if the provided IP address is already assigned
        if ip_address in assigned_ips:
            raise ValueError(f"Error: The IP address '{ip_address}' is already assigned.")

    # Combine IP address and prefix length into one string
    ip_address_with_prefix = f"{ip_address}/{prefix_len}"

    if gw_address :
        if not is_valid_ip(gw_address):
            raise ValueError(f"Error: gw address '{gw_address}' is not a valid IP address.")
    else:
    # If gateway is not provided, get the default for the remote
        gw_address = get_gw_address(remap_remote)

    if gw_address is None:
        raise ValueError(f"Error: Gateway address not found for remote '{remap_remote}'.")

    # check that gw_address is in the same subnet as ip_address
    if not is_same_subnet(ip_address, gw_address, prefix_len):
        raise ValueError(f"Error: gw address '{gw_address}' is not in the same subnet as ip address '{ip_address}/{prefix_len}'.")

    return ip_address_with_prefix, gw_address

def create_instance(instance_name, image, remote_name, project, instance_type, 
                    ip_address_and_prefix_len=None, gw_address=None, nic_device_name=None,
                    profiles=[], create_project_flag=False):
    """Create a new instance from a local or remote image with specified configurations.

    It assigns a static IP address and gateway to the instance.

    Args:
    - instance_name: Name of the instance.
    - image: Image source. If it starts with 'local:', it uses a local image; otherwise, it defaults to 'remote:image'.
    - remote_name: Remote server name.
    - project: Project name.
    - instance_type: Type of the instance ('vm' or 'container').
    - ip_address: Static IP address for the instance.
    - gw_address: Gateway address for the instance.
    - nic_device_name: Optional NIC device name for the instance.
    - instance_size: Optional size profile for the instance.

    Returns:
    True if the instance was created successfully, False otherwise.
    """

    try:
        remote_client = None
        try:
            remote_client = get_remote_client(remote_name, project_name=project, raise_project_not_found=True)  
        except ValueError as e:
            if "Project not found" in str(e) and create_project_flag:
                logger.info(f"Project '{project}' not found on remote '{remote_name}'. Creating project.")
                created_project = create_project(remote_name, project)
                if not created_project:
                    logger.error(f"Failed to create project '{project}' on remote '{remote_name}'.")
                    return False
                else:
                    logger.info(f"Project '{project}' created on remote '{remote_name}'.")
                remote_client = get_remote_client(remote_name, project_name=project)
        if not remote_client:
            logger.error(f"Failed to connect to remote '{remote_name}' and project '{project}'.")
            return False

        # set the as a profile the DEFAULT_INSTANCE_SIZE profile if none is provided
        if not profiles and DEFAULT_INSTANCE_SIZE:
            profiles = [DEFAULT_INSTANCE_SIZE]

        # Check if the project exists
        try:
            remote_client.projects.get(project)
            logger.info(f"Project '{project}' exists on remote '{remote_name}'.")
        except pylxd.exceptions.NotFound:
            logger.info(f"Project '{project}' does not exist on remote '{remote_name}'. Creating project.")
            if create_project_flag: # Create the project if the flag is set (second attempt, we should never reach this point)
                created_project = create_project(remote_name, project)
                if not created_project:
                    logger.error(f"2nd attempt failed to create project '{project}' on remote '{remote_name}'.")
                    return False

        # Check if the instance already exists
        try:
            existing_instance = remote_client.instances.get(instance_name)
            if existing_instance:
                logger.error(f"Instance '{instance_name}' already exists in project '{project}' on remote '{remote_name}'.")
                return False
        except pylxd.exceptions.LXDAPIException:
            pass  # Instance does not exist, proceed with creation

        # Handle image selection based on whether it is local or from a remote
        if image.startswith('local:'):
            # Local image (format: local:image)
            alias = image.split(':')[1]
            logger.info(f"Creating instance '{instance_name}' from local image '{alias}'.")

            # Retrieve the local image by alias
            try:
                image = remote_client.images.get_by_alias(alias)
                logger.info(f"Found local image with alias '{alias}', using fingerprint '{image.fingerprint}'.")
            except pylxd.exceptions.LXDAPIException:
                logger.error(f"Local image '{alias}' not found.")
                return False

            # Use the fingerprint instead of the alias
            config_source = {
                'type': 'image',
                'fingerprint': image.fingerprint  # Use the fingerprint of the local image
            }

        else:
            # Remote image (format: remote:image)
            image_server, alias = image.split(':')
            logger.info(f"Creating instance '{instance_name}' from remote image '{alias}' on server '{image_server}'.")

            # Get the image server address
            image_server_address, protocol = get_remote_address(image_server, get_protocol=True)
            
            if protocol != "simplestreams":
                logger.error(f"Error: Image server '{image_server}' does not use the 'simplestreams' protocol.")
                return False

            config_source = {
                'type': 'image',
                "mode": "pull",
                "server": image_server_address,
                "protocol": "simplestreams",
                'alias': alias
            }

        if not nic_device_name:
            device_name = DEFAULT_VM_NIC if instance_type == "vm" else DEFAULT_CNT_NIC
        else:
            device_name = nic_device_name  # Use the specified NIC device name

        try:
            ip_address_and_prefix_len, gw_address = get_ip_and_gw(ip_address_and_prefix_len, gw_address, remote_name)
        except ValueError as e:
            logger.error(f"Failed to assign IP address and gateway: {e}")
            return False

        logger.info(f"IP address: {ip_address_and_prefix_len}, Gateway: {gw_address}")

        final_profiles = ['default'] + profiles  # Add default and instance size profiles   
        # Create the instance configuration
        config = {
            'name': instance_name,
            'source': config_source,
            'profiles': final_profiles,  # Add default and instance size profiles
            'config': {
                'user.network-config': f"""
                version: 2
                ethernets:
                    {device_name}:
                        dhcp4: false
                        addresses:
                            - {ip_address_and_prefix_len}
                        gateway4: {gw_address}
                        nameservers:
                            addresses:
                                - {NAME_SERVER_IP_ADDR}
                                - {NAME_SERVER_IP_ADDR_2}
                """
            }
        }

        if instance_type == "vm":
            config['type'] = "virtual-machine"

        # Create the instance
        instance = remote_client.instances.create(config, wait=True)

        logger.info(f"Instance '{instance_name}' created successfully.")

        # if remote_name is a l1-host, set the l2 IP addresses
        # get the instance name from the remote_name
        # get the ip address from ip_address_and_prefix_len
        
        if is_l1_host(remote_name):
            # get the IP address from the ip_address_and_prefix_len
            ip_address = get_ip_string_from_ip_and_prefix(ip_address_and_prefix_len)

            client_instance = get_remote_client(get_l0_remote(remote_name), project_name="figo-stefano")
            if not client_instance:
                logger.error(f"Failed to connect to remote : '{remote_name}', project : 'figo-stefano'.")
                return None
            instance_object = client_instance.instances.get(get_l1_host(remote_name))

            my_result = add_l2_ip_address(instance_object, ip_address)
            if my_result:
                logger.info(f"Added l2 IP address '{ip_address}' to l1-host '{remote_name}'")
            else:
                logger.error(f"Failed to add l2 IP address '{ip_address}' to l1-host '{remote_name}'")
                return False # it is debatable if we should return False here because the instance has been added... 
                             # anyway the result value is not used

        return True

    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to create instance '{instance_name}': {e}")
        return False

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return False

def delete_instance(instance_name, remote, project, force=False):
    """Delete a specific instance on the specified remote and project.
    
    Returns:    True if the instance was deleted successfully, False otherwise.
    """
    try:
        remote_client = get_remote_client(remote, project_name=project) # Function to retrieve the remote client
        if not remote_client:
            logger.error(f"Failed to connect to remote '{remote}' and project '{project}'.")
            return False

        # Check if the instance exists
        try:
            instance = remote_client.instances.get(instance_name)
        except pylxd.exceptions.LXDAPIException:
            logger.error(f"Instance '{instance_name}' not found in project '{project}' on remote '{remote}'.")
            return False

        instance_state_dict = get_instance_state_dict (instance)

        # save the ip addresses of the instance to be deleted in a list called ip_addresses_to_delete
        ip_addresses_to_delete = get_ip_addresses(instance_state_dict)

        # Delete the instance
        if force:
            if instance.status.lower() == 'running':
                instance.stop(wait=True)
        instance.delete(wait=True)
        logger.info(f"Instance '{instance_name}' deleted successfully.")
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to delete instance '{instance_name}': {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return False

    # if remote is a l1-host, delete the l2 IP address from the l1-host using remove_l2_ip_address
    if is_l1_host(remote):
        client_instance = get_remote_client(get_l0_remote(remote), project_name="figo-stefano")
        if not client_instance:
            logger.error(f"Failed to connect to remote : '{remote}', project : 'figo-stefano'.")
            return None
        instance_object = client_instance.instances.get(get_l1_host(remote))

        boolean_result_list = []
        for ip_address in ip_addresses_to_delete:
            my_result = remove_l2_ip_address(instance_object, ip_address)
            boolean_result_list.append(my_result)

        if all(boolean_result_list):
            logger.info(f"Deleted all l2 IP addresses from l1-host '{remote}'")
        else:
            logger.error(f"Failed to delete at least one IP address from l1-host '{remote}'")

    return True

def exec_instance_bash(instance_name, remote, project, force=False, timeout=BASH_CONNECT_TIMEOUT, max_attempts=BASH_CONNECT_ATTEMPTS):
    """Execute a bash shell in a specific instance (container or VM).
    
    For VMs, the incus-agent must be running. If the agent is not running, retry connecting.

    Args:
    - instance_name: Name of the instance.
    - remote: Remote server name.
    - project: Project name.
    - force: If True, start the instance if it is not running.

    Returns:
    - False if it was not possible to execute the bash shell, True otherwise.
    """
    
    interval = timeout/max_attempts  # seconds

    try:
        # Determine the correct full instance name format
        full_instance_name = f"{remote}:{instance_name}" if remote != 'local' else instance_name

        was_started = False
        # Check if the instance is running
        remote_client = get_remote_client(remote, project_name=project)
        if not remote_client:
            logger.error(f"Failed to connect to remote '{remote}' and project '{project}'.")
            return False
        
        instance = remote_client.instances.get(instance_name)
        instance_type = instance.type  # "container" or "virtual-machine"

        # If the instance is not running, start it if force=True
        if instance.status.lower() != "running":
            if force:
                logger.info(f"Starting instance '{instance_name}'...")
                was_started = start_instance(instance.name, remote, project)
                if not was_started:
                    logger.error(f"Error: Instance '{instance_name}' failed to start.")
                    return False
            else:    
                logger.error(f"Instance '{instance_name}' is not running.")
                return False

        # If it's a VM, check if the incus-agent is running
        if instance_type == "virtual-machine":
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.info(f"Trying to connect to instance (attempt {attempt}/{max_attempts})...")
                    # Attempt to check if the incus-agent is running by executing a basic command
                    exec_result = instance.execute(["ls", "/"])
                    if exec_result.exit_code == 0:
                        # If successful, break the loop and continue
                        logger.info(f"Successfully connected to instance '{instance_name}'.")
                        break
                    else:
                        raise Exception("VM agent isn't currently running")
                except Exception as e:
                    if attempt < max_attempts:
                        time.sleep(interval)  # Wait for the interval before retrying
                    else:
                        logger.error(f"Error: VM agent isn't currently running in '{instance_name}' after {max_attempts} attempts (timeout = {BASH_CONNECT_TIMEOUT}). {e}")
                        if force and was_started:
                            # Stop the instance if we started it earlier
                            logger.info(f"Stopping instance '{instance_name}'...")
                            stop_instance(instance.name, remote, project)
                        return False
        
        # Build the bash command with the --project option if the project is not default
        command = ["incus", "exec", full_instance_name, "--project", project, "--", "bash"]

        # Execute the bash command interactively using subprocess
        subprocess.run(command, check=False, text=True)

        if force and was_started:
            # Stop the instance if we started it earlier
            result = stop_instance(instance.name, remote, project)
            if not result:
                logger.error(f"Error: Failed to stop instance '{instance_name}'")
                return False

        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to execute bash in instance '{remote}:{project}.{instance_name}': {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while executing bash in instance '{remote}:{project}.{instance_name}': {e}")
        return False

#############################################
###### figo gpu command functions ###########
#############################################

def show_gpu_status(client, extend=False):
    """Show the status of GPUs.
    
    It uses lspci to count NVIDIA GPUs
    I checks the total number of GPUs, the number of available GPUs, and the active GPU profiles.

    """
    try:
        result = subprocess.run('lspci | grep NVIDIA', capture_output=True, text=True, shell=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in lspci: {e.stderr.strip()}")
        return
    total_gpus = len(result.stdout.strip().split('\n'))

    running_instances = [
        i for i in client.instances.all() if i.status == "Running"
    ]
    active_gpu_profiles = [
        profile for instance in running_instances for profile in instance.profiles
        if profile.startswith("gpu-")
    ]

    available_gpus = total_gpus - len(active_gpu_profiles)

    gpu_profiles_str = ", ".join(active_gpu_profiles)
    COLS = [('TOTAL', 10), ('AVAILABLE', 10), ('ACTIVE', 10), ('PROFILES', 40)]
    add_header_line_to_output(COLS)
    add_row_to_output(COLS, [str(total_gpus), str(available_gpus), str(len(active_gpu_profiles)), gpu_profiles_str])
    flush_output(extend=extend)

def list_gpu_profiles(client, extend=False):
    """List all GPU profiles."""
    gpu_profiles = [
        profile.name for profile in client.profiles.all() if profile.name.startswith("gpu-")
    ]
    COLS = [('TOTAL', 10), ('PROFILES', 30)]
    add_header_line_to_output(COLS)
    add_row_to_output(COLS, [str(len(gpu_profiles)), ", ".join(gpu_profiles)])
    flush_output(extend=extend)

def add_gpu_profile(instance_name, client, remote='local', project='default'):
    """
    Add a GPU profile to a specified instance within an optional remote and project scope.

    This function checks if the given instance exists within the specified project and 
    remote, ensures that the instance is in a stopped state, and then adds an available 
    GPU profile to it if possible.

    Args:
        instance_name (str): The name of the instance to which the GPU profile will be added.
                             This can include the project and remote scope.
        client (pylxd.Client): The LXD client instance used to interact with the Incus server.
        remote (str, optional): The remote server where the instance is located. Defaults to 'local'.
        project (str, optional): The project under which the instance resides. Defaults to 'default'.

    Returns:
        bool: True if the GPU profile was added successfully, False otherwise.
    """
    try:
        full_instance_name = f"{remote}:{project}.{instance_name}" if remote != 'local' or project != 'default' else instance_name
        logger.info(f"Adding GPU profile to instance '{full_instance_name}'...")

        # Set the project on the client
        client = pylxd.Client(project=project)

        # Fetch the instance
        instance = client.instances.get(instance_name)

        if instance.status.lower() != "stopped":
            logger.error(f"Instance '{full_instance_name}' is running or in error state.")
            return False

        instance_profiles = instance.profiles
        gpu_profiles_for_instance = [
            profile for profile in instance_profiles if profile.startswith("gpu-")
        ]
        
        try:
            result = subprocess.run('lspci | grep NVIDIA', capture_output=True, text=True, shell=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error in lspci: {e.stderr.strip()}")
            return False
        
        total_gpus = len(result.stdout.strip().split('\n'))

        if len(gpu_profiles_for_instance) >= total_gpus:
            logger.error(f"Instance '{full_instance_name}' already has the maximum number of GPU profiles.")
            return False

        all_profiles = get_all_profiles(client)
        available_gpu_profiles = [
            profile for profile in all_profiles if profile.startswith("gpu-")
            and profile not in instance_profiles
        ]

        if not available_gpu_profiles:
            logger.error(f"No available GPU profiles to add to instance '{full_instance_name}'.")
            return False

        new_profile = available_gpu_profiles[0]
        instance_profiles.append(new_profile)
        instance.profiles = instance_profiles
        instance.save(wait=True)

        logger.info(f"Added GPU profile '{new_profile}' to instance '{full_instance_name}'.")
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to add GPU profile to instance '{full_instance_name}': {e}")
        return False
    
    return True

def remove_gpu_all_profiles(instance_name, client):
    """Remove all GPU profiles from an instance."""
    try:
        instance = client.instances.get(instance_name)
        if instance.status.lower() != "stopped":
            logger.error(f"Instance '{instance_name}' is running or in error state.")
            return

        instance_profiles = instance.profiles
        gpu_profiles_for_instance = [
            profile for profile in instance_profiles if profile.startswith("gpu-")
        ]

        if not gpu_profiles_for_instance:
            logger.error(f"Instance '{instance_name}' has no GPU profiles to remove.")
            return

        for gpu_profile in gpu_profiles_for_instance:
            instance_profiles.remove(gpu_profile)

        instance.profiles = instance_profiles
        instance.save(wait=True)

        logger.info(
            f"Removed all GPU profiles from instance '{instance_name}'."
        )
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(
            f"Failed to remove GPU profiles from instance '{instance_name}': {e}"
        )

def remove_gpu_profile(instance_name, client):
    """Remove a GPU profile from an instance."""
    try:
        instance = client.instances.get(instance_name)
        if instance.status.lower() != "stopped":
            logger.error(f"Instance '{instance_name}' is running or in error state.")
            return

        instance_profiles = instance.profiles
        gpu_profiles_for_instance = [
            profile for profile in instance_profiles if profile.startswith("gpu-")
        ]

        if not gpu_profiles_for_instance:
            logger.error(f"Instance '{instance_name}' has no GPU profiles to remove.")
            return

        profile_to_remove = gpu_profiles_for_instance[0]
        instance_profiles.remove(profile_to_remove)
        instance.profiles = instance_profiles
        instance.save(wait=True)

        logger.info(
            f"Removed GPU profile '{profile_to_remove}' from instance '{instance_name}'."
        )
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(
            f"Failed to remove GPU profile from instance '{instance_name}': {e}"
        )

#############################################
###### figo profile command functions #######
#############################################

def dump_profile_to_file(profile, directory):
    """Helper function to write a profile to a .yaml file.

    only the name, description, config, and devices are saved.
    the file is saved in the specified directory with the profile name as the file name.
    #TODO it only work for local profiles, not remote profiles.

    """
    profile_data = {
        'name': profile.name,
        'description': profile.description,
        'config': profile.config,
        'devices': profile.devices
    }
    file_name = os.path.join(directory, f"{profile.name}.yaml")
    with open(file_name, 'w') as file:
        yaml.dump(profile_data, file)
    logger.info(f"Profile '{profile.name}' saved to '{file_name}'.")

def dump_profiles(client):
    """Dump all profiles into .yaml files."""
    profiles = client.profiles.all()
    directory = os.path.expanduser(PROFILE_DIR)
    
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    for profile in profiles:
        dump_profile_to_file(profile, directory)

def dump_profile(client, profile_name):
    """Dump a specific profile into a .yaml file.
    
    Retuns true if the profile was dumped successfully, false otherwise.
    """
    try:
        profile = client.profiles.get(profile_name)
        directory = os.path.expanduser(PROFILE_DIR)
        
        if not os.path.exists(directory):
            os.makedirs(directory)
        
        dump_profile_to_file(profile, directory)
    
    except pylxd.exceptions.NotFound:
        logger.error(f"Profile '{profile_name}' not found.")
        return False
    
    except Exception as e:
        logger.error(f"Failed to dump profile '{profile_name}': {e}")
        return False
    
    return True

def show_profile(remote, project, profile_name):
    """Display the details of a profile.
    
    Returns True if the profile was displayed successfully, False otherwise.
    """
    if not profile_name:
        logger.error("Error: Profile name must be specified.")
        return False

    if not remote:
        logger.error("Error: Remote name must be specified.")
        return False
    
    if not project:
        logger.error("Error: Project name must be specified.")
        return False

    print(f" remote: {remote}, project: {project}, profile_name: {profile_name}") # debug


    try:
        # Handle retrieving the client based on remote and project (if needed)
        client = get_remote_client(remote, project_name=project)
        profile = client.profiles.get(profile_name)

        profile_data = {
            'name': profile.name,
            'description': profile.description,
            'config': profile.config,
            'devices': profile.devices
        }
        print(yaml.dump(profile_data, default_flow_style=False))
    except pylxd.exceptions.NotFound:
        logger.error(f"Profile '{profile_name}' not found in project '{project}' on remote '{remote}'.")
        return False
    except Exception as e:
        logger.error(f"Failed to retrieve profile '{profile_name}': {e}")
        return False
    
    return True


def list_profiles_specific(remote, project, profile_name=None, COLS=None):
    """List all profiles on a specific remote and project optionally with a match on profile_name
    
    For each profile, list the associated instances.
    
    Returns:    False if fetching the profiles failed, True otherwise.
    """
    client = get_remote_client(remote, project_name=project)
    if not client:
        logger.error(f"Failed to retrieve client for '{remote}:{project}'.")
        return False
    
    #check if the project exists
    try:
        client.projects.get(project)
    except pylxd.exceptions.NotFound:
        logger.error(f"Project '{project}' does not exist on remote '{remote}'.")
        return False

    try:
        profiles = client.profiles.all()
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to retrieve profiles from '{remote}:{project}': {e}")
        return False

    for profile in profiles:
        if profile_name and not matches(profile.name, profile_name):
            continue
        instances = client.instances.all()
        associated_instances = [
            instance.name for instance in instances
            if profile.name in instance.profiles
        ]
        context = f"{remote}:{project}" 
        associated_instances_str = ', '.join(associated_instances) if associated_instances else 'None'
        add_row_to_output(COLS, [profile.name, context, associated_instances_str])

    return True

def list_profiles(remote, project, profile_name=None, inherited=False, extend=False):
    """
    List profiles overall or on specific remote and project optionally with a match on profile_name.

    - If remote and project are not specified, list all profiles on all remotes and projects.
    - If remote is specified but project is not, list all profiles on the remote.
    - If project is specified but remote is not, list all profiles on the project on all remotes.
    - If remote and project are specified, list all profiles on the remote and project.
    - If `inherited` is False, skip profiles from projects where `features.profiles` is False.
    - extend: If True, adapts the output column width to the content.

    Returns:    False if fetching the profiles failed, True otherwise.
    """

    COLS = [('PROFILE', 25), ('CONTEXT', 25), ('INSTANCES', 80)]
    add_header_line_to_output(COLS)

    if remote and project:
        try:
            remote_client = None
            remote_client = get_remote_client(remote, project_name=project, raise_project_not_found=True, show_info=False)
        except ValueError as e:
            if "Project not found" in str(e):
                pass # the project is not found
            else:
                logger.error(f"Failed to retrieve client for '{my_remote_node}:{project}': {e}.")
                return False 
        except Exception as e:
            logger.error(f"Failed to retrieve client for '{my_remote_node}:{project}': {e}")
            return False
        if not remote_client:
            return False

        profiles_managed_separately_for_project = check_profiles_feature(remote, project, remote_client=remote_client)
        if profiles_managed_separately_for_project is None:
            logger.error(f"Failed to check the 'features.profiles' value for '{remote}:{project}'.")
            return False  # Error occurred while checking the target project
        if not inherited and not profiles_managed_separately_for_project:
            return False  # Skip profiles from projects where `features.profiles` is False
        return list_profiles_specific(remote, project, profile_name, COLS)

    elif remote:  # list all profiles on the remote
        for project in iterator_over_projects(remote):
            profiles_managed_separately_for_project = check_profiles_feature(remote, project["name"])
            if profiles_managed_separately_for_project is None:
                logger.error(f"Failed to check the 'features.profiles' value for '{remote}:{project}'.")
                return False  # Error occurred while checking the target project            
            if not inherited and not profiles_managed_separately_for_project:
                continue
            list_profiles_specific(remote, project["name"], profile_name, COLS)

    else:  # list all profiles on all remotes associated with all the project or with a specific project
        remotes = get_incus_remotes()
        for my_remote_node in remotes:
            # check to skip all the remote nodes of type images
            if remotes[my_remote_node]["Protocol"] == "simplestreams":
                continue        
            if project: # a specific project is specified
                try:
                    remote_client = get_remote_client(my_remote_node, project_name=project, raise_project_not_found=True, show_info=False)
                except ValueError as e:
                    if "Project not found" in str(e):
                        continue # skip the remote node because the project is not found
                    else:
                        logger.error(f"Failed to retrieve client for '{my_remote_node}:{project}': {e}.")
                        return False 
                except Exception as e:
                    logger.error(f"Failed to retrieve client for '{my_remote_node}:{project}': {e}")
                    return False

                profiles_managed_separately_for_project = check_profiles_feature(my_remote_node, project, remote_client=remote_client)
                if profiles_managed_separately_for_project is None:
                    logger.error(f"Failed to check the 'features.profiles' value for '{remote}:{project}'.")
                    return False  # Error occurred while checking the target project            
                if not inherited and not profiles_managed_separately_for_project:
                    continue
                list_profiles_specific(my_remote_node, project, profile_name, COLS)
            else: # all the projects
                for my_project in iterator_over_projects(my_remote_node):
                    profiles_managed_separately_for_project = check_profiles_feature(my_remote_node, my_project["name"])
                    if profiles_managed_separately_for_project is None:
                        logger.error(f"Failed to check the 'features.profiles' value for '{remote}:{project}'.")
                        return False  # Error occurred while checking the target project                              
                    if not inherited and not profiles_managed_separately_for_project:
                        continue
                    list_profiles_specific(my_remote_node, my_project["name"], profile_name, COLS)
    
    flush_output(extend=extend)

def check_profiles_feature(remote, project, remote_client=None):
    """
    Check if the 'features.profiles' value is True for the specified project on the remote.
    If True, profiles are managed within the project; 
    If False, profiles are inherited from the default project.

    Args:
    - remote (str): The name of the remote.
    - project (str): The name of the project.
    - remote_client (pylxd.Client, optional): An existing pylxd client for the remote. If provided, it will be used instead of creating a new client.

    Returns:
    - bool: True if profiles are managed within the project, False if profiles are inherited from the default project.
    - None if the project is not found or an error occurs.
    """
    try:
        # Use the provided remote_client if available, otherwise create a new one
        client = remote_client if remote_client else get_remote_client(remote, project_name=project)
        if not client:
            logger.error(f"Failed to retrieve client for '{remote}:{project}'.")
            return None
        project_data = client.projects.get(project)
        return project_data.config.get('features.profiles', 'false') == 'true'
    except pylxd.exceptions.NotFound:
        logger.error(f"Project '{project}' not found on remote '{remote}'.")
        return None
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to retrieve project '{project}' on remote '{remote}': {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while checking profiles feature: {e}")
        return None

def copy_profile(source_remote, source_project, source_profile, target_remote, target_project, target_profile):
    """Copy a profile from one location to another with error handling, including the description.
    
    Return True if the profile was copied successfully, False otherwise.
    """
    try:
        # Get the source and target clients
        source_client = get_remote_client(source_remote, project_name=source_project)
        if not source_client:
            logger.error(f"Failed to retrieve client for '{source_remote}:{source_project}'.")
            return False 
        target_client = get_remote_client(target_remote, project_name=target_project)
        if not target_client:
            logger.error(f"Failed to retrieve client for '{target_remote}:{target_project}'.")
            return False

        # Check the project's config for 'features.profiles' in the target project
        check_result = check_profiles_feature(target_remote, target_project, remote_client=target_client)
        if check_result is None:
            logger.error(f"Failed to check the 'features.profiles' value for '{target_remote}:{target_project}'.")
            return False  # Error occurred while checking the target project
        if not check_result:
            logger.error(f"Cannot copy profile '{source_profile}' to '{target_remote}:{target_project}'"
                         " because the target project inherits profiles from the default project.")
            return False

        # Verify if the source profile exists
        try:
            # Fetch the source profile (may trigger a warning due to the 'project' attribute)
            profile = source_client.profiles.get(source_profile)
        except pylxd.exceptions.NotFound:
            logger.error(f"Source profile '{source_profile}' not found in '{source_remote}:{source_project}'.")
            return False
        except pylxd.exceptions.LXDAPIException as e:
            logger.error(f"Failed to retrieve source profile '{source_profile}' from '{source_remote}:{source_project}': {e}")
            return False

        # Check if the target profile already exists
        try:
            target_client.profiles.get(target_profile)
            logger.error(f"Target profile '{target_profile}' already exists in '{target_remote}:{target_project}'.")
            return False
        except pylxd.exceptions.NotFound:
            pass  # Profile does not exist, proceed with creation
        except pylxd.exceptions.LXDAPIException as e:
            logger.error(f"Failed to check if target profile '{target_profile}' exists on '{target_remote}:{target_project}': {e}")
            return False

        # Prepare and create the target profile with the correct structure, including the description
        try:
            target_client.profiles.create(
                name=target_profile,
                config=profile.config.copy(),
                devices=profile.devices.copy(),
                description=profile.description  # Copy the description
            )
            logger.info(f"Profile '{source_remote}:{source_project}.{source_profile}' successfully copied to '{target_remote}:{target_project}.{target_profile}'.")
            return True
        except pylxd.exceptions.LXDAPIException as e:
            logger.error(f"Failed to create target profile '{target_profile}' on '{target_remote}:{target_project}': {e}")
            return False

    except Exception as e:
        logger.error(f"An unexpected error occurred while copying profile: {e}")
        return False

def delete_profile(remote, project, profile_name):
    """
    Delete a profile from a specific remote and project.

    Returns:
    - True if the profile was successfully deleted.
    - False if the profile could not be deleted due to an error or project configuration.
    """
    try:
        client = get_remote_client(remote, project_name=project)
        if not client:
            logger.error(f"Failed to retrieve client for '{remote}:{project}'.")
            return False

        # Check the project's config for 'features.profiles'

        check_result = check_profiles_feature(remote, project, remote_client=client)
        if check_result is None:
            logger.error(f"Failed to check the 'features.profiles' value for '{remote}:{project}'.")
            return False  # Error occurred while checking the target project
        if not check_result:
            logger.error(f"Cannot delete profile '{profile_name}' from '{remote}:{project}'"
                         " because the project inherits profiles from the default project.")
            return False

        # Proceed with profile deletion
        profile = client.profiles.get(profile_name)
        profile.delete()
        logger.info(f"Profile '{profile_name}' successfully deleted from '{remote}:{project}'.")
        return True

    except pylxd.exceptions.NotFound:
        logger.error(f"Profile '{profile_name}' not found in '{remote}:{project}'.")
        return False
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to delete profile '{profile_name}' on '{remote}:{project}': {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while deleting profile: {e}")
        return False


#############################################
###### figo user command functions ##########
#############################################

def list_users(client, full=False, extend=False):
    """List all installed certificates with optional full details, adding email, name, and org details with specified lengths."""

    certificates_info = []

    for certificate in client.certificates.all():
        name = certificate.name or "__N/A__"
        fingerprint = certificate.fingerprint[:12]

        # Fetch detailed information about the certificate using incus command
        try:
            result = subprocess.run(["incus", "config", "trust", "show", fingerprint], capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to retrieve certificate details: {e.stderr.strip()}")
            continue
        user_cert_yaml = yaml.safe_load(result.stdout)  # Load the certificate configuration into a dictionary

        # Parse email, name, and organization from the description if available
        description = user_cert_yaml.get('description', '')
        description_parts = description.split(',') if description else ['', '', '']
        # Ensure that description_parts has exactly three elements
        description_parts += [''] * (3 - len(description_parts))  # Pad list to avoid index errors

        email = truncate(description_parts[0], 30)
        real_name = truncate(description_parts[1], 20)
        org = truncate(description_parts[2], 15)
        projects = ", ".join(certificate.projects) if certificate.projects else "None"
        admin_status = 'no' if certificate.restricted else 'yes'

        certificates_info.append({
            "name": name,
            "fingerprint": fingerprint,
            "type": certificate.type[:3],
            "admin": admin_status,
            "email": email,
            "real_name": real_name,
            "org": org,
            "projects": projects
        })

    # Sort certificates by name
    certificates_info.sort(key=lambda x: x["name"])

    # Print headers
    if full:
        COLS= [('NAME', 18), ('FINGERPRINT', 12), ('TYPE', 4), ('ADMIN', 5), ('EMAIL', 30),
               ('REAL NAME', 20), ('ORGANIZATION', 15), ('PROJECTS', 20)]
    else:
        COLS = [('NAME', 20), ('FINGERPRINT', 12)]
    add_header_line_to_output(COLS)

    # Print sorted certificates
    for cert in certificates_info:
        if full:
            add_row_to_output(COLS, [cert["name"], cert["fingerprint"], cert["type"], cert["admin"],
                             cert["email"], cert["real_name"], cert["org"], cert["projects"]])
        else:
            add_row_to_output(COLS, [cert["name"], cert["fingerprint"]])

    flush_output(extend=extend)

def get_next_wg_client_ip_address():
    # List to contain the IP addresses found in .conf files
    ip_addresses = []

    directory = os.path.expanduser(USER_DIR)

    # Search for all .conf files in the directory folder
    for filename in os.listdir(directory):
        if filename.endswith('.conf'):
            file_path = os.path.join(directory, filename)  # Construct the full path to the file
            with open(file_path, 'r') as file:
                for line in file:
                    if line.startswith('Address ='):
                        ip_str = line.split('=')[1].strip().split('/')[0]
                        ip_addresses.append(ip_str)
                        break
    
    if not ip_addresses:
        # If no IP addresses are found, start from BASE_IP
        return BASE_IP
    
    # Convert IP addresses to ip_address objects and sort
    ip_addresses = sorted([ipaddress.ip_address(ip) for ip in ip_addresses])

    # Find the next available IP address
    last_ip = ip_addresses[-1]
    next_ip = last_ip + 1
    
    return str(next_ip)

def generate_wireguard_config(username, ip_address=None):
    """
    Generate WireGuard configuration for a user, saving both the private key in the config file
    and the public key in a separate .wgpub file.

    Args:
    - username (str): Username for which to generate the WireGuard configuration.
    - ip_address (str, optional): IP address to assign to the user. If not provided, a new one is generated.

    Returns:
    - Tuple containing the public key and IP address assigned to the user if successful, or (None, None) otherwise.
    """
    try:
        # If no IP address is provided, generate a new one
        if not ip_address:
            ip_address = get_next_wg_client_ip_address()

        # Generate the private and public keys using wg
        key_file = f"{username}.tempkey"
        private_key = subprocess.check_output(f"wg genkey | tee {key_file}", shell=True).decode('utf-8').strip()
        public_key = subprocess.check_output(f"wg pubkey < {key_file}", shell=True).decode('utf-8').strip()

        # WireGuard configuration template
        config_content = f"""[Interface]
PrivateKey = {private_key}
Address = {ip_address}/24

[Peer]
PublicKey = {public_key}
AllowedIPs = {AllowedIPs}
Endpoint = {Endpoint}
"""

        directory = os.path.expanduser(USER_DIR)

        # Ensure the directory exists
        if not os.path.exists(directory):
            os.makedirs(directory)

        # Write the WireGuard configuration to the .conf file
        config_filename = os.path.join(directory, f"{username}.conf")
        with open(config_filename, 'w') as config_file:
            config_file.write(config_content)

        # Write the public key to a separate .wgpub file
        public_key_filename = os.path.join(directory, f"{username}.wgpub")
        with open(public_key_filename, 'w') as pubkey_file:
            pubkey_file.write(public_key + '\n')

        # Delete the temporary key file after use
        try:
            os.remove(key_file)
            logger.info(f"Deleted temporary key file: {key_file}")
        except OSError as e:
            logger.error(f"Failed to delete temporary key file {key_file}: {e}")

        logger.info(f"Generated WireGuard configuration: {config_filename}, IP address: {ip_address}")
        logger.info(f"Saved public key: {public_key_filename}")

        return public_key, ip_address

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to generate WireGuard configuration: {e}")
        return None, None
    except Exception as e:
        logger.error(f"An unexpected error occurred while generating WireGuard configuration: {e}")
        return None, None

def add_friendly_name(pfx_file, friendly_name, password=None):
    """Add a friendlyName attribute to the existing PFX file, overwriting the original.
    
    Return true if the friendlyName was added successfully, false otherwise.
    """
    temp_pem_file = "temp.pem"
    temp_pfx_file = "temp_with_friendlyname.pfx"

    try:    

        # Convert the existing PFX to PEM format
        openssl_cmd = [
            "openssl", "pkcs12", "-in", pfx_file, "-out", temp_pem_file, "-nodes"
        ]
        if password:
            openssl_cmd.extend(["-password", f"pass:{password}"])

        subprocess.run(openssl_cmd, check=True, capture_output=True, text=True)

        # Prepare the command to create the new PFX file with friendlyName
        openssl_cmd = [
            "openssl", "pkcs12", "-export", "-in", temp_pem_file, "-out", temp_pfx_file,
            "-name", friendly_name
        ]
        if password:
            openssl_cmd.extend(["-passin", f"pass:{password}", "-passout", f"pass:{password}"])
        else:
            openssl_cmd.extend(["-passout", "pass:"])

        subprocess.run(openssl_cmd, check=True, capture_output=True, text=True)

        # Replace the original PFX file with the new one
        subprocess.run(["mv", temp_pfx_file, pfx_file], capture_output=True, text=True)

        # Clean up temporary files
        subprocess.run(["rm", temp_pem_file], capture_output=True, text=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to add friendlyName to PFX file: {e.stderr.strip()}")
        return False
    except FileNotFoundError:
        logger.error("OpenSSL is not installed or not found in the system's PATH.")
        return False
    except Exception as e:
        logger.error(f"An error occurred while adding friendlyName to PFX file: {e.stderr.strip()}")
        return False

    logger.info(f"PFX file with friendlyName updated: {pfx_file}")
    return True

def generate_key_pair(user_name, crt_file, key_file, pfx_file, pfx_password=None):
    """Generate key pair (CRT and PFX files) for the user.

    Parameters:
    - user_name: Name of the user
    - crt_file: Path to the certificate file
    - key_file: Path to the private key file (PEM format) temporary file
    - pfx_file: Path to the PFX file
    - pfx_password: Password for the PFX file (optional)

    Returns:
    - True if the key pair was generated successfully, False otherwise
    """

    try:
        # Generate private key
        private_key = cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=cryptography.hazmat.backends.default_backend()
        )

        # Generate a self-signed certificate with detailed subject and issuer information
        subject = issuer = cryptography.x509.Name([
            cryptography.x509.NameAttribute(cryptography.x509.oid.NameOID.COUNTRY_NAME, u"IT"),
            cryptography.x509.NameAttribute(cryptography.x509.oid.NameOID.STATE_OR_PROVINCE_NAME, u"RM"),
            cryptography.x509.NameAttribute(cryptography.x509.oid.NameOID.ORGANIZATION_NAME, u"Restart"),
            cryptography.x509.NameAttribute(cryptography.x509.oid.NameOID.COMMON_NAME, f"{FIGO_PREFIX}{user_name}")  # Add the user_name as the Common Name (CN)
        ])

        # Set the certificate validity to 2 years
        certificate = cryptography.x509.CertificateBuilder() \
            .subject_name(subject) \
            .issuer_name(issuer) \
            .public_key(private_key.public_key()) \
            .serial_number(cryptography.x509.random_serial_number()) \
            .not_valid_before(datetime.datetime.utcnow()) \
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=2*365)) \
            .sign(private_key, cryptography.hazmat.primitives.hashes.SHA256(), cryptography.hazmat.backends.default_backend())

        # Write the private key to a file
        try:
            with open(key_file, "wb") as key_out:
                key_out.write(private_key.private_bytes(
                    cryptography.hazmat.primitives.serialization.Encoding.PEM,
                    cryptography.hazmat.primitives.serialization.PrivateFormat.TraditionalOpenSSL,
                    cryptography.hazmat.primitives.serialization.NoEncryption()
                ))
        except IOError as e:
            logger.error(f"Failed to write private key to {key_file}: {e}")
            return False

        # Write the certificate to a file
        try:
            with open(crt_file, "wb") as crt:
                crt.write(certificate.public_bytes(cryptography.hazmat.primitives.serialization.Encoding.PEM))
        except IOError as e:
            logger.error(f"Failed to write certificate to {crt_file}: {e}")
            return False

        # Use OpenSSL to create the PFX file with specific settings
        openssl_cmd = [
            "openssl", "pkcs12", "-export",
            "-out", pfx_file,
            "-inkey", key_file,
            "-in", crt_file,
            "-certpbe", "PBE-SHA1-3DES",  # Use SHA1 and 3DES for encryption
            "-keypbe", "PBE-SHA1-3DES",   # Use SHA1 and 3DES for the key
            "-macalg", "sha1",             # Use SHA1 for MAC
            "-iter", "2048"                # Set iteration count to 2048
        ]

        if pfx_password:
            openssl_cmd.extend(["-passout", f"pass:{pfx_password}"])

        try:
            subprocess.run(openssl_cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"OpenSSL command failed: {e}")
            return False
        except FileNotFoundError:
            logger.error("OpenSSL is not installed or not found in the system's PATH.")
            return False

        # Delete the key file because it is no longer needed (the PFX file contains the key)
        try:
            subprocess.run(["rm", key_file], check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to delete key file {key_file}: {e.stderr.strip()}")
            return False

        # Add a friendly name to the PFX file
        result = add_friendly_name(pfx_file, f"{FIGO_PREFIX}{user_name}", password=pfx_password)
        
        if not result:
            logger.error(f"Failed to add a friendly name to the PFX file {pfx_file}: {e}")
            return False

        logger.info(f"PFX file generated: {pfx_file}")
        return True

    except Exception as e:
        logger.error(f"An error occurred while generating the key pair: {e}")
        return False

def create_project(remote_name, project_name):
    """Create a project with the specified name and disable separate profiles.

    client_name: the name of the node (remote or local) on which the project will be created.

    Returns:
    - True if the project was created successfully, False otherwise.
    """
    try:
        # Explicitly define the project details as a dictionary
        project_data = {
            "name": project_name,  # The project's name (string)
            "description": f"Project for user {project_name}",  # Optional description
            "config": {
                "features.profiles": "false",  # Disable separate profiles for this project; 
                                               # profiles from the default project will be inherited
                "features.images": "false"     # Disable separate images for this project
                                               # images from the default project will be inherited
            }
        }
        client_object = get_remote_client(remote_name, project_name=project_name, test_project=False)
        if not client_object:
            logger.error(f"Failed to retrieve client for remote '{remote_name}'.")
            return False

        # Creating the project using the correct format
        client_object.api.projects.post(json=project_data)
        logger.info(f"Project '{project_name}'"
                    " created successfully with features.profiles and .images set to false.")
        return True

    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Error creating project '{project_name}': {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during creation of project: '{project_name}': {str(e)}")
        return False

def edit_certificate_description(client, user_name, email=None, name=None, org=None):
    """Edit the description of a certificate in Incus by the user name.

    Args:
    - user_name: The username associated with the certificate.
    - email: Email address of the user.
    - name: Name of the user.
    - org: Organization of the user.

    Returns:
    True if the description was successfully added, False otherwise.
    """

    if email==None and name==None and org==None:
        logger.info("Warning: certificate description not changed.")
        return True
    
    try:
        # Step 1: Retrieve the certificate by username
        certificates = client.certificates.all()
        user_cert = None
        for cert in certificates:
            if cert.name == user_name:
                user_cert = cert
                break
        
        if not user_cert:
            logger.error(f"User '{user_name}' not found.")
            return
        
        fingerprint = user_cert.fingerprint[:24]

        # Step 2: load the user_cert into a temporary .YAML object using incus config trust show
        result = subprocess.run(["incus", "config", "trust", "show", fingerprint], capture_output=True, text=True, check=True)
        user_cert_yaml = yaml.safe_load(result.stdout)   # Load the certificate configuration into a dictionary
        
        if not user_cert_yaml:
            logger.error(f"Failed to load certificate configuration for '{user_name}'.")
            return False
        
        if "description" not in user_cert_yaml:
            user_cert_yaml["description"] = ""

        original_description = user_cert_yaml["description"] # Get the original description
        target_email = ''
        target_name = ''
        target_org = ''
        if original_description == "":
            pass
        else:
            target_email, target_name, target_org = original_description.split(",")

        if email!=None:
            target_email = email
        if name!=None:
            target_name = name
        if org!=None:
            target_org = org

        # Format the description with the additional user details
        description = f"{target_email},{target_name},{target_org}"  # Format: email,name,org

        if description == ",,":
            description = ""

        user_cert_yaml["description"] = description  # Update the description

        # Step 3: Save the updated configuration to a temporary file
        temp_file = f"/tmp/{user_name}.yaml"
        with open(temp_file, "w") as f:
            yaml.dump(user_cert_yaml, f)
        
        # Step 4: Update the certificate configuration using incus config trust edit
        # The command is: cat temp_file | incus config trust edit fingerprint

        cat_process = subprocess.Popen(
            ['cat', temp_file], 
            stdout=subprocess.PIPE  # Redirect the output to a pipe
        )

        # Create a subprocess to run 'incus config trust edit fingerprint'
        # using the output of the first command as input
        incus_process = subprocess.Popen(
            ['incus', 'config', 'trust', 'edit', fingerprint], 
            stdin=cat_process.stdout,  # Use output of cat as input
            stdout=subprocess.PIPE  # Redirect the output to a pipe if needed
        )

        # Close the output of the first process to allow it to receive a SIGPIPE if the second exits
        cat_process.stdout.close()

        # Get the output of the second command if needed
        output, error = incus_process.communicate()

        if incus_process.returncode != 0:
            logger.error("Error in executing incus command:", error)
            return False

        logger.info(f"Description added to certificate '{user_name}'.")

        # Step 5: Remove the temporary file
        os.remove(temp_file)
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to edit certificate description: {e.stderr.strip()}")
        return False
    
    except Exception as e:
        logger.error(f"Unexpected error while editing description: {e}")
        return False

def add_certificate_to_incus(client, user_name, crt_file, project_name, admin=False, email=None, name=None, org=None):
    """Add user certificate to Incus
    
    If the user is an admin, the certificate is added without any restrictions.
    If the user is not an admin, the certificate is restricted to the specified project.

    Args:
    - user_name: The username associated with the certificate.
    - crt_file: Path to the certificate file.
    - project_name: Name of the project to restrict the certificate to.
    - admin: Specifies if the user has admin privileges.
    - email: Email address of the user.
    - name: Name of the user.
    - org: Organization of the user.

    Returns:
    True if the certificate is added successfully, False otherwise.
    """
    try:
        command = [
            "incus", "config", "trust", "add-certificate", crt_file, 
            f"--name={user_name}"
        ]

        if not admin:
            command.extend([
                "--restricted", 
                f"--projects={project_name}"
            ])

        # Execute the command
        subprocess.run(command, capture_output=True, text=True, check=True)
        logger.info(f"Certificate '{user_name}' added to Incus.")

        # Edit the certificate's description if needed
        if email!=None or name!=None or org!=None:
            logger.info(f"Adding description to certificate '{user_name}'")
            if not edit_certificate_description(client, user_name, email, name, org):
                logger.error(f"Failed to add description to certificate '{user_name}'.")
                return False

        return True

    except subprocess.CalledProcessError as e:
        # Print the exact error message from the command's stderr
        logger.error(f"Failed to add certificate to Incus: {e.stderr.strip()}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error while adding certificate: {e}")
        return False

def delete_project(remote_node, project_name):
    """
    Delete a project on a specific remote node (can also be local:)

    Parameters:
    - remote_node: Name of the remote node where the project is located
    - project_name: Name of the project to delete

    Returns: True if the project was deleted successfully, False otherwise.
    """
    logger.info(f"Deleting project '{project_name}' on remote '{remote_node}'")
    
    remote_client = get_remote_client(remote_node, project_name=project_name)
    if not remote_client:
        logger.error(f"Failed to retrieve client for remote '{remote_node}', project_name '{project_name}'.")
        return False

    try:
        # Retrieve the project from the remote node
        project = remote_client.projects.get(project_name)
        
        # Delete the project
        project.delete()
        logger.info(f"Deleted project '{project_name}' on remote '{remote_node}'")

    except pylxd.exceptions.NotFound:
        logger.error(f"Project '{project_name}' not found on the remote node. No action taken.")
        return False
        
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to delete project '{project_name}' on remote '{remote_node}: {e}")
        return False
    
    except Exception as e:
        logger.error(f"Unexpected error while deleting project '{project_name}' on remote '{remote_node}: {e}")
        return False
    
    return True

def generate_ssh_key_pair(username, private_key_file):
    """
    Generate an Ed25519 SSH key pair for the user.

    Args:
    - username (str): Username for whom the keys are being generated.
    - private_key_file (str): Full path to the private key file.
    
    The public key is saved to a file with the same name as the private key file,
    but with the .pub extension.

    Returns:
    True if the key pair was generated successfully, False otherwise.
    """
    try:
        
        # Generate the private key using ssh-keygen
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", private_key_file, "-N", ""],
            check=True,
        )
        
        logger.info(f"Generated SSH Ed25519 key pair for user '{username}'"
                    f" with private key: {private_key_file} and public key: {private_key_file}.pub")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to generate SSH key pair for user '{username}': {e}")
        return False

def add_wireguard_vpn_user_on_mikrotik(public_key, ip_address, vpnuser, username=SSH_MIKROTIK_USER_NAME, 
                                 host=SSH_MIKROTIK_HOST, port=SSH_MIKROTIK_PORT, interface=WG_INTERFACE, 
                                 keepalive=WG_VPN_KEEPALIVE):
    """
    Configures a MikroTik switch with a new WireGuard VPN user.
    It is optinally executed in the add_user function, if the command line argument -s, --set_vpn is provided.

    Args:
    - public_key (str): The WireGuard public key of the new VPN user.
    - ip_address (str): The allowed IP address (without prefix) for the VPN user
    - vpnuser (str): The VPN username, added as a comment for identification.
    - username (str, optional): The SSH username to connect to the MikroTik switch. Default is 'admin'.
    - host (str, optional): The IP address or hostname of the MikroTik switch. Default is '192.168.88.1'.
    - port (int, optional): The SSH port for the MikroTik switch. Default is 22.
    - interface (str, optional): The WireGuard interface on the MikroTik switch. Default is 'wireguard2'.
    - keepalive (str, optional): The persistent keepalive interval. Default is '20s'.

    Returns:
    - bool: True if the configuration is successful, False otherwise.
    """

    try:
        # Set up the SSH client and connect to the MikroTik switch
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Automatically add the host key

        logger.info(f"Connecting to MikroTik switch at {host}...")
        ssh_client.connect(hostname=host, username=username, port=port)

        # Build the WireGuard configuration command
        wireguard_command = (
            f'/interface wireguard peers add interface={interface} '
            f'public-key="{public_key}" allowed-address={ip_address}/32 '
            f'persistent-keepalive={keepalive} comment="{vpnuser}"'
        )

        logger.info(f"Executing command on MikroTik: {wireguard_command}")

        # Execute the command
        stdin, stdout, stderr = ssh_client.exec_command(wireguard_command)

        # Read output and error from the command execution
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        # Check for errors
        if error:
            logger.error(f"Error while configuring WireGuard on MikroTik: {error}")
            return False

        # Log successful configuration
        if output == "":
            logger.info(f"WireGuard VPN user '{vpnuser}' added successfully.")
        else:
            logger.info(f"WireGuard VPN user '{vpnuser}' added successfully, command output: {output}")
        
        return True

    except paramiko.SSHException as e:
        logger.error(f"SSH connection error: {e}")
        return False

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return False

    finally:
        # Close the SSH connection
        ssh_client.close()

def add_user(
    user_name,
    cert_file,
    client,
    remote_name=None,
    admin=False,
    wireguard=False,
    set_vpn=False,
    project=None,
    email=None,
    name=None,
    org=None,
    keys=False,
):
    """
    Add a user to Incus with a certificate and optionally generate an additional SSH key pair.

    Args:
    - user_name (str): The username associated with the certificate.
    - cert_file (str): The certificate file (in .crt format) or None if generating a new key pair.
    - client (object): Client instance for interacting with Incus.
    - remote_name (str, optional): Name of the remote node where the user is added.
    - admin (bool, optional): Specifies if the user has admin privileges.
    - wireguard (bool, optional): Specifies if WireGuard config for the user has to be generated.
    - set_vpn (bool, optional): Specifies if the user has to be added to the wireguard access node 
      (e.g. the MikroTik switch).
    - project (str, optional): Name of the project to restrict the certificate to.
      if not provided, a project will be created with the name 'figo-<user_name>'.
    - email (str, optional): Email address of the user.
    - name (str, optional): Name of the user.
    - org (str, optional): Organization of the user.
    - keys (bool, optional): If True, generate an additional Ed25519 SSH key pair for the user.

    Returns:
    True if the user is added successfully, False otherwise.
    """

    # Check if user already exists in the certificates
    for cert in client.certificates.all():
        if cert.name == user_name:
            logger.error(f"Error: User '{user_name}' already exists.")
            return False

    # Initialize the project name
    project_name = project if project else f"{PROJECT_PREFIX}{user_name}"

    set_of_errored_remotes = set()
    if not project:
        # Retrieve the list of remote servers and check project existence on each
        remotes = get_incus_remotes()
        for remote_node in remotes:
            if remotes[remote_node]["Protocol"] == "simplestreams":
                continue

            projects = get_projects(remote_name=remote_node)
            if projects is None:
                set_of_errored_remotes.add(remote_node)
                continue

            else:  # projects is not None:
                if project_name in [myproject["name"] for myproject in projects]:
                    logger.error(
                        f"Error: Project '{project_name}' already exists on remote '{remote_node}'."
                    )
                    return False
    else:
        # Check if the provided project exists on the local server
        projects = get_projects(remote_name="local")
        if projects is None:
            logger.error(f"Error: Failed to retrieve projects from the local server.")
            return False

        if projects is not None:  # Check again after retrieving projects
            if project not in [myproject["name"] for myproject in projects]:
                logger.error(f"Error: Project '{project}' not found on the local server.")
                return False

    if set_of_errored_remotes:
        logger.warning(
            f"Failed to retrieve projects from the following remote nodes: {', '.join(set_of_errored_remotes)}"
        )

    directory = os.path.expanduser(USER_DIR)
    # Ensure the directory exists
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Determine whether to use the provided certificate or generate a new key pair
    if cert_file:
        # If a certificate file is provided, use it
        # the certificate file is in the folder USER_DIR
        # the certificate file should be named as user_name.crt
        # get the certificate file path
        crt_file = os.path.join(directory, cert_file)
        if not os.path.exists(crt_file):
            logger.error(f"Error: Certificate file '{crt_file}' not found.")
            return False
        logger.info(f"Using provided certificate: {crt_file}")

    else:
        # Generate key pair and certificate
        crt_file = os.path.join(directory, f"{user_name}.crt")
        pfx_file = os.path.join(directory, f"{user_name}.pfx")
        key_file = os.path.join(directory, f"{user_name}.key")
        if not generate_key_pair(user_name, crt_file, key_file, pfx_file):
            logger.error(f"Failed to generate key pair and certificate for user: {user_name}")
            return False
        logger.info(f"Generated certificate and key pair for user: {user_name}")

    # Optionally generate additional SSH key pair if `keys` flag is set
    if keys:
        # Generate Ed25519 key pair for SSH login
        ssh_key_file = os.path.join(directory, f"{user_name}.key_ssh_ed25519")
        if not generate_ssh_key_pair(user_name, ssh_key_file):
            logger.error(f"Failed to generate SSH key pair for user: {user_name}")
            return False

    # Create a project for the user in the main server (local)
    project_created = False
    if not admin and project == None:
        if remote_name == None:
            logger.error(f"Error: Client name not provided.")
            return False
        project_created = create_project(remote_name, project_name)

    if not project_created:
        logger.error(f"Error: Failed to create project '{project_name}', no certificate added.")
        return False

    # Add the user certificate to Incus
    certificate_added = add_certificate_to_incus(
        client, user_name, crt_file, project_name, admin=admin, email=email, name=name, org=org
    )

    if not admin and project == None and not certificate_added:
        delete_project("local", project_name)
        return False

    if wireguard:
        wg_public_key, wg_ip_address = generate_wireguard_config(user_name)
        if not wg_public_key:
            logger.error("Failed to generate WireGuard configuration.")
            return False
    
    if set_vpn:
        if not wireguard:
            logger.error("Error: Cannot set VPN without generating WireGuard configuration.")
            return False
        
        if not add_wireguard_vpn_user_on_mikrotik(
            wg_public_key, wg_ip_address, user_name
        ):
            logger.error(f"Failed to add user to WireGuard VPN on MikroTik.")
            return False
    
    return True

def grant_user_access(username, projectname, client):
    try:
        # Step 1: Retrieve the certificate by username
        certificates = client.certificates.all()
        user_cert = None
        for cert in certificates:
            if cert.name == username:
                user_cert = cert
                break
        
        if not user_cert:
            logger.error(f"User '{username}' not found.")
            return

        # Step 3: Fetch the user's configuration
        try:
            # Assuming the 'projects' attribute exists on 'user_cert'
            projects = user_cert.projects or []  # Get current projects or initialize an empty list
            
            # Step 4: Modify the user's configuration to add the project
            if projectname not in projects:
                projects.append(projectname)
                user_cert.projects = projects

                # Step 5: Save the updated user configuration
                user_cert.save()  # Save the updated configuration
                logger.info(f"User '{username}' has been granted access to project '{projectname}'.")
            else:
                logger.info(f"User '{username}' already has access to project '{projectname}'.")
        except Exception as e:
            logger.error(f"Error updating user configuration: {e}")
            return

    except Exception as e:
        logger.error(f"Error retrieving certificate for user '{username}': {e}")

def edit_user(username, client, email=None, name=None, org=None):
    """
    Edit user's certificate description in Incus.

    Args:
    - username (str): The username associated with the certificate.
    - client (object): Client instance for interacting with Incus.
    - email (str, optional): The new email address for the user.
    - name (str, optional): The new full name for the user.
    - org (str, optional): The new organization for the user.

    Returns:
    - bool: True if the edit was successful, False otherwise.
    """

    # Update the description using the edit_certificate_description function
    if not edit_certificate_description(client, username, email, name, org):
        logger.error(f"Failed to update description for user '{username}'.")
        return False

    logger.info(f"Updated description for user '{username}' successfully.")
    return True

def get_certificate_path(remote_node):
    """
    Retrieve the path to the self-signed certificate for the specified remote node.
    """
    return os.path.join(CERTIFICATE_DIR, f"{remote_node}.crt")

def get_remote_address(remote_node, get_protocol=False):
    """Retrieve the address of the remote node."""

    remotes = get_incus_remotes()
    remote_info = remotes.get(remote_node, None)
    if remote_info and "Addr" in remote_info:
        if get_protocol:
            if "Protocol" in remote_info:
                return remote_info["Addr"], remote_info["Protocol"]
            else:
                raise ValueError(f"Error: Protocol not found for remote node '{remote_node}'") 
        else:
            return remote_info["Addr"]
    else:
        raise ValueError(f"Error: Address not found for remote node '{remote_node}'")

def list_instances_in_project(remote_node, project_name):
    """List instances associated with a project on a specific remote node.
    
    Returns a list of instance names in the project or None if an error occurs.
    """
    
    remote_client = get_remote_client(remote_node, project_name=project_name)
    if not remote_client:
        logger.error(f"Failed to retrieve client for remote '{remote_node}', project_name '{project_name}'.")
        return None

    # List all instances in the remote node in the given project
    instances = remote_client.instances.all()

    # Filter instances by the project name
    instances_in_project = [
        instance.name for instance in instances if instance.config.get("volatile.project") == project_name
    ]
    return instances_in_project

def list_profiles_in_project(remote_node, project_name):
    """List profiles associated with a project on a specific remote node.
    
    Returns a list of profile names in the project or None if an error occurs.
    """

    remote_client = get_remote_client(remote_node, project_name=project_name)
    if not remote_client:
        logger.error(f"Failed to retrieve client for remote '{remote_node}', project_name '{project_name}'.")
        return None

    profiles_in_project = []

    # Retrieve all profiles on the remote node
    profiles = remote_client.profiles.all()

    for profile in profiles:
        # Check if the profile is associated with the project
        if profile.config.get("volatile.project") == project_name:
            profiles_in_project.append(profile.name)

    return profiles_in_project

def list_storage_volumes_in_project(remote_node, project_name):
    """List storage volumes associated with a project on a specific remote node.
    
    Returns a list of storage volume names in the project or None if an error occurs.
    """

    remote_client = get_remote_client(remote_node, project_name=project_name)
    if not remote_client:
        logger.error(f"Failed to retrieve client for remote '{remote_node}', project_name '{project_name}'.")
        return None

    storage_volumes_in_project = []

    # Iterate over all storage pools on the remote client
    for pool in remote_client.storage_pools.all():
        try:
            # Retrieve all volumes in the storage pool
            volumes = pool.volumes.all()
        except pylxd.exceptions.NotFound:
            # Handle the case where no volumes are found in the pool
            logger.error(f"No volumes found in storage pool '{pool.name}'.")
            continue

        # Filter volumes by project name in their configuration
        for volume in volumes:
            if volume.config.get("volatile.project") == project_name:
                storage_volumes_in_project.append(volume.name)

    return storage_volumes_in_project

def delete_user(user_name, client, purge=False, removefiles=False):
    """
    Delete a user from the system.

    Parameters:
    - username: Username of the user to delete
    - client: pylxd.Client instance
    - purge: If True, delete associated projects even if the user does not exist
    - removefiles: If True, remove files associated with the user in the USER_DIR
    """

    # Construct the project name associated with the user
    project_name = f"{PROJECT_PREFIX}{user_name}"

    # Check if the user exists in the certificates
    cert_exists = False
    for cert in client.certificates.all():
        if cert.name == user_name:
            cert_exists = True
            # Remove the user's certificate
            cert.delete()
            logger.info(f"Certificate for user '{user_name}' has been removed.")
            break

    if not cert_exists:
        if purge:
            logger.info(f"Warning: User '{user_name}' does not exist.")
        else:
            logger.info(f"User '{user_name}' does not exist. No action taken.")
            return

    # Remove the user's files if the flag is set
    if removefiles:
        directory = os.path.expanduser(USER_DIR)
        # Use glob to match all files that start with user_name followed by any extension
        user_files = glob.glob(os.path.join(directory, f"{user_name}.*"))
        
        for file_path in user_files:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"File '{os.path.basename(file_path)}' has been removed.")

    # Retrieve the list of remote servers
    remotes = get_incus_remotes()

    set_of_errored_remotes = set()
    project_found = False
    for remote_node in remotes:
        # Skipping remote node with protocol simplestreams
        if remotes[remote_node]["Protocol"] == "simplestreams":
            continue

        # Check if the project exists on the remote node
        projects = get_projects(remote_name=remote_node)
        if projects is None:
            set_of_errored_remotes.add(remote_node)
            continue
        else: #if projects is not None:
            if project_name in [project['name'] for project in projects]:
                project_found = True

                # Check if there are any instances in the project
                instances = list_instances_in_project(remote_node, project_name)
                # Check if there are any profiles in the project
                profiles = list_profiles_in_project(remote_node, project_name)
                # Check if there are any storage volumes in the project
                #TODO: Implement this function
                storage_volumes = None
                #storage_volumes = list_storage_volumes_in_project(remote_node, project_name)

                # Warn if the project is not empty
                if instances or profiles or storage_volumes:
                    logger.info(f"Warning: Project '{project_name}' on remote '{remote_node}' is not empty.")
                    if instances:
                        logger.info(f"  - Contains {len(instances)} instance(s)")
                    if profiles:
                        logger.info(f"  - Contains {len(profiles)} profile(s)")
                    if storage_volumes:
                        logger.info(f"  - Contains {len(storage_volumes)} storage volume(s)")
                else:
                    # Delete the empty project
                    #TODO
                    delete_project(remote_node, project_name)
                    logger.info(f"Project '{project_name}' on remote '{remote_node}' has been deleted.")

    if set_of_errored_remotes:
        logger.warning(f"Failed to retrieve projects from the following remote nodes: {', '.join(set_of_errored_remotes)}")

    if not project_found:
        logger.error(f"No associated project '{project_name}' found for user '{user_name}' on any remote.")
    else:
        logger.info(f"User '{user_name}' has been deleted successfully.")

#############################################
###### figo remote command functions ########
#############################################

def list_remotes(full=False, extend=False):
    """Lists the available Incus remotes and their addresses."""
    try:
        remotes = get_incus_remotes()
    except RuntimeError as e:
        logger.error(f"Error: {e}")
        return
    except ValueError as e:
        logger.error(f"Error: {e}")
        return
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return

    if full:
        for remote_name, remote_info in remotes.items():
            print(f"REMOTE NAME: {remote_name}")
            for key, value in remote_info.items():
                print(f"  {key}: {value}")
            print("-" * 60)
    else:
        COLS = [('REMOTE NAME', 20), ('ADDRESS', 40)]
        add_header_line_to_output(COLS)
        for remote_name, remote_info in remotes.items():
            add_row_to_output(COLS, [remote_name, remote_info['Addr']])

    flush_output(extend=extend) # Flush the output buffer

def resolve_hostname(hostname):
    """Resolve the hostname to an IP address."""
    try:
        return socket.gethostbyname(hostname)
    except socket.error:
        return None
    

def enroll_remote(remote_server, ip_address_port, cert_filename="~/.config/incus/client.crt",
                  user="ubuntu", loc_name="main", remote_cert_filename="/var/lib/incus/server.crt"):
    """Enroll a remote server by transferring the client certificate of the figo main node 
    and adding it to the remote Incus daemon. It also retrieves the remote server's certificate 
    and stores it locally on the figo main node.

    Parameters:
    - remote_server: The name of the remote server.
    - ip_address_port: The IP address and port of the remote server in the format 'IP:PORT'.
    - cert_filename: The path to the client certificate file in the main figo node.
    - user: The username to use for SSH connection.
    - loc_name: The location name for the client certificate on the remote server.
    - remote_cert_filename: The path to the server certificate on the remote server.

    Returns:
    True if the remote server was successfully enrolled, False otherwise.
    """
    #TODO enroll_remote has several hardcoded paths that should be replaced with global variables

    # Check if the remote server already exists
    try:
        remotes = get_incus_remotes()
        if remote_server in remotes:
            logger.info(f"Warning: Remote server {remote_server} is already configured.")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"An error occurred while checking configured remotes: {e}")
        return False

    ip_address, port = (ip_address_port.split(":") + ["8443"])[:2]

    if not is_valid_ip(ip_address):
        resolved_ip = resolve_hostname(ip_address)
        if resolved_ip:
            ip_address = resolved_ip
        else:
            logger.error(f"Invalid IP address or hostname: {ip_address}")
            return False

    cert_filename = os.path.expanduser(cert_filename)
    local_cert_path = os.path.join(CERTIFICATE_DIR, f"{remote_server}.crt")
    remote_cert_path = f"{user}@{ip_address}:~/figo/certs/{loc_name}.crt"

    try:
        # Ensure the local certificate directory exists
        os.makedirs(CERTIFICATE_DIR, exist_ok=True)

        # Copy the server certificate from the remote server to the local main node
        scp_command = f"scp {user}@{ip_address}:{remote_cert_filename} {local_cert_path}"
        subprocess.run(scp_command, shell=True, check=True, capture_output=True, text=True)
        logger.info(f"Remote server certificate {remote_cert_filename} copied to {local_cert_path}.")

        # Check if the client certificate already exists on the remote server
        check_cmd = f"ssh {user}@{ip_address} '[ -f ~/figo/certs/{loc_name}.crt ]'"
        result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info(f"Warning: Certificate {loc_name}.crt already exists on {ip_address}.")
        else:
            try:
                # Ensure the destination directory exists on the remote server
                subprocess.run(
                    ["ssh", f"{user}@{ip_address}", "mkdir -p ~/figo/certs"],
                    check=True, capture_output=True, text=True
                )
                logger.info(f"Directory ~/figo/certs ensured on {ip_address}.")
            except subprocess.CalledProcessError as e:
                logger.error(f"An error occurred while creating the directory on {ip_address}: {e}")
                return False

            try:
                # Transfer the client certificate to the remote server
                subprocess.run(
                    ["scp", cert_filename, remote_cert_path],
                    check=True, capture_output=True, text=True
                )
                logger.info(f"Client certificate {cert_filename} successfully transferred to {ip_address} as {loc_name}.crt.")
            except subprocess.CalledProcessError as e:
                logger.error(f"An error occurred while transferring the certificate to {ip_address}: {e}")
                return False

            # Add the client certificate to the Incus daemon on the remote server
            try:
                add_cert_cmd = (
                    f"incus config trust add-certificate --name incus_{loc_name} ~/figo/certs/{loc_name}.crt"
                )
                subprocess.run(
                    ["ssh", f"{user}@{ip_address}", add_cert_cmd],
                    check=True, capture_output=True, text=True
                )
                logger.info(f"Client certificate incus_{loc_name}.crt added to Incus on {ip_address}.")
            except subprocess.CalledProcessError as e:
                if "already exists" in str(e):
                    logger.info(f"Warning: Certificate incus_{loc_name} already added to Incus on {ip_address}.")
                else:
                    logger.error(f"An error occurred while adding the certificate to Incus: {e}")
                    return False

    except subprocess.CalledProcessError as e:
        logger.error(f"An error occurred while copying or processing the certificate: {e}")
        return False

    try:
        # (Already checked that the remote server does not exist)
        # Add the remote server to the client configuration
        subprocess.run(
            ["incus", "remote", "add", remote_server, f"https://{ip_address}:{port}", "--accept-certificate"],
            check=True
        )
        logger.info(f"Remote server {remote_server} added to client configuration.")
    except subprocess.CalledProcessError as e:
        logger.error(f"An error occurred while adding the remote server to the client configuration: {e}")
        return False
    
    return True

def delete_remote(remote_server):
    """Delete a remote server from the client configuration."""
    try:
        # Check if the remote server exists
        remotes = get_incus_remotes()
        if remote_server not in remotes:
            logger.info(f"Remote server {remote_server} not found.")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"An error occurred while deleting the remote server from the client configuration: {e}")
        return False

    try:
        # Delete the remote server from the client configuration
        subprocess.run(
            ["incus", "remote", "remove", remote_server],
            check=True
        )
        logger.info(f"Remote server {remote_server} deleted from client configuration.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"An error occurred while deleting the remote server from the client configuration: {e}")
        return False

#############################################
###### figo project command functions #######
#############################################

def list_projects(remote_name, project, extend=False):
    """List projects on the specified remote and project scope."""

    COLS = [('PROJECT',20), ('REMOTE',25)]
    add_header_line_to_output(COLS)

    if remote_name is None:
        # List all projects on all remotes
        remotes = get_incus_remotes()
        for my_remote_name in remotes:
            # Skip remote nodes with protocol simplestreams
            if remotes[my_remote_name]["Protocol"] == "simplestreams":
                continue
            projects = get_projects(my_remote_name)
            if projects is not None:
                for my_project in projects:
                    if project:
                        if project not in my_project['name']:
                            continue
                    add_row_to_output(COLS, [my_project['name'], my_remote_name])

            else:
                logger.error("  Error: Failed to retrieve projects.")
    else:
        # List projects on the specified remote
        projects = get_projects(remote_name)
        if projects is not None:
            for my_project in projects:
                if project:
                    if project not in my_project['name']:
                        continue
                add_row_to_output(COLS, [my_project['name'], remote_name])
        else:
            logger.error(f"Error: Failed to retrieve projects on remote '{remote_name}'")

    flush_output(extend=extend) # Flush the output buffer

#############################################
###### figo vpn command functions ###########
############################################# 

def get_host_from_target(target):
    """
    Retrieve host, user, and port for a given target from the global TARGETS dictionary.

    Args:
    - target (str): The target identifier to resolve the SSH connection details.

    Returns:
    - tuple: (host, user, port) for the resolved target.
    - Raises ValueError if the target is not found.
    """
    if target in ACCESS_ROUTER_TARGETS:
        return ACCESS_ROUTER_TARGETS[target]
    else:
        logger.error(f"Error: Target '{target}' not found in the global dictionary.")
        raise ValueError("Invalid target")

def add_route_on_mikrotik(dst_address, gateway, username=SSH_MIKROTIK_USER_NAME, 
                          host=SSH_MIKROTIK_HOST, port=SSH_MIKROTIK_PORT):
    """
    Adds a route on a vpn access node (by default the MikroTik switch) to a specific destination address.

    Args:
    - dst_address (str): The destination address in CIDR format (e.g., '10.202.128.0/24').
    - gateway (str): The gateway address for the route (e.g., '10.202.9.2').
    - dev (str): The interface (e.g., 'vlan403') to use for the route.
    - username (str, optional): The SSH username to connect to the MikroTik switch. Default is 'admin'.
    - host (str, optional): The IP address or hostname of the MikroTik switch. Default is '192.168.88.1'.
    - port (int, optional): The SSH port for the MikroTik switch. Default is 22.

    Returns:
    - bool: True if the route is added successfully, False otherwise.
    """

    try:
        # Set up the SSH client and connect to the MikroTik switch
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Automatically add the host key

        logger.info(f"Connecting to MikroTik switch at {host}...")
        ssh_client.connect(hostname=host, username=username, port=port)

        # Build the route add command
        route_command = (
            f'/ip route add dst-address={dst_address} gateway={gateway}'
        )

        logger.info(f"Executing command on MikroTik: {route_command}")

        # Execute the command
        stdin, stdout, stderr = ssh_client.exec_command(route_command)

        # Read output and error from the command execution
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        # Check for errors
        if error:
            logger.error(f"Error while adding route on MikroTik: {error}")
            return False

        # Log successful route addition
        if output == "":
            logger.info(f"Route to '{dst_address}' via '{gateway}' added successfully.")
        else:
            logger.info(f"Route likely not added, command output: {output}")
        
        return True

    except paramiko.SSHException as e:
        logger.error(f"SSH connection error: {e}")
        return False

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return False

    finally:
        # Close the SSH connection
        ssh_client.close()

def add_route_on_linux(dst_address, gateway, dev, username=SSH_LINUX_USER_NAME, 
                       host=SSH_LINUX_HOST, port=SSH_LINUX_PORT):
    """
    Adds a route on a Linux VPN access node using the ip route command.

    Args:
    - dst_address (str): The destination address in CIDR format (e.g., '10.202.128.0/24').
    - gateway (str): The gateway address for the route (e.g., '10.202.9.2').
    - dev (str): The interface (e.g., 'vlan403') to use for the route.
    - username (str, optional): The SSH username to connect to the Linux router. Default is 'ubuntu'.
    - host (str, optional): The IP address or hostname of the Linux router. Default is 'localhost'.
    - port (int, optional): The SSH port for the Linux router. Default is 22.

    Returns:
    - bool: True if the route is added successfully, False otherwise.
    """
    try:
        if host == '':
            logger.error("Error: Hostname or IP address not provided.")
            return False
        
        # Set up the SSH client and connect to the Linux router
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Automatically add the host key

        logger.info(f"Connecting to Linux router at {host}...")
        ssh_client.connect(hostname=host, username=username, port=port)

        # Build the ip route add command
        route_command = (
            f'sudo ip route add {dst_address} via {gateway} dev {dev}'
        )

        logger.info(f"Executing command on Linux: {route_command}")

        # Execute the command
        stdin, stdout, stderr = ssh_client.exec_command(route_command)

        # Read output and error from the command execution
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        # Check for errors
        if error:
            logger.error(f"Error while adding route on Linux: {error}")
            return False

        # Log successful route addition
        if output == "":
            logger.info(f"Route to '{dst_address}' via '{gateway}' on '{dev}' added successfully.")
        else:
            logger.info(f"Route likely not added, command output: {output}")

        return True

    except paramiko.SSHException as e:
        logger.error(f"SSH connection error: {e}")
        return False

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return False

    finally:
        # Close the SSH connection
        ssh_client.close()


def add_route_on_vpn_access(dst_address, gateway, dev, device_type='mikrotik', username=None, 
                          host=None, port=None):
    """
    Adds a route on a vpn access node (by default the MikroTik switch) to a specific destination address.

    Args:
    - dst_address (str): The destination address in CIDR format (e.g., '10.202.128.0/24').
    - gateway (str): The gateway address for the route (e.g., '10.202.9.2').
    - dev (str): The interface (e.g., 'vlan403') to use for the route.
    - username (str, optional): The SSH username to connect to the MikroTik switch. Default is 'admin'.
    - host (str, optional): The IP address or hostname of the MikroTik switch. Default is '192.168.88.1'.
    - port (int, optional): The SSH port for the MikroTik switch. Default is 22.

    Returns:
    - bool: True if the route is added successfully, False otherwise.
    """

    if device_type == 'mikrotik':
        return add_route_on_mikrotik(dst_address, gateway,  
                                     username if username else SSH_MIKROTIK_USER_NAME,
                                     host if host else SSH_MIKROTIK_HOST,
                                     port if port else SSH_MIKROTIK_PORT)
    elif device_type == 'linux':
        return add_route_on_linux(dst_address, gateway, dev,
                                  username if username else SSH_LINUX_USER_NAME,
                                  host if host else SSH_LINUX_HOST,
                                  port if port else SSH_LINUX_PORT)
    else:
        logger.error(f"Unsupported device type: {device_type}")
        return False


#############################################
######### Command Line Interface (CLI) ######
#############################################

#############################################
######### Common helper functions for CLI ###
#############################################

def check_instance_name(instance_name):
    """Check validity of instance name."""
    if instance_name is None:
        return False
    # Instance name can only contain letters, numbers, hyphens, no underscores
    if not re.match(r'^[a-zA-Z0-9-]+$', instance_name):
        logger.error(f"Error: Instance name can only contain letters, numbers, hyphens: '{instance_name}'.")
        return False
    return True

def parse_instance_scope(instance_name, provided_remote, provided_project):
    """Parse the instance name to extract remote, project, and instance.
    
    return remote, project, instance
    """
    remote, project, instance = '', '', instance_name  # Default values

    if ':' in instance_name:
        parts = instance_name.split(':')
        if len(parts) == 2:
            if '.' in parts[1]:
                remote, project_instance = parts
                parts_pro_inst = project_instance.split('.')
                if len(parts_pro_inst) == 2:
                    project, instance = parts_pro_inst
                else:
                    logger.error(f"Syntax error in instance name '{instance_name}'.")
                    return None, None, None
            else:
                remote, instance = parts
        else:
            logger.error(f"Syntax error in instance name '{instance_name}'.")
            return None, None, None
    elif '.' in instance_name:
        parts_pro_inst = instance_name.split('.')
        if len(parts_pro_inst) == 2:
            project, instance = parts_pro_inst
        else:
            logger.error(f"Syntax error in instance name '{instance_name}'.")
            return None, None, None

    if not check_instance_name(instance):
        return None, None, None

    # Resolve conflicts
    if provided_remote and remote != '' and provided_remote != remote:
        logger.error(f"Error: Conflict between scope remote '{remote}' and provided remote '{provided_remote}'.")
        return None, None, None
    if provided_project and project != '' and provided_project != project:
        logger.error(f"Error: Conflict between scope project '{project}' and provided project '{provided_project}'.")
        return None, None, None

    # Use provided flags if there's no conflict and they are provided
    remote = provided_remote if provided_remote else remote
    project = provided_project if provided_project else project

    if remote == '':
        remote = 'local'

    if project == '':
        project = 'default'

    return remote, project, instance


#############################################
###### figo instance command CLI ############
#############################################

def create_instance_parser(subparsers):
    instance_parser = subparsers.add_parser(
        "instance", help="Manage instances", formatter_class=argparse.RawTextHelpFormatter
    )
    instance_subparsers = instance_parser.add_subparsers(dest="instance_command")

    # Add common options for remote, project, user, IP, gateway, and NIC
    def add_common_arguments(parser):
        parser.add_argument("-r", "--remote", help="Specify the remote server name")
        parser.add_argument("-p", "--project", help="Specify the project name")
        parser.add_argument(
            "-u", "--user",
            help="Used to infer the project (for list, start, stop, set_key, set_ip, bash)"
        )
        parser.add_argument("-i", "--ip", help="Specify a static IP address for the instance")
        parser.add_argument(
            "-g", "--gw", help="Specify the gateway address for the instance"
        )
        parser.add_argument(
            "-n", "--nic",
            help="Specify the NIC name for the instance, used in create and set_ip subcommands.\n"
                 "Default: eth0 for containers, enp5s0 for VMs"
        )

    # List command
    instance_list_parser = instance_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List instances in the system, with options to specify scope, remote, and project.",
        description="List instances, optionally specifying a scope, remote server, or project.\n"
                    "The scope can include 'remote:project.', 'project.', or 'remote:'.\n"
                    "Use the -f/--full option to display more detailed information.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo instance list\n"
               "  figo instance list remote:project.\n"
               "  figo instance list project. -r remote_name\n"
               "  figo instance list -f --extend"
    )
    instance_list_parser.add_argument(
        "-f", "--full", action="store_true", help="Show full details of instance profiles"
    )
    instance_list_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit content"
    )
    instance_list_parser.add_argument(
        "scope", nargs="?", help="Scope in the format 'remote:project.', 'project.', or 'remote:' to limit the listing"
    )
    add_common_arguments(instance_list_parser)

    # Start command
    start_parser = instance_subparsers.add_parser(
        "start",
        help="Start a specific instance, with optional remote and project scope.",
        description="Start a specific instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "If the scope is not provided in the instance name, the -r/--remote and -p/--project options can be used.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo instance start instance_name\n"
               "  figo instance start remote:project.instance_name\n"
               "  figo instance start instance_name -r remote_name -p project_name"
    )
    start_parser.add_argument(
        "instance_name",
        help="Name of the instance to start. Can include remote and project scope."
    )
    add_common_arguments(start_parser)

    # Stop command
    stop_parser = instance_subparsers.add_parser(
        "stop",
        help="Stop a specific instance or all instances in a specified scope.",
        description="Stop a specific instance or all instances in a given scope.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "Use the --all option to stop all instances within the specified scope.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo instance stop instance_name\n"
               "  figo instance stop remote:project.instance_name\n"
               "  figo instance stop -a -r remote_name\n"
               "  figo instance stop project. -a"
    )
    stop_parser.add_argument(
        "instance_name", nargs="?", default=None,
        help="Name of the instance to stop. Can include remote and project scope.\n"
             "If '--all' is provided, a specific instance cannot be given.\n"
    )
    stop_parser.add_argument(
        "-a", "--all", action="store_true",
        help=("Stop all instances in the specified scope.\n"
              "If remote or project is not specified, all remotes or all projects are considered.")
    )
    add_common_arguments(stop_parser)

    # Set Key command
    set_key_parser = instance_subparsers.add_parser(
        "set_key",
        help="Set a public key for a user in a specific instance.",
        description="Set a public key for a user in a specific instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "If the scope is not provided in the instance name, the -r/--remote and -p/--project options can be used.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo instance set_key instance_name key_filename\n"
               "  figo instance set_key remote:project.instance_name key_filename\n"
               "  figo instance set_key instance_name key_filename -r remote_name -p project_name"
    )
    set_key_parser.add_argument("instance_name", help="Name of the instance. Can include remote and project scope.")
    set_key_parser.add_argument("key_filename", help="Filename of the public key on the host (by default in the ./users folder)")
    set_key_parser.add_argument("-l", "--login", default=DEFAULT_LOGIN_FOR_INSTANCES, 
                                help="Specify the user login name (default: ubuntu) for which we are setting the key")
    set_key_parser.add_argument("-d", "--dir", default=USER_DIR, 
                                help="Specify the directory path where the key file is located (default: ./users)")
    set_key_parser.add_argument("-f", "--force", action="store_true", 
                                help="Start the instance if not running, then stop after setting the key")
    add_common_arguments(set_key_parser)

    # Set IP command
    set_ip_parser = instance_subparsers.add_parser(
        "set_ip",
        help="Set a static IP address and gateway for a stopped instance.",
        description="Set a static IP address and gateway for a stopped instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo instance set_ip instance_name -i 192.168.1.10/24 -g 192.168.1.1\n"
               "  figo instance set_ip remote:project.instance_name -i 10.0.0.5/24 -g 10.0.0.1"
    )
    set_ip_parser.add_argument("instance_name",
                               help="Name of the instance to set the IP address for. Can include remote and project scope.")
    add_common_arguments(set_ip_parser)

    # Create command
    create_parser = instance_subparsers.add_parser(
        "create",
        aliases=["c"],
        help="Create a new instance, specifying the instance name, image, type, and optional profiles.",
        description="Create a new instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "Specify the image, instance type, optional profiles, and the option to create the project if it does not exist.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance create instance_name image_name\n"
            "  figo instance create remote:project.instance_name image_name -t vm\n"
            "  figo instance create instance_name image_name -r remote_name -p project_name\n"
            "  figo instance create instance_name image_name -f profile1,profile2\n"
            "  figo instance create instance_name image_name -m"
    )
    create_parser.add_argument("instance_name", help="Name of the new instance.\n"
                            "Can include remote and project scope in the format 'remote:project.instance_name'")
    create_parser.add_argument("image", help="Image source to create the instance from. Format: 'remote:image' or 'image'.")
    create_parser.add_argument("-t", "--type", choices=["vm", "container", "cnt"], default="container", 
                            help="Specify the instance type: 'vm', 'container', or 'cnt' (default: 'container').")
    create_parser.add_argument("-f", "--profile", help="Comma-separated list of profiles to apply to the instance.")
    create_parser.add_argument("-m", "--make_project", action="store_true",
                            help="Create the project if it does not exist on the remote specified.")
    add_common_arguments(create_parser)

    # Delete command
    delete_parser = instance_subparsers.add_parser(
        "delete",
        aliases=["del", "d"],
        help="Delete a specific instance, with optional force deletion.",
        description="Delete a specific instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "Use the -f/--force option to delete the instance even if it is running.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo instance delete instance_name\n"
               "  figo instance delete remote:project.instance_name -f\n"
               "  figo instance delete instance_name -r remote_name -p project_name"
    )
    delete_parser.add_argument("instance_name", help="Name of the instance to delete. Can include remote and project scope.")
    delete_parser.add_argument("-f", "--force", action="store_true", help="Force delete the instance even if it is running")
    add_common_arguments(delete_parser)

    # Bash command
    bash_parser = instance_subparsers.add_parser(
        "bash",
        aliases=["b"],
        help="Execute bash in a specific instance, optionally starting it first.",
        description="Execute bash in a specific instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "Use the -f/--force option to start the instance if it is not running.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo instance bash instance_name\n"
               "  figo instance bash remote:project.instance_name\n"
               "  figo instance bash instance_name -f -r remote_name -p project_name"
    )
    bash_parser.add_argument("instance_name", help="Name of the instance to execute bash. Can include remote and project scope.")
    bash_parser.add_argument("-f", "--force", action="store_true", help="Start the instance if not running and exec bash (stop on exit if not running)")
    bash_parser.add_argument("-t", "--timeout", type=int, default=BASH_CONNECT_TIMEOUT, help="Total timeout in seconds for retries (default: {BASH_CONNECT_TIMEOUT})")
    bash_parser.add_argument("-a", "--attempts", type=int, default=BASH_CONNECT_ATTEMPTS, help="Number of retry attempts to connect (default: {BASH_CONNECT_ATTEMPTS})")
    add_common_arguments(bash_parser)

    # Aliases for the main parser
    subparsers._name_parser_map["in"] = instance_parser
    subparsers._name_parser_map["i"] = instance_parser

    return instance_parser

def handle_instance_list(args):
    """Handle the 'list' command for instances."""
    remote_node = args.remote
    project_name = args.project
    instance_scope = None

    if args.scope:
        if ":" in args.scope: # remote:project.instance or remote:project. or remote:instance or remote:
            remote_scope, project_and_instance_scope = args.scope.split(":", 1)
            if remote_scope == "":
                logger.error(f"Error: Invalid remote scope '{remote_scope}'.")
                return False
            if "." in project_and_instance_scope:
                project_scope, instance_scope = project_and_instance_scope.split(".", 1)
                if project_scope == "":
                    logger.error(f"Error: Invalid project scope '{project_scope}'.")
                    return False
                if instance_scope == "":
                    instance_scope = None
            elif project_and_instance_scope == "":
                project_scope = None
                instance_scope = None
            else:
                instance_scope = project_and_instance_scope
                project_scope = None
            
        elif "." in args.scope: # project.instance or project. 
            remote_scope = None
            project_and_instance_scope = args.scope
            project_scope, instance_scope = project_and_instance_scope.split(".", 1)
            if project_scope == "":
                logger.error(f"Error: Invalid project scope '{project_scope}'.")
                return False
            if instance_scope == "":
                instance_scope = None
        else: # instance
            remote_scope = None
            project_scope = None
            instance_scope = args.scope

        if args.remote and args.remote != remote_scope:
            logger.error(f"Error: Conflict between scope remote '{remote_scope}' and provided remote '{args.remote}'.")
            return False
        if args.project and project_scope and args.project != project_scope:
            logger.error(f"Error: Conflict between scope project '{project_scope}' and provided project '{args.project}'.")
            return

        remote_node = remote_scope
        project_name = project_scope if project_scope else args.project # Use provided project if no project scope
        # project_name can be None if project_scope is None

    # Pass the `extend` flag to list_instances to adjust column width as specified by user
    list_instances(remote_node, project_name=project_name, instance_scope=instance_scope, full=args.full, extend=args.extend)

def handle_instance_command(args, parser_dict):
    if not args.instance_command:
        parser_dict['instance_parser'].print_help()
        return

    def parse_instance_scope_for_all(instance_name, provided_remote, provided_project):
        """Parse the instance name to extract remote, project, and instance for the '--all' option."""
        remote, project, instance = None, None, instance_name  # Default to None

        if ':' in instance_name:
            parts = instance_name.split(':')
            if len(parts) == 2:
                remote = parts[0]
                if '.' in parts[1]:
                    project, instance = parts[1].split('.', 1)
                else:
                    instance = parts[1]
            else:
                logger.error(f"Syntax error in instance name '{instance_name}'.")
                return None, None, None
        elif '.' in instance_name:
            project, instance = instance_name.split('.', 1)
        else:
            instance = instance_name

        # Handle special cases with trailing ':' or '.' for the --all option
        if args.all:
            # If '--all' is used, treat trailing '.' or ':' as project or remote scopes.
            if instance_name.endswith(':'):
                remote = instance_name[:-1]
                project = None
                instance = None
            elif instance_name.endswith('.'):
                project = instance_name[:-1]
                remote = provided_remote or None
                instance = None

        # Validate instance name if it's provided and '--all' isn't used
        if not args.all and not check_instance_name(instance):
            logger.error(f"Error: Instance name can only contain letters, numbers, hyphens: '{instance}'.")
            return None, None, None

        # Resolve conflicts between provided flags and parsed values
        if provided_remote and remote and provided_remote != remote:
            logger.error(f"Error: Conflict between scope remote '{remote}' and provided remote '{provided_remote}'.")
            return None, None, None
        if provided_project and project and provided_project != project:
            logger.error(f"Error: Conflict between scope project '{project}' and provided project '{provided_project}'.")
            return None, None, None

        # Use provided flags if there's no conflict and they are provided
        remote = provided_remote if provided_remote else remote
        project = provided_project if provided_project else project

        return remote, project, instance

    def parse_image(image_name):
        if ':' in image_name:
            parts = image_name.split(':')
            if len(parts) == 2:
                return image_name
            else:
                logger.error(f"Syntax error in image name '{image_name}'.")
                return None
        else:
            return f"images:{image_name}"

    # Validate the IP address and prefix length
    if args.ip and not is_valid_ip_prefix_len(args.ip):
        logger.error(f"Error: Invalid IP address or prefix length '{args.ip}'.")
        return

    # Validate the gateway address if provided
    if args.gw and not is_valid_ip(args.gw):
        logger.error(f"Error: Invalid gateway address '{args.gw}'.")
        return

    if args.instance_command in ["list", "l"]:
        handle_instance_list(args)
    else:
        # Handle project based on user if provided
        user_project = None
        if 'user' in args and args.user:
            user_project = derive_project_from_user(args.user)

        # If user_project is set, check for conflicts
        if user_project:
            if args.project and user_project != args.project:
                logger.error(f"Error: Conflict between derived project '{user_project}' from user '{args.user}'"
                             f" and provided project '{args.project}'.")
                return
            else:
                args.project = user_project  # Use the derived project

        if args.instance_command == "stop":
            if args.all:
                # Parse instance scope if provided with '--all'
                remote, project, instance = parse_instance_scope_for_all(args.instance_name or '', args.remote, args.project)

                # Ensure '--all' is not used with a specific instance
                if instance:
                    logger.error("Error: '--all' cannot be used with a specific instance name.")
                    return

                # Handle None values for remote and project appropriately
                remote_str = remote if remote else "all remotes"
                project_str = project if project else "all projects"

                logger.info(f"Stopping all instances in {remote_str} and {project_str}...")
                stop_all_instances(remote, project)
            else:
                # Stop a specific instance
                remote, project, instance = parse_instance_scope(args.instance_name, args.remote, args.project)
                
                # Check if instance is valid; `remote` and `project` should not be `None` in this context
                if remote is None or project is None or instance is None:
                    logger.error("Error: A valid remote and project are required when stopping a specific instance.")
                    return

                # Proceed to stop the specified instance
                stop_instance(instance, remote, project)
        else:
            remote, project, instance = parse_instance_scope(args.instance_name, args.remote, args.project)
            if remote is None or project is None:
                return  # Error already printed by parse_instance_scope

            if args.instance_command == "start":
                start_instance(instance, remote, project)

            elif args.instance_command == "set_key":
                # Extract the parameters with defaults applied
                login = args.login
                folder = args.dir
                force = args.force
                set_user_key(instance, remote, project, args.key_filename, login=login, folder=folder, force=force)
            elif args.instance_command == "set_ip":
                set_ip(instance, remote, project, 
                    ip_address_and_prefix_len=args.ip, gw_address=args.gw, nic_device_name=args.nic)
            elif args.instance_command in ["create", "c"]:
                image = parse_image(args.image)
                if image is None:
                    return  # Error already printed by parse_image

                # Determine instance type
                instance_type = args.type
                if instance_type == "cnt":
                    instance_type = "container"  # Convert 'cnt' to 'container'

                profiles = [p for p in args.profile.split(',') if p.strip()] if args.profile else []

                # Pass the --make_project option as create_project to create_instance
                create_instance(instance, image, remote, project, instance_type,
                                ip_address_and_prefix_len=args.ip, gw_address=args.gw, nic_device_name=args.nic,
                                profiles=profiles, create_project_flag=args.make_project)
            elif args.instance_command in ["delete", "del", "d"]:
                delete_instance(instance, remote, project, force=args.force)
            elif args.instance_command in ["bash", "b"]:
                exec_instance_bash(instance, remote, project, force=args.force, timeout=args.timeout, max_attempts=args.attempts)
            else:
                logger.error(f"Unknown instance subcommand: {args.instance_command}")

#############################################
###### figo gpu command CLI #################
#############################################

def create_gpu_parser(subparsers):
    gpu_parser = subparsers.add_parser("gpu", help="Manage GPUs")
    gpu_subparsers = gpu_parser.add_subparsers(dest="gpu_command")

    # GPU Status with extended column option
    status_gpu_parser = gpu_subparsers.add_parser(
        "status",
        help="Show the current status of GPUs, including their availability and usage.",
        description="Show the status of GPUs in the system, displaying their availability and usage.\n"
                    "Use the -e/--extend option to adjust column width for better readability.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo gpu status\n"
               "  figo gpu status --extend"
    )
    status_gpu_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit the content"
    )

    # List GPU profiles
    list_gpu_parser = gpu_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List GPU profiles configured in the system.",
        description="List all GPU profiles configured in the system.\n"
                    "Use the -e/--extend option to adjust column width for better readability.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo gpu list\n"
               "  figo gpu list --extend"
    )
    list_gpu_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit the content"
    )

    # Add GPU profile command with enhanced help and documentation
    add_gpu_parser = gpu_subparsers.add_parser(
        "add",
        help="Add a GPU profile to a specific instance, with optional remote and project scope.",
        description="Add a GPU profile to a specific instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "If the scope is not provided in the instance name, the -r/--remote and -p/--project options can be used.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo gpu add my_instance\n"
               "  figo gpu add my_project.instance_name -r my_remote\n"
               "  figo gpu add my_remote:my_project.instance_name\n"
               "  figo gpu add instance_name -p my_project -r my_remote\n"
               "  figo gpu add my_instance -u user_name"
    )
    add_gpu_parser.add_argument(
        "instance_name", 
        help="Name of the instance to add a GPU profile to. Can include remote and project scope."
    )
    add_gpu_parser.add_argument(
        "-p", "--project", 
        help="Specify the project name for the instance."
    )
    add_gpu_parser.add_argument(
        "-r", "--remote", 
        help="Specify the remote Incus server name."
    )
    add_gpu_parser.add_argument(
        "-u", "--user", 
        help="Specify the user to infer the project from."
    )

    # Remove GPU profiles command with enhanced help and support for scoped instance_name
    remove_gpu_parser = gpu_subparsers.add_parser(
        "remove",
        help="Remove GPU profiles from a specific instance, with optional remote and project scope.",
        description="Remove GPU profiles from a specified instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "If the scope is not provided in the instance name, the -r/--remote and -p/--project options can be used.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo gpu remove my_instance\n"
               "  figo gpu remove my_project.instance_name --all\n"
               "  figo gpu remove my_remote:my_project.instance_name\n"
               "  figo gpu remove instance_name -p my_project -r my_remote\n"
               "  figo gpu remove my_instance -u user_name"
    )
    remove_gpu_parser.add_argument(
        "instance_name", 
        help="Name of the instance to remove a GPU profile from. Can include remote and project scope."
    )
    remove_gpu_parser.add_argument(
        "-p", "--project", 
        help="Specify the project name for the instance."
    )
    remove_gpu_parser.add_argument(
        "-r", "--remote", 
        help="Specify the remote Incus server name."
    )
    remove_gpu_parser.add_argument(
        "-u", "--user", 
        help="Specify the user to infer the project from."
    )
    remove_gpu_parser.add_argument(
        "--all", action="store_true", help="Remove all GPU profiles from the instance."
    )

    # Aliases for main parser
    subparsers._name_parser_map["gp"] = gpu_parser
    subparsers._name_parser_map["g"] = gpu_parser

    return gpu_parser


def handle_gpu_command(args, client, parser_dict):
    if not args.gpu_command:
        parser_dict['gpu_parser'].print_help()
    elif args.gpu_command == "status":
        # Pass the extend argument to adjust column width
        show_gpu_status(client, extend=args.extend)
    elif args.gpu_command in ["list", "l"]:
        # Pass the extend argument to adjust column width
        list_gpu_profiles(client, extend=args.extend)

    else:
        # Handle project based on user if provided
        user_project = None
        if 'user' in args and args.user:
            user_project = derive_project_from_user(args.user)

        # If user_project is set, check for conflicts
        if user_project:
            if args.project and user_project != args.project:
                logger.error(f"Error: Conflict between derived project '{user_project}' from user '{args.user}'"
                             f" and provided project '{args.project}'.")
                return
            else:
                args.project = user_project  # Use the derived project

        if args.gpu_command == "add":
            # Parse the instance scope and validate
            remote, project, instance = parse_instance_scope(
                args.instance_name, provided_remote=args.remote, provided_project=args.project
            )
            if remote is None or project is None or instance is None:
                logger.error("Error: Invalid instance name.")
                return  # Error already printed in parse_instance_scope

            # Proceed with adding the GPU profile
            add_gpu_profile(instance, client, remote=remote, project=project)
        elif args.gpu_command == "remove":
            # Parse the instance scope and validate
            remote, project, instance = parse_instance_scope(
                args.instance_name, provided_remote=args.remote, provided_project=args.project
            )
            if remote is None or project is None or instance is None:
                return  # Error already printed in parse_instance_scope

            # Proceed with removing the GPU profile(s)
            if args.all:
                remove_gpu_all_profiles(instance, client, remote=remote, project=project)
            else:
                remove_gpu_profile(instance, client, remote=remote, project=project)


#############################################
###### figo profile command CLI #############
#############################################

def create_profile_parser(subparsers):
    profile_parser = subparsers.add_parser(
        "profile",
        help="Manage profiles",
        description="Manage and manipulate profiles for instances, including listing, copying, deleting, dumping, and displaying profiles.",
        epilog="Use 'figo profile <command> -h' for more detailed help on a specific command.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command")

    # Show command
    show_parser = profile_subparsers.add_parser(
        "show",
        help="Display the details of a profile.",
        description="Display detailed information about a specific profile, including its name, description, config, and devices.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo profile show my_profile\n"
               "  figo profile show remote:project.my_profile"
    )
    show_parser.add_argument(
        "profile_name",
        help="Name of the profile to display. Can include remote and project scope."
    )

    # Profile dump command with options to dump all profiles or a specific profile
    dump_profiles_parser = profile_subparsers.add_parser(
        "dump",
        help="Dump profiles to .yaml files for backup or inspection.",
        description="Dump profile(s) to .yaml files for backup or inspection.\n"
                    "The profile data includes only the name, description, config, and devices.\n"
                    "Note: This currently only works for local profiles and not for remote profiles.\n"
                    "Each dumped profile is saved in the './profiles' directory, with the filename matching the profile name.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo profile dump my_profile  # Dumps the specified profile to 'my_profile.yaml' in the './profiles' directory.\n"
               "  figo profile dump --all       # Dumps all available local profiles to individual .yaml files in the './profiles' directory."
    )
    dump_profiles_parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Dump all profiles to .yaml files in the './profiles' directory."
    )
    dump_profiles_parser.add_argument(
        "profile_name",
        nargs="?",
        help="Name of the profile to dump. If omitted, use the --all option to dump all profiles."
    )

    # List command with extend option
    list_parser = profile_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List profiles and associated instances.",
        description="List profiles and their associated instances.\n"
                    "You can specify a scope to filter by remote, project, or profile.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo profile list\n"
               "  figo profile list remote:project.profile_name\n"
               "  figo profile list -i --extend"
    )
    list_parser.add_argument(
        "scope",
        nargs="?",
        help="Scope in the format 'remote:project.profile_name', 'remote:project', 'project.profile_name', 'profile_name', or defaults to 'local:default'."
    )
    list_parser.add_argument("-i", "--inherited", action="store_true", help="Include inherited profiles in the listing.")
    list_parser.add_argument("-e", "--extend", action="store_true", help="Extend column width to fit the content.")

    # Copy command
    copy_parser = profile_subparsers.add_parser(
        "copy",
        help="Copy a profile to a new profile name or remote/project.",
        description="Copy a profile to a new profile name or remote/project.\n"
                    "If the target profile is not provided, the source profile name will be used.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo profile copy remote:project.profile1 remote:project.profile2\n"
               "  figo profile copy remote:project.profile1 remote:project\n"
               "  figo profile copy profile1 profile2"
    )
    copy_parser.add_argument(
        "source_profile",
        help="Source profile in the format 'remote:project.profile_name' or 'project.profile_name' or 'profile_name'."
    )
    copy_parser.add_argument(
        "target_profile",
        nargs="?",
        help="Target profile in the format 'remote:project.profile_name' or 'project.profile_name' or 'profile_name'."
    )

    # Delete command
    delete_parser = profile_subparsers.add_parser(
        "delete",
        aliases=["del", "d"],
        help="Delete a profile.",
        description="Delete a specific profile.\n"
                    "Provide the profile name along with optional remote and project scopes.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo profile delete remote:project.profile_name\n"
               "  figo profile delete project.profile_name\n"
               "  figo profile delete profile_name"
    )
    delete_parser.add_argument(
        "profile_scope",
        help="Profile scope in the format 'remote:project.profile_name', 'remote:project', 'project.profile_name', or 'profile_name'."
    )

    # Aliases for main parser
    subparsers._name_parser_map["pr"] = profile_parser
    subparsers._name_parser_map["p"] = profile_parser

    return profile_parser

def parse_profile_scope(profile_scope, command='list'):
    """Parse a profile scope string and return remote, project, and profile names.
    
    It is used for profile list and profile copy commands.
    command: list or copy
    
    """
    remote = None
    project = None
    profile = None

    if profile_scope:
        if ':' in profile_scope and '.' in profile_scope:  # remote:project.profile or remote:project.
            remote, rest = profile_scope.split(':', 1)
            project, profile = rest.split('.', 1)
            if remote == '':
                logger.error("Error: Remote name cannot be empty.")
                return None, None, None
            if project == '':
                logger.error("Error: Project name cannot be empty.")
                return None, None, None
            if profile == '':
                profile = None
        elif ':' in profile_scope: # remote:profile or remote:
            remote, profile = profile_scope.split(':', 1)
            if remote == '':
                logger.error("Error: Remote name cannot be empty.")
                return None, None, None
            if profile == '':
                profile = None
        elif '.' in profile_scope: # project.profile or project.
            project, profile = profile_scope.split('.', 1)
            if project == '':
                logger.error("Error: Project name cannot be empty.")
                return None, None, None
            if profile == '':
                profile = None
        else: # profile
            profile = profile_scope

    if command == 'list':
        pass
    if command == 'copy':
        if remote is None:
            remote = "local"
        if project is None:
            project = "default"

    return remote, project, profile

def handle_profile_command(args, parser_dict):
    """
    Handle subcommands for managing profiles, including dump, show, list, copy, and delete.
    """
    if not args.profile_command:
        parser_dict['profile_parser'].print_help()
    elif args.profile_command == "dump":
        # Parse scope to get remote, project, and profile for the dump command
        remote, project, profile = parse_profile_scope(args.profile_name, command='list')

        client = pylxd.Client()
        if args.all:
            dump_profiles(client)
        elif profile:
            dump_profile(client, profile)
        else:
            logger.error("You must provide a profile name or use the --all option.")
    elif args.profile_command == "show":
        # Parse scope to get remote, project, and profile for the show command
        remote, project, profile = parse_profile_scope(args.profile_name, command='list')

        if profile:
            result = show_profile(remote, project, profile)
            if not result:
                logger.error(f"Error in displaying profile '{profile}'.")
        else:
            logger.error("You must provide a valid profile name to display.")
    elif args.profile_command in ["list", "l"]:
        remote, project, profile = parse_profile_scope(args.scope, command='list')
        list_profiles(remote, project, profile_name=profile, inherited=args.inherited, extend=args.extend)
    elif args.profile_command == "copy":
        source_remote, source_project, source_profile = parse_profile_scope(args.source_profile, command='copy')
        target_remote, target_project, target_profile = parse_profile_scope(
            args.target_profile if args.target_profile else source_profile, command='copy'
        )

        if source_profile is None or source_profile == "":
            logger.error("Error: Source profile name cannot be empty.")
            return
        
        if target_profile is None or target_profile == "":
            target_profile = source_profile

        copy_profile(source_remote, source_project, source_profile, target_remote, target_project, target_profile)
    elif args.profile_command in ["delete", "del", "d"]:
        remote, project, profile = parse_profile_scope(args.profile_scope, command='copy')

        if profile is None or profile == "":
            logger.error("Error: Profile name cannot be empty.")
            return

        delete_profile(remote, project, profile)


#############################################
###### figo user command CLI ################
#############################################

class NoCommaCheck(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if ',' in values:
            parser.error(f"The {option_string} argument cannot contain commas.")
        else:
            setattr(namespace, self.dest, values)

class NoUnderscoreCheck(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if '_' in values:
            parser.error(f"The {self.dest} argument cannot contain underscore.")
        else:
            setattr(namespace, self.dest, values)

def create_user_parser(subparsers):
    user_parser = subparsers.add_parser("user", help="Manage users")
    user_subparsers = user_parser.add_subparsers(dest="user_command")

    # List subcommand
    user_list_parser = user_subparsers.add_parser("list", aliases=["l"], help="List installed certificates (use -f or --full for more details)")
    user_list_parser.add_argument("-f", "--full", action="store_true", help="Show full details of installed certificates")
    user_list_parser.add_argument("-e", "--extend", action="store_true", help="Extend column width to fit the content")

    # Add subcommand
    user_add_parser = user_subparsers.add_parser("add", aliases=["a"], help="Add a new user to the system")
    user_add_parser.add_argument("username", action=NoUnderscoreCheck, help="Username of the new user")
    user_add_parser.add_argument("-c", "--cert", help="Path to the user's certificate file (optional, "
                                "if not provided a new key pair will be generated)")  
    user_add_parser.add_argument("-a", "--admin", action="store_true", help="Add user with admin privileges (unrestricted)")
    user_add_parser.add_argument("-w", "--wireguard", action="store_true", help="Generate WireGuard config for the user in .conf file") 
    user_add_parser.add_argument("-s", "--set_vpn", action="store_true", help="Set the user's VPN profile into the WireGuard access node") 
    user_add_parser.add_argument("-p", "--project", help="Project name to associate the user with an existing project")
    user_add_parser.add_argument("-e", "--email", action=NoCommaCheck, help="User's email address")
    user_add_parser.add_argument("-n", "--name", action=NoCommaCheck, help="User's full name")
    user_add_parser.add_argument("-o", "--org", action=NoCommaCheck, help="User's organization")
    user_add_parser.add_argument("-k", "--keys", action="store_true", help="Generate a key pair for SSH access to instances")

    # Grant subcommand
    user_grant_parser = user_subparsers.add_parser("grant", help="Grant a user access to a specific project")
    user_grant_parser.add_argument("username", help="Username to grant access")
    user_grant_parser.add_argument("projectname", help="Project name to grant access to")

    # Edit subcommand
    user_edit_parser = user_subparsers.add_parser("edit", help="Edit an existing user's details")
    user_edit_parser.add_argument("username", action=NoUnderscoreCheck, help="Username to edit")
    user_edit_parser.add_argument("-e", "--email", action=NoCommaCheck, help="New email for the user")
    user_edit_parser.add_argument("-n", "--name", action=NoCommaCheck, help="New full name for the user")
    user_edit_parser.add_argument("-o", "--org", action=NoCommaCheck, help="New organization for the user")

    # Delete subcommand
    user_delete_parser = user_subparsers.add_parser("delete", aliases=["del", "d"], help="Delete an existing user from the system")
    user_delete_parser.add_argument("username", help="Username of the user to delete")
    user_delete_parser.add_argument("-p", "--purge", action="store_true", help="Delete associated projects and user files (even if the user does not exist)")
    user_delete_parser.add_argument("-k", "--keepfiles", action="store_true", help="Keep the associated files of the user in the users folder")

    # Link parsers back to the main command
    subparsers._name_parser_map["us"] = user_parser
    subparsers._name_parser_map["u"] = user_parser

    return user_parser

def handle_user_command(args, client, parser_dict, client_name=None):
    if not args.user_command:
        parser_dict['user_parser'].print_help()
    elif args.user_command in ["list", "l"]:
        list_users(client, full=args.full, extend=args.extend)
    elif args.user_command == "add":
        # Pass the 'keys' flag to the add_user function
        add_user(args.username, args.cert, client, remote_name=client_name, admin=args.admin, wireguard=args.wireguard, 
                set_vpn=args.set_vpn, project=args.project, email=args.email, name=args.name,
                org=args.org, keys=args.keys)
    elif args.user_command == "grant":
        grant_user_access(args.username, args.projectname, client)
    elif args.user_command == "edit":
        edit_user(args.username, client, email=args.email, name=args.name, org=args.org)
    elif args.user_command in ["delete", "del", "d"]:
        # Reverse logic: delete files by default unless --keepfiles is used
        removefiles = not args.keepfiles
        delete_user(args.username, client, purge=args.purge, removefiles=removefiles)

#############################################
###### figo remote command CLI ##############
#############################################

def create_remote_parser(subparsers):
    remote_parser = subparsers.add_parser("remote", help="Manage remotes")
    remote_subparsers = remote_parser.add_subparsers(dest="remote_command")

    # List subcommand with --full and --extend options
    remote_list_parser = remote_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List available remotes, with options to show detailed or extended views.",
        description="List all available remotes in the system.\n"
                    "Use the -f/--full option to display full details.\n"
                    "Use the -e/--extend option to adjust column width for better readability.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo remote list\n"
               "  figo remote list -f\n"
               "  figo remote list --extend"
    )
    remote_list_parser.add_argument("-f", "--full", action="store_true", help="Show full details of available remotes")
    remote_list_parser.add_argument("-e", "--extend", action="store_true", help="Extend column width to fit the content")

    # Enroll subcommand
    remote_enroll_parser = remote_subparsers.add_parser(
        "enroll",
        help="Enroll a remote Incus server.",
        description="Enroll a remote Incus server by specifying its name, IP address, port, and other optional parameters.\n"
                    "The enrolled server can then be used for managing instances and resources.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo remote enroll my_remote 192.168.1.100\n"
               "  figo remote enroll my_remote 192.168.1.100 8443 ubuntu ~/.config/incus/client.crt --loc_name main"
    )
    remote_enroll_parser.add_argument("remote_server", help="Name to assign to the remote server")
    remote_enroll_parser.add_argument("ip_address", help="IP address or domain name of the remote server")
    remote_enroll_parser.add_argument("port", nargs="?", default="8443", help="Port of the remote server (default: 8443)")
    remote_enroll_parser.add_argument("user", nargs="?", default="ubuntu", help="Username for SSH into the remote (default: ubuntu)")
    remote_enroll_parser.add_argument("cert_filename", nargs="?", default="~/.config/incus/client.crt", 
                                      help="Client certificate file to transfer (default: ~/.config/incus/client.crt)")
    remote_enroll_parser.add_argument("remote_cert_filename", nargs="?", default="/var/lib/incus/server.crt",
                                      help="Remote certificate file to transfer locally (default: /var/lib/incus/server.crt)")
    remote_enroll_parser.add_argument("--loc_name", default="main",
                                      help="Name for saving the client certificate on the remote server (default: main)")

    # Delete subcommand with detailed help
    remote_delete_parser = remote_subparsers.add_parser(
        "delete",
        help="Delete a specified remote.",
        description="Delete a specified remote from the system by providing its name.\n"
                    "This action removes the remote configuration from the system.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo remote delete my_remote\n"
               "  figo remote delete test_remote"
    )
    remote_delete_parser.add_argument("remote_name", help="Name of the remote to delete")

    # Link aliases for easier access
    subparsers._name_parser_map["re"] = remote_parser
    subparsers._name_parser_map["r"] = remote_parser

    return remote_parser

def handle_remote_command(args, parser_dict):
    if not args.remote_command:
        parser_dict['remote_parser'].print_help()
    elif args.remote_command in ["list", "l"]:
        list_remotes(full=args.full, extend=args.extend)  # Pass --extend option to list_remotes
    elif args.remote_command == "enroll":
        ip_address_port = f"{args.ip_address}:{args.port}"
        enroll_remote(args.remote_server, ip_address_port, args.cert_filename, user=args.user,
                      loc_name=args.loc_name, remote_cert_filename=args.remote_cert_filename)
    elif args.remote_command == "delete":
        delete_remote(args.remote_name)


#############################################
###### figo project command CLI #############
#############################################

def create_project_parser(subparsers):
    project_parser = subparsers.add_parser("project", help="Manage projects")
    project_subparsers = project_parser.add_subparsers(dest="project_command")

    # List projects
    project_list_parser = project_subparsers.add_parser("list", aliases=["l"], help="List available projects")
    project_list_parser.add_argument("scope", nargs="?", help="Scope in the format 'remote:project.', 'remote:', or 'project.'")
    project_list_parser.add_argument("--remote", help="Specify the remote server name")
    project_list_parser.add_argument("--user", help="Specify the user to filter projects")
    project_list_parser.add_argument("-e", "--extend", action="store_true", help="Extend column width to fit the content")

    # Create a project
    project_create_parser = project_subparsers.add_parser("create", aliases=["c"], help="Create a new project")
    project_create_parser.add_argument("scope", help="Scope in the format 'remote:project' or 'remote:'")
    project_create_parser.add_argument("--project", help="Project name if not provided directly in the scope")
    project_create_parser.add_argument("--user", help="Specify the user who will own the project")

    # Delete a project
    project_delete_parser = project_subparsers.add_parser("delete", aliases=["del", "d"], help="Delete an existing project")
    project_delete_parser.add_argument("project_name", help="Name of the project to delete, in the format 'remote:project' or 'project'")

    subparsers._name_parser_map["pr"] = project_parser
    subparsers._name_parser_map["p"] = project_parser

    return project_parser

def parse_project_scope(project_scope, command='list'):
    """Parse a project scope string and return remote and project names.
    
    Used for project list, create, and delete commands.
    """
    remote = None
    project = None

    if project_scope:
        if ':' in project_scope and '.' in project_scope:  # remote:project.
            remote, rest = project_scope.split(':', 1)
            project, token = rest.split('.', 1)
            if remote == '':
                logger.error("Error: Remote name cannot be empty if ':' is used.")
                return None, None
            if project == '':
                logger.error("Error: Project name cannot be empty if ':' and '.' are used.")
                return None, None
            if token != '':
                logger.error("Error: Invalid project scope format.")
                return None, None
        elif ':' in project_scope:  # remote:project or remote:
            remote, project = project_scope.split(':', 1)
            if remote == '':
                logger.error("Error: Remote name cannot be empty.")
                return None, None
            if project == '':
                project = None
        elif '.' in project_scope:  # project.
            project, token = project_scope.split('.', 1)
            if project == '':
                logger.error("Error: Project name cannot be empty.")
                return None, None
            if token != '':
                logger.error("Error: Invalid project scope format.")
                return None, None
        else:  # project
            project = project_scope

    if command == 'list':
        pass  # Keeping this for specific command behaviors in the future

    # Set defaults for create or delete commands
    if command in ['delete', 'create']:
        if remote is None:
            remote = "local"
        if project is None:
            project = "default"

    return remote, project

def handle_project_command(args, parser_dict):
    def adjust_project_scope(args, remote, project):
        if 'user' in args and args.user:
            derived_project = derive_project_from_user(args.user)
            if project and project != derived_project:
                logger.error(f"Error: Conflict between derived project '{derived_project}' from user '{args.user}'"
                             f" and provided project '{project}'.")
                raise ValueError
            project = derived_project

        if 'project' in args and args.project and project is None:
            project = args.project
        if 'project' in args and args.project and project and args.project != project:
            logger.error(f"Error: Conflict between scope project '{project}' and provided project '{args.project}'.")
            raise ValueError
        if 'remote' in args and args.remote and remote is None:
            remote = args.remote
        if 'remote' in args and args.remote and remote and args.remote != remote:
            logger.error(f"Error: Conflict between scope remote '{remote}' and provided remote '{args.remote}'.")
            raise ValueError

        return remote, project

    if not args.project_command:
        parser_dict['project_parser'].print_help()

    elif args.project_command in ["list", "l"]:
        remote_name, project = parse_project_scope(args.scope, command='list')
        try:
            remote_name, project = adjust_project_scope(args, remote_name, project)
        except ValueError:
            return

        list_projects(remote_name, project, extend=args.extend)

    elif args.project_command in ["create", "c"]:
        remote_name, project = parse_project_scope(args.scope, command='create')
        try:
            remote_name, project = adjust_project_scope(args, remote_name, project)
        except ValueError:
            return

        create_project(remote_name, project)

    elif args.project_command in ["delete", "del", "d"]:
        remote_name, project = parse_project_scope(args.project_name, command='delete')
        try:
            remote_name, project = adjust_project_scope(args, remote_name, project)
        except ValueError:
            return

        delete_project(remote_name, project)

#############################################
###### figo vpn command CLI #################
#############################################

def create_vpn_parser(subparsers):
    vpn_parser = subparsers.add_parser("vpn", help="Manage VPN configuration")
    vpn_subparsers = vpn_parser.add_subparsers(dest="vpn_command")

    # Add route subcommand
    vpn_add_parser = vpn_subparsers.add_parser("add", help="Add VPN configuration")
    vpn_add_subparsers = vpn_add_parser.add_subparsers(dest="vpn_add_command")

    # Route subcommand
    route_parser = vpn_add_subparsers.add_parser("route", help="Add a route to VPN")

    # Positional argument for destination
    route_parser.add_argument("dst_address", help="Destination address in CIDR format (e.g., 10.202.128.0/24)")

    # Explicit token 'via' followed by the gateway IP
    route_parser.add_argument("via_token", help="Must be the keyword 'via'", choices=["via"])
    route_parser.add_argument("gateway", help="Gateway address (e.g., 10.202.9.2) without prefix")

    # Optional argument for device interface (for Linux routers, but not required on MikroTik)
    route_parser.add_argument("-d", "--dev", help="Device interface (e.g., vlan403). Required for Linux routers.")

    # Explicit token 'type' followed by the VPN type, generalized using global VPN_DEVICE_TYPES
    route_parser.add_argument("type_token", help="Must be the keyword 'type'", choices=["type"])
    route_parser.add_argument("type", choices=VPN_DEVICE_TYPES, help="Type of the VPN device (e.g., mikrotik, linux)")

    # Explicit tokens for target or host
    group = route_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("target_token", nargs='?', help="Must be the keyword 'target' followed by the target", choices=["target"])
    group.add_argument("host_token", nargs='?', help="Must be the keyword 'host' followed by the host", choices=["host"])

    # Positional argument for either target or host
    route_parser.add_argument("target_or_host", help="Target for VPN or Host to connect to")

    # Optional user and port if host is provided
    route_parser.add_argument("-u", "--user", help=f"SSH username for login into the node (default: {DEFAULT_SSH_USER_FOR_VPN_AR})")
    route_parser.add_argument("-p", "--port", type=int, help=f"SSH port (default: {DEFAULT_SSH_PORT_FOR_VPN_AR})")

    return vpn_parser

def handle_vpn_command(args, parser_dict):
    if not args.vpn_command:
        parser_dict['vpn_parser'].print_help()
    elif args.vpn_command == "add":
        if args.vpn_add_command == "route":
            # Validate the `dst_address` parameter (route) for being a valid CIDR address
            if not is_valid_cidr(args.dst_address):
                logger.error(f"Error: '{args.dst_address}' is not a valid CIDR address.")
                return

            # Validate the `gateway` parameter (via) for being a valid IP address without prefix
            if not is_valid_ip(args.gateway):
                logger.error(f"Error: '{args.gateway}' is not a valid IP address or contains a prefix.")
                return

            # Check if the user provided 'target' or 'host'
            if args.target_token == "target":
                # It's a target, resolve from target mapping
                host, user, port = get_host_from_target(args.target_or_host)
            elif args.host_token == "host":
                # It's a host, resolve user and port
                host = args.target_or_host
                user = args.user if args.user is not None else DEFAULT_SSH_USER_FOR_VPN_AR
                port = args.port if args.port is not None else DEFAULT_SSH_PORT_FOR_VPN_AR
            else:
                logger.error("Error: Either 'target' or 'host' must be provided.")
                return

            # Add the route using the resolved host, user, port, and device type
            add_route_on_vpn_access(
                dst_address=args.dst_address,  # This is validated as a CIDR address
                gateway=args.gateway,          # This is validated as a plain IP address
                dev=args.dev,                  # The device can be None if not provided (MikroTik doesn't need it)
                device_type=args.type,         # Pass the type argument to the generic function
                username=user,
                host=host,
                port=port
            )
        else:
            logger.error("Unknown vpn add command.")

#############################################
###### figo main functions
#############################################

def create_parser():
    parser = argparse.ArgumentParser(
        description="Manage a federated testbed with CPUs and GPUs",
        prog="figo"
    )
    subparsers = parser.add_subparsers(dest="command")

    parser.add_argument("--version", action="version", version="%(prog)s 0.1")  # Set the version of the program

    parser_dict = {}
    parser_dict['instance_parser'] = create_instance_parser(subparsers)
    parser_dict['gpu_parser'] = create_gpu_parser(subparsers)
    parser_dict['profile_parser'] = create_profile_parser(subparsers)
    parser_dict['user_parser'] = create_user_parser(subparsers)
    parser_dict['remote_parser'] = create_remote_parser(subparsers)
    parser_dict['project_parser'] = create_project_parser(subparsers)
    parser_dict['vpn_parser'] = create_vpn_parser(subparsers)

    return parser, parser_dict

def handle_command(args, parser, parser_dict):

    # if --version is provided, print the version and exit
    if hasattr(args, 'version'):
        print(parser.prog, parser.version)  # prints the version of the parser
        return
    
    # Handle the command based on the subparser
    if args.command in ["instance", "in", "i"]:
        handle_instance_command(args, parser_dict)
    elif args.command in ["gpu", "gp", "g"]:
        client = pylxd.Client()
        handle_gpu_command(args, client, parser_dict)
    elif args.command in ["profile", "pr", "p"]:
        handle_profile_command(args, parser_dict)
    elif args.command in ["user", "us", "u"]:
        client = pylxd.Client()
        handle_user_command(args, client, parser_dict, client_name="local")
    elif args.command in ["remote", "re", "r"]:
        handle_remote_command(args, parser_dict)
    elif args.command in ["project"]:
        handle_project_command(args, parser_dict)
    elif args.command in ["vpn"]:
        handle_vpn_command(args, parser_dict)

def main():
    parser, parser_dict = create_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
    else:
        handle_command(args, parser, parser_dict)   

if __name__ == "__main__":
    main()