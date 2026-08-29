# # PYTHON_ARGCOMPLETE_OK
#!/home/gpuserver/figo/venv/bin/python

import argparse
import zipfile
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
import shlex
import collections

# Configuration for the WireGuard VPN server
# The following configuration is used to set up a WireGuard VPN server on a MikroTik router.
SSH_MIKROTIK_USER_NAME = "admin"  # Default SSH username
SSH_MIKROTIK_HOST = "160.80.105.2"  # Default MikroTik IP or host
#SSH_WG_HOST = "mikrotik.netgroup.uniroma2.it"  # Default MikroTik IP or host
SSH_MIKROTIK_PORT = 22  # Default SSH port
WG_INTERFACE = "wireguard2"  # Default WireGuard interface
WG_VPN_KEEPALIVE = "20s"  # Default persistent keepalive interval
WG_SERVER_PUB_KEY = "rdM5suGD/hTHdStf/K1SVc4rviUcUQbKnARnw0AAwT8="  # Default public key of the WireGuard server

SSH_LINUX_USER_NAME = "ubuntu"  # Default SSH username for remote Linux hosts
SSH_LINUX_HOST = ""  # Default Linux IP or host
SSH_LINUX_PORT = 22  # Default SSH port

# Define the SSH key file suffix
SSH_KEY_FILE_SUFFIX = "key_ssh_ed25519"  # Default SSH key file suffix
SSHFS_KEY_FILE_SUFFIX = "key_sshfs_ed25519"  # SSHFS compatible SSH key file suffix

# Define a global dictionary for target lookups
ACCESS_ROUTER_TARGETS = {
    "mikrotik-rm2": (SSH_MIKROTIK_HOST, SSH_MIKROTIK_USER_NAME, SSH_MIKROTIK_PORT),
    "figo-2gpu": ("160.80.223.203", "ubuntu", 22),
    # Add more targets as needed
}

CONTROLLER_CLIENT_CERT_FILE = "/home/ubuntu/.config/incus/client.crt"  # Controller client certificate file
CONTROLLER_CLIENT_KEY_FILE = "/home/ubuntu/.config/incus/client.key"  # Controller client key file

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
NAME_SERVER_IP_ADDR_2 = "8.8.4.4"

PROFILE_DIR = "./profiles"
USER_DIR = "./users"

# Deployment configuration: the facts about *this* installation, which do not
# belong in the source. The file is optional -- with no file figo behaves
# exactly as it did before it existed -- and 'config.yaml.example' in the
# repository documents its shape. See figo-network-model.md Section 5.2.
CONFIG_FILE = "./config.yaml"

# Directory that contains the remote node certificates
CERTIFICATE_DIR = "./certs"

# Base IP address to start the IP address generation for WireGuard VPN clients
BASE_IP_FOR_WG_VPN = "10.202.1.15"

# Allowed IP addresses for the VPN server
AllowedIPs = "10.192.0.0/10"

# Endpoint of the VPN server
Endpoint = "gpunet-vpn.netgroup.uniroma2.it:13232"

FIGO_PREFIX="figo-"  

# used for setting user identifier in pub key if email is not provided
FIGO_FAKE_DOMAIN = "@figo"

# NB: PROJECT_PREFIX cannot contain underscores
PROJECT_PREFIX = FIGO_PREFIX 

DEFAULT_LOGIN_FOR_INSTANCES = 'ubuntu'

DEFAULT_INSTANCE_SIZE = 'compute-medium'  # profile to be added to default if no profile is specified
#DEFAULT_INSTANCE_SIZE = ''  # if empty, no profile is added to defautl


DEFAULT_PREFIX_LEN = 25 # Default prefix length for IP addresses of instances

DEFAULT_VM_NIC = "enp5s0"  # Default NIC for VM instances
DEFAULT_CNT_NIC = "eth0"  # Default NIC for container instances

# Default list of profiles to transfer if not provided
DEFAULT_PROFILES_TO_TRANSFER = ["compute-large", "compute-medium", "compute-small",
                                "disk-128GB", "disk-64GB",
                                "ssh-deploy"]

# ip addresses to instances are assigned as follows:
# the network is of size /25
# the gateway is .129
# the base ip is .150 for addresses assigned to instances by figo ipam
# the addresses from .130 to .134 are reserved for static assignment outside figo ipam    
# the addresses from .135 to .149 are assigned by DHCP server outside figo ipam
REMOTE_TO_IP_INFO_MAP = {
    "local": {
        "gw": "10.202.8.129",
        "prefix_len": 25,
        "base_ip": "10.202.8.150"
        },
    "eln_cloud": {
        "ssh_user": "ubuntu",
        "ssh_port": 22,
        "ssh_host": "160.80.223.231",
        "gw": "10.202.10.129",
        "prefix_len": 25,
        "base_ip": "10.202.10.150"
        },
    "blade3": {
        "ssh_user": "ubuntu",
        "ssh_port": 22,
        "ssh_host": "160.80.105.53",        
        "gw": "10.202.9.129",
        "prefix_len": 25,
        "base_ip": "10.202.9.150"
        },
    "jeeg":  {
        "ssh_user": "ubuntu",
        "ssh_port": 22,
        "ssh_host": "10.202.8.130",        
        "gw": "10.202.8.129",
        "prefix_len": 25,
        "base_ip": "10.202.8.150"
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
    """Evaluate the width of the columns in the output rows."""
    
    column_widths = [0] * len(header_row[0])
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
    """Print the header row and output rows, clearing the lists afterwards.
    
    If extend is True, adapt the output column width to the content
    """
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
        logger.info("All IP addresses cleared from l2 IP address list.")
        return True
    except Exception as e:
        logger.error(f"Error clearing l2 IP address list: {e}")
        return False

#############################################
###### additional IP addresses          #####
#############################################
# An instance can hold, besides its own address, further addresses of the same subnet:
# addresses used by nested QEMU virtual machines it runs, by containers started inside it,
# or simply extra addresses configured on its own NIC. They are recorded here so that the
# IPAM never hands them out to somebody else. figo records them, it does not configure them.
#
# The state lives in the instance configuration, under ADDITIONAL_IPS_KEY, as a YAML list:
#
#   - ip: 10.202.9.214
#     mac: 52:54:00:ca:09:d6
#     name: gob0
#   - ip: 10.202.9.215
#     name: dev-guest
#
# This is deliberately NOT the same key as 'user.l2_ip_list' used by L1 hosts: that one is an
# index of nested *Incus instances* that exist as objects elsewhere, this one is a primary
# record of addresses about which figo knows nothing else. Both are honoured by the allocator.

ADDITIONAL_IPS_KEY = 'user.figo.additional_ips'

# Prefix used when deriving a MAC address from an IP address (locally administered, QEMU).
DERIVED_MAC_PREFIX = '52:54:00'

def get_additional_ips_from_config(config):
    """Return the additional IP entries found in an instance configuration dictionary.

    Accepts the raw config dict, as provided both by 'incus list -f json' and by a pylxd
    instance object, so that it can be used on the listing path and on the write path alike.

    Returns: a list of dicts with the 'ip' key always present and the 'mac' and 'name' keys
             possibly None. Returns an empty list when the key is absent, empty or unreadable:
             a malformed value must not prevent the rest of figo from working.
    """
    raw = (config or {}).get(ADDITIONAL_IPS_KEY, '')
    if not raw or not str(raw).strip():
        return []

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing '{ADDITIONAL_IPS_KEY}': {e}")
        return []

    if not isinstance(parsed, list):
        logger.error(f"Error: '{ADDITIONAL_IPS_KEY}' does not contain a YAML list.")
        return []

    entries = []
    for item in parsed:
        if isinstance(item, dict) and item.get('ip'):
            entries.append({
                'ip': str(item.get('ip')),
                'mac': str(item.get('mac')) if item.get('mac') else None,
                'name': str(item.get('name')) if item.get('name') else None,
            })
        else:
            logger.error(f"Error: ignoring malformed entry in '{ADDITIONAL_IPS_KEY}': {item}")
    return entries

def get_additional_ip_list(instance_object):
    """Retrieve the additional IP entries of an instance.

    Returns:    A list of entries, or None if there is an error.
    """
    try:
        return get_additional_ips_from_config(instance_object.config)
    except Exception as e:
        logger.error(f"Error retrieving additional IP address list: {e}")
        return None

def _store_additional_ip_list(instance_object, entries):
    """Serialise the entries and save them on the instance object.

    Keys whose value is None are dropped, so that an entry without MAC or label does not
    leave empty fields behind in the stored configuration.
    """
    if entries:
        cleaned = [{k: v for k, v in entry.items() if v is not None} for entry in entries]
        instance_object.config[ADDITIONAL_IPS_KEY] = yaml.safe_dump(
            cleaned, default_flow_style=False, sort_keys=False)
    else:
        # Drop the key altogether rather than leaving an empty value behind, so that an instance
        # that holds no additional address shows no trace of the feature in 'incus config show'.
        instance_object.config.pop(ADDITIONAL_IPS_KEY, None)
    instance_object.save(wait=True)

def add_additional_ip(instance_object, ip_address, mac=None, name=None):
    """Add an IP address to the additional IP address list of the instance.

    The address is added only if it is not already in the list. Checking that it is not in
    use elsewhere in the subnet is the caller's responsibility (see handle_instance_additional_ip),
    because it requires querying the whole remote.

    return: True if the IP address was added, False otherwise.
    """
    try:
        entries = get_additional_ips_from_config(instance_object.config)
        if any(entry['ip'] == ip_address for entry in entries):
            logger.error(f"IP address {ip_address} is already in the additional IP address list.")
            return False

        entries.append({'ip': ip_address, 'mac': mac, 'name': name})
        _store_additional_ip_list(instance_object, entries)
        logger.info(f"IP address {ip_address} added to the additional IP address list.")
        return True
    except Exception as e:
        logger.error(f"Error adding IP address to the additional IP address list: {e}")
        return False

def remove_additional_ip(instance_object, ip_address):
    """Remove an IP address from the additional IP address list of the instance.

    return: True if the IP address was removed, False otherwise.
    """
    try:
        entries = get_additional_ips_from_config(instance_object.config)
        remaining = [entry for entry in entries if entry['ip'] != ip_address]
        if len(remaining) == len(entries):
            logger.error(f"IP address {ip_address} not found in the additional IP address list.")
            return False

        _store_additional_ip_list(instance_object, remaining)
        logger.info(f"IP address {ip_address} removed from the additional IP address list.")
        return True
    except Exception as e:
        logger.error(f"Error removing IP address from the additional IP address list: {e}")
        return False

def clear_additional_ip_list(instance_object):
    """Clear all the IP addresses from the additional IP address list of the instance.

    return: True if the IP addresses were cleared, False otherwise.
    """
    try:
        _store_additional_ip_list(instance_object, [])
        logger.info("All IP addresses cleared from the additional IP address list.")
        return True
    except Exception as e:
        logger.error(f"Error clearing the additional IP address list: {e}")
        return False

def derive_mac_from_ip(ip_address):
    """Derive a deterministic MAC address from an IPv4 address.

    Uses the locally administered prefix '52:54:00' followed by the last three octets of the
    address. Within a single /8 this guarantees uniqueness without keeping a second registry,
    and it lets one read the IP address back from a packet capture.

    Returns: the MAC address as a string, or None if the IP address is not a valid IPv4.
    """
    try:
        address = ipaddress.ip_address(ip_address)
    except ValueError:
        logger.error(f"Error: cannot derive a MAC address from '{ip_address}': not a valid IP address.")
        return None

    if address.version != 4:
        logger.error(f"Error: MAC derivation is only supported for IPv4 addresses, got '{ip_address}'.")
        return None

    return f"{DERIVED_MAC_PREFIX}:" + ":".join(f"{octet:02x}" for octet in address.packed[-3:])

def is_valid_mac(mac_address):
    """Helper function to validate a MAC address in the colon-separated hexadecimal form."""
    return bool(re.fullmatch(r'([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', mac_address or ''))

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
            client_instance = pylxd.Client(endpoint=address, verify=cert_path,
                                           cert=(CONTROLLER_CLIENT_CERT_FILE, CONTROLLER_CLIENT_KEY_FILE),
                                           project=project_name)
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

def wrap_get_remote_client(remote_node, project_name='default', raise_project_not_found=False,
                           test_project=True, show_info=True):
    """Wrapper function to handle exceptions when getting a remote client.
    
    Returns:    A pylxd.Client instance for the remote node and project if successful, False otherwise.
    """

    try:
        remote_client = get_remote_client(remote_node, project_name=project_name, raise_project_not_found=raise_project_not_found,
                                          test_project=test_project, show_info=show_info)
        return remote_client

    except ValueError as e:
        if "Project not found" in str(e):
            # do not log the error message if the project is not found
            return False 
        else:
            logger.error(f"Failed to retrieve client for '{remote_node}:{project_name}': {e}.")
            return False 
    except Exception as e:
        logger.error(f"Failed to retrieve client for '{remote_node}:{project_name}': {e}")
        return False

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

def get_projects(remote_name="local", timeout=None): 
    """Fetches and returns the list of projects as a JSON object.
    
    Returns:    A list of projects as JSON objects if successful. Otherwise, returns None.
    """
    try:
        if timeout:
            result = subprocess.run(['timeout', str(timeout),
                                     'incus', 'project', 'list', f"{remote_name}:", '--format', 'json'],
                                     capture_output=True, text=True)
        else:
            result = subprocess.run(['incus', 'project', 'list', f"{remote_name}:", '--format', 'json'],
                                    capture_output=True, text=True)
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

def run_incus_list(remote_node="local", project_name="default", empty_list_if_project_not_found=False):
    """Run the 'incus list -f json' command to get the instance state all the instances, optionally targeting a remote node and project.
    
    Return the output as a list of dict if successful
    Return None if the command fails.
    Return None if the project does not exist and empty_list_if_project_not_found is False (default).
    Retun an empty list if the project does not exist and empty_list_if_project_not_found is True.

    """
    try:
        # Check if the project exists
        command_check = ["incus", "project", "show", project_name]
        if remote_node:
            command_check = ["incus", "project", "show", f"{remote_node}:{project_name}"]

        result_check = subprocess.run(command_check, capture_output=True, text=True, check=True)

    except subprocess.CalledProcessError as e:
        if "Project not found" in e.stderr:
            if empty_list_if_project_not_found:
                return []
            else:
                return None
        else:
            logger.error(f"Failed to check if the project exists: {e}")
            return None

    except Exception as e:
        logger.error(f"Unexpected error while running 'incus project show': {e}")
        return None
    
    try:

        # If the project exists, proceed to list instances
        command = ["incus", "list", "-f", "json", "--project", project_name]
        if remote_node:
            command = ["incus", "list", f"{remote_node}:", "-f", "json", "--project", project_name]

        result = subprocess.run(command, capture_output=True, text=True, check=True)

        # Parse the JSON output
        instances = json.loads(result.stdout)

        return instances

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
        #logger.info(f"Instance '{name}' network config: {network_config}")
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

def iterator_over_instance_dicts(remote, project_name, instance_scope=None):
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

def iterator_over_instances(remote, project=None):
    """
    Iterates over all instances on a given Incus remote, covering all projects or a specific project.

    Returns:    A generator that yields a couple of project name and instance object for each instance.

    """
    # Connect to the remote Incus server
    client = get_remote_client(remote)  

    if project is None:
        # Iterate over all projects
        for my_project in client.projects.all():
            project_name = my_project.name

            # Create a project-specific client and switch to the current project
            project_client = get_remote_client(remote, project_name=project_name)
            project_client.project = project_name

            # Iterate over all instances within the current project
            for instance in project_client.instances.all():
                yield project_name, instance  # Yield both project name and instance object for each instance
    else:
        project_client = get_remote_client(remote, project_name=project)
        project_client.project = project
        for instance in project_client.instances.all():
            yield project_name, instance  # Yield both project name and instance object for each instance

def exec_command(instance, command):
    """
    Execute a command in an instance and handle the output and errors.

    Args:
        instance: The instance object where the command will be executed.
        command: List of command arguments to execute (e.g., ['ls', '-la']).

    Returns:
        tuple: (exit_code, stdout, stderr)
            - exit_code: Integer, 0 if the command was successful, non-zero otherwise.
            - stdout: String containing the command's standard output.
            - stderr: String containing the command's standard error.

    Raises:
        Exception: If there is an issue executing the command or accessing the instance.
    """
    try:
        result = instance.execute(command)
        # Handle decoding if stdout or stderr are bytes
        stdout = result.stdout.decode("utf-8").strip() if isinstance(result.stdout, bytes) else result.stdout.strip()
        stderr = result.stderr.decode("utf-8").strip() if isinstance(result.stderr, bytes) else result.stderr.strip()
        return result.exit_code, stdout, stderr
    except Exception as e:
        raise Exception(f"Error executing command '{' '.join(command)}': {e}")


#############################################
###### figo instance command functions #####
#############################################

def get_and_print_instances(COLS, remote_node=None, project_name=None, instance_scope=None, full=False, join=False,
                            additional=False):
    """Get instances from the specified remote node and project and add their details using add_row_to_output.

    If additional is False, an instance holding additional IP addresses is marked with a '+N'
    counter appended to its address column. If additional is True, each additional address gets
    its own row below the instance holding it, and the NAME and MAC columns are filled in.

    Returns:    False if fetching the instances failed, True otherwise.
    """

    RED = "\033[91m"
    GREEN = "\033[92m"
    RESET = "\033[0m"
    # Get the instances from 'incus list -f json'
    instances = run_incus_list(remote_node=remote_node, project_name=project_name, empty_list_if_project_not_found=True)
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

        # Additional IP addresses held by the instance (nested VMs, inner containers, extra
        # addresses on its own NIC). See ADDITIONAL_IPS_KEY.
        additional_entries = get_additional_ips_from_config(instance.get("config"))

        ip_str = format_ip_device_pairs(ip_device_pairs)
        if additional_entries:
            # The address column is narrow: spelling the addresses out inline would truncate
            # immediately and convey less than the counter does. Use -a/--additional to see them.
            ip_str = f"{ip_str} +{len(additional_entries)}"

        if full:
            # Print all profiles
            profiles_str = ", ".join(instance.get("profiles", []))
            reset_color = False
        else:
            # Print only GPU profiles with color coding based on state
            gpu_profiles = [profile for profile in instance.get("profiles", []) if profile.startswith("gpu")]
            plain_profiles_str = ", ".join(gpu_profiles)
            profiles_str = (f"{RED}{plain_profiles_str}{RESET}" if state == "run"
                            else f"{GREEN}{plain_profiles_str}{RESET}")
            reset_color = True

        # Join the context and instance name, when requested
        name_field = f"{context}.{name}" if join else name

        def build_row(instance_field, type_field, state_field, context_field,
                      ip_field, name_col, mac_col, profiles_field):
            """Assemble a row matching the columns selected in list_instances."""
            row = [instance_field, type_field, state_field]
            if not join:
                row.append(context_field)
            row.append(ip_field)
            if additional:
                # With -a the profiles are dropped: see the note in list_instances.
                row.extend([name_col, mac_col])
            else:
                row.append(profiles_field)
            return row

        add_row_to_output(COLS,
                          build_row(name_field, instance_type, state, context, ip_str, '', '', profiles_str),
                          reset_color=reset_color and not additional)

        if additional:
            # One row per additional address, below the instance holding it. STATE, CONTEXT and
            # PROFILES describe an instance, and an address is not one, so they are left empty.
            # The instance name is repeated so that every row stands on its own when the output
            # is grepped, sorted or pasted in isolation.
            for entry in additional_entries:
                add_row_to_output(COLS,
                                  build_row(name_field, 'additional_ip', '', '', entry['ip'],
                                            entry['name'] or '', entry['mac'] or '', ''))
    return True
    

def list_instances(remote_node=None, project_name=None, instance_scope=None, full=False, extend=False, join=False,
                   additional=False):
    """Print profiles of all instances, either from the local or a remote Incus node.

    If full is False, prints only GPU profiles with color coding.
    If full is True, prints all profiles.

    If extend is True, the output of each column is extended to the maximum width of the values in that column.
    If join is True, the context and intance name are joined into a single string and extend is set to True.

    If additional is True, each additional IP address held by an instance gets its own row, and
    the NAME and MAC columns are added. Otherwise those addresses are only summarised by a '+N'
    counter in the address column.

    """

    if join:
        extend = True

    # Determine the columns based on the 'full', 'join' and 'additional' flags.
    # With 'additional' the TYPE column must fit the 'additional_ip' value, and two columns are
    # added to carry the label and the MAC of each address.
    if join:
        COLS = [('INSTANCE WITH CONTEXT',35), ('TYPE', 13 if additional else 4), ('STATE',5)]
    else:
        COLS = [('INSTANCE',16), ('TYPE', 13 if additional else 4), ('STATE',5), ('CONTEXT',25)]
    COLS.append(('IP ADDRESS(ES)',25))
    if additional:
        # The profiles column is dropped in this view: it is empty by definition on the address
        # rows, and the room taken by TYPE, NAME and MAC already pushes the line close to the
        # width of a normal terminal. Whoever asks for -a is looking at addresses, not profiles.
        COLS.extend([('NAME',12), ('MAC',17)])
    else:
        COLS.append(('PROFILES',75) if full else ('GPU PROFILES',75))

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
                                                         instance_scope=instance_scope, full=full, join=join, additional=additional)
                        if not result:
                            set_of_errored_remotes.add(my_remote_node)
            else: # project_name is not None
                # Get instances for the specified project_name
                result = get_and_print_instances(COLS, remote_node=my_remote_node, project_name=project_name,
                                                 instance_scope=instance_scope, full=full, join=join, additional=additional)
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
                                                     instance_scope=instance_scope, full=full, join=join, additional=additional)
                    if not result:
                        set_of_errored_remotes.add(remote_node)
        else: # remote_node is not None and project_name is not None
            # Get instances from the specified remote node and project
            result = get_and_print_instances(COLS, remote_node=remote_node, project_name=project_name,
                                             instance_scope=instance_scope, full=full, join=join, additional=additional)
            if not result:
                set_of_errored_remotes.add(remote_node)

    flush_output(extend=extend)

    if set_of_errored_remotes:
        logger.error(f"Error: Failed to retrieve projects from remote(s): {', '.join(set_of_errored_remotes)}")

# --- GPU discovery: four outcomes, not a bare None --------------------------
#
# Section 7 of figo-gpu-resource-model.md: 'no GPU on this host', 'the host does
# not answer', 'the host is not in REMOTE_TO_IP_INFO_MAP' and 'the command
# failed' used to collapse into one ERROR + None. They are four different
# situations with four different reactions, and the third one is the ordinary
# state of every L1 host until req 13 lands: an L1 host must not look broken
# just because figo cannot yet reach it.

GPU_DISCOVERY_OK = 'ok'
GPU_DISCOVERY_NO_GPU = 'no_gpu'
GPU_DISCOVERY_UNREACHABLE = 'unreachable'
GPU_DISCOVERY_NOT_CONFIGURED = 'not_configured'
GPU_DISCOVERY_ERROR = 'error'

# ssh reserves 255 for its own failures: the remote command never returns it.
SSH_FAILURE_RETURNCODE = 255

# A PCI address, with or without the domain: '06:00.0' or '0000:06:00.0'.
PCI_ADDRESS_RE = re.compile(r'^(?:[0-9a-fA-F]{4}:)?[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]$')

GpuDiscovery = collections.namedtuple('GpuDiscovery', 'outcome pci_addresses detail')


def normalize_pci_address(pci_address):
    """Drop the default PCI domain: '0000:06:00.0' -> '06:00.0'.

    lspci omits the domain when it is 0000, profiles written by hand may carry
    it either way, and the two sides have to be compared: one form is needed.
    A non-default domain is kept, because there the domain is part of the name.
    """
    if not pci_address:
        return pci_address

    pci_address = pci_address.strip()
    parts = pci_address.split(':')
    if len(parts) == 3 and parts[0] == '0000':
        return ':'.join(parts[1:])
    return pci_address


def parse_lspci_nvidia(stdout):
    """Return the PCI addresses in the output of 'lspci | grep NVIDIA'.

    Pure function. Only the first field of a line is taken, and only when it is
    shaped like a PCI address: ssh banners, motd lines and warnings reach this
    output too, and none of them is a card.
    """
    addresses = set()
    for line in (stdout or '').splitlines():
        fields = line.strip().split()
        if fields and PCI_ADDRESS_RE.match(fields[0]):
            addresses.add(normalize_pci_address(fields[0]))
    return sorted(addresses)


def classify_gpu_discovery(remote, has_ssh_info, returncode, stdout, stderr):
    """Turn the result of the discovery command into one of the outcomes above.

    Pure function: it receives what the command returned and decides what that
    means, so the four cases can be tested without a host to run them on.

    Parameters:
        remote (str): name of the remote, for the messages.
        has_ssh_info (bool): whether the remote can be reached at all (True for
                             'local', which needs no SSH information).
        returncode (int): exit status of the command, None when it never ran.
        stdout (str), stderr (str): what it printed.

    Returns:
        GpuDiscovery: (outcome, PCI addresses, message).
    """
    if not has_ssh_info:
        return GpuDiscovery(GPU_DISCOVERY_NOT_CONFIGURED, [], (
            f"GPU discovery is not configured for remote '{remote}': no SSH information "
            f"in REMOTE_TO_IP_INFO_MAP. This is the normal state of a nested (L1) host "
            f"today; add an entry for the host that enumerates the cards to enable it."
        ))

    if returncode == SSH_FAILURE_RETURNCODE:
        return GpuDiscovery(GPU_DISCOVERY_UNREACHABLE, [], (
            f"Remote '{remote}' is unreachable over SSH, GPU inventory unknown"
            + (f": {stderr.strip()}" if (stderr or '').strip() else ".")
        ))

    if returncode == 0:
        addresses = parse_lspci_nvidia(stdout)
        if addresses:
            return GpuDiscovery(GPU_DISCOVERY_OK, addresses, (
                f"{len(addresses)} NVIDIA card(s) visible on remote '{remote}'."
            ))
        return GpuDiscovery(GPU_DISCOVERY_NO_GPU, [], (
            f"No NVIDIA card is visible on remote '{remote}'."
        ))

    if returncode == 1 and not (stderr or '').strip():
        # grep found nothing: the command worked, the host has no NVIDIA card.
        return GpuDiscovery(GPU_DISCOVERY_NO_GPU, [], (
            f"No NVIDIA card is visible on remote '{remote}'."
        ))

    return GpuDiscovery(GPU_DISCOVERY_ERROR, [], (
        f"GPU discovery failed on remote '{remote}' (exit {returncode})"
        + (f": {stderr.strip()}" if (stderr or '').strip() else ".")
    ))


def gpu_inventory(remote):
    """Enumerate the NVIDIA cards physically present on a remote.

    The I/O half of the discovery: it builds and runs the command, locally or
    over SSH, and hands the result to classify_gpu_discovery. lspci is inventory
    and physical-existence check only -- usage truth is read from the expanded
    devices of running instances (Section 2.3), never from here.

    Returns:
        GpuDiscovery: (outcome, PCI addresses, message).
    """
    if remote == 'local':
        command = 'lspci | grep NVIDIA'
    else:
        remote_info = REMOTE_TO_IP_INFO_MAP.get(remote) or {}
        ssh_host = remote_info.get("ssh_host")
        if not ssh_host:
            return classify_gpu_discovery(remote, False, None, '', '')

        ssh_user = remote_info.get("ssh_user", "ubuntu")
        ssh_port = remote_info.get("ssh_port", 22)
        command = f"ssh -p {ssh_port} {ssh_user}@{ssh_host} 'lspci | grep NVIDIA'"

    try:
        result = subprocess.run(command, capture_output=True, text=True, shell=True)
    except Exception as e:
        return GpuDiscovery(GPU_DISCOVERY_ERROR, [], (
            f"GPU discovery could not be run for remote '{remote}': {e}"
        ))

    return classify_gpu_discovery(remote, True, result.returncode, result.stdout, result.stderr)


def report_gpu_discovery(discovery):
    """Log a discovery outcome with the tone the model prescribes.

    A host with no card is not a host in trouble: 'no GPU' is a result, not an
    error, and the non-interference rule of Section 7 forbids polluting the
    output of decisions that do not need GPU information at all.
    """
    if discovery.outcome in (GPU_DISCOVERY_OK, GPU_DISCOVERY_NO_GPU):
        return
    logger.error(discovery.detail)


# --- Deployment configuration ----------------------------------------------

def load_figo_config(path=None):
    """Read the deployment configuration file, or return an empty configuration.

    A missing file is the normal case, not an error: everything figo reads from
    here has a fallback in the source, so an installation that never creates the
    file behaves exactly as before. A file that exists and cannot be parsed is a
    different matter and is reported, because silently ignoring it would make
    figo run with settings the administrator believes are in force.

    Parameters:
        path (str): file to read; defaults to CONFIG_FILE.

    Returns:
        dict: the parsed configuration, or {}.
    """
    path = CONFIG_FILE if path is None else path

    if not os.path.exists(path):
        return {}

    try:
        with open(path, 'r') as config_file:
            config = yaml.safe_load(config_file)
    except (OSError, yaml.YAMLError) as e:
        logger.error(f"Cannot read the configuration file '{path}': {e}")
        return {}

    if config is None:
        return {}
    if not isinstance(config, dict):
        logger.error(f"Configuration file '{path}' does not contain a mapping: ignored.")
        return {}

    return config


# --- Network: which gw-float serves an instance -----------------------------
#
# Section 3.4 of figo-network-model.md: a floating IP is served by the gw-float
# of the instance's own subnet. Resolution is a named function with one answer
# even while there is a single gateway deployed, because the mistake to avoid is
# '10.202.9.254' appearing in a dozen places.

FLOAT_GATEWAY_SERVED = 'served'
FLOAT_GATEWAY_DEPLOYABLE = 'deployable'
FLOAT_GATEWAY_NO_PUBLIC_VLAN = 'no_public_vlan'
FLOAT_GATEWAY_UNKNOWN_VLAN = 'unknown_vlan'
FLOAT_GATEWAY_UNKNOWN_SUBNET = 'unknown_subnet'

FloatGatewayResolution = collections.namedtuple(
    'FloatGatewayResolution', 'outcome subnet host gateway detail'
)


def subnet_of_remote(remote_info):
    """Derive the instance subnet of a remote from its gateway and prefix length.

    Pure function. The subnet is not declared anywhere: it is implied by the
    entries figo already has in REMOTE_TO_IP_INFO_MAP, and deriving it keeps the
    deployment inventory in one place instead of two that can disagree. Note
    that several remotes can share one subnet -- 'jeeg' and the controller are
    virtual machines of goldrake and sit on its subnet -- which is exactly why
    the gateway is resolved per subnet and not per remote.

    Returns:
        str: the subnet in CIDR form, or None when the remote does not describe one.
    """
    gateway_address = (remote_info or {}).get('gw')
    prefix_len = (remote_info or {}).get('prefix_len')
    if not gateway_address or not prefix_len:
        return None

    try:
        return str(ipaddress.ip_network(f"{gateway_address}/{prefix_len}", strict=False))
    except ValueError:
        return None


UPSTREAM_CONFIDENCE = ('verified', 'declared', 'suspected')
UPSTREAM_EFFECTS = ('blocked', 'allowed')
UPSTREAM_PROTOCOLS = ('tcp', 'udp', 'icmp')


def parse_upstream_policy(config, today=None):
    """Read 'upstream_policy' into normalised assertions about the outside world.

    Pure function. Section 7.2: what the external network permits is knowledge
    figo holds on somebody else's word. It cannot be measured from inside the
    testbed (7.5), so it is never a refusal -- only a warning that names who
    said it and when, so the reader can judge it.

    Two rules are enforced here instead of being left to whoever writes the
    file, because both failures are silent:

    - an entry without a date, a source or a confidence level is dropped. A
      policy file with no provenance looks authoritative and cannot be judged,
      which is worse than not having the entry at all.
    - the scope is read exactly as written and never widened. An assertion
      stated more broadly than it was verified produces false warnings, and
      false warnings train people to ignore warnings. The network model got
      this wrong once, generalising a comment about one address to a whole /24
      that was later shown to allow the port.

    Returns:
        tuple: (entries, warnings). Each entry carries 'public_ip' or
               'public_range', 'protocol', 'ports', 'effect', 'confidence',
               'source', 'date' and 'note'.
    """
    warnings = []
    entries = []

    section = (config or {}).get('upstream_policy')
    if section is None:
        return [], warnings
    if not isinstance(section, list):
        return [], ["'upstream_policy' is not a list: ignored."]

    for position, raw in enumerate(section, start=1):
        where = f"upstream_policy entry {position}"
        if not isinstance(raw, dict):
            warnings.append(f"{where} is not a mapping: ignored.")
            continue

        scope = raw.get('scope') or {}
        public_ip, public_range = None, None
        if isinstance(scope, dict) and scope.get('public_ip'):
            try:
                public_ip = str(ipaddress.ip_address(str(scope['public_ip'])))
            except ValueError:
                warnings.append(f"{where}: '{scope['public_ip']}' is not an address: ignored.")
                continue
        elif isinstance(scope, dict) and scope.get('public_range'):
            try:
                public_range = str(ipaddress.ip_network(str(scope['public_range']), strict=False))
            except ValueError:
                warnings.append(f"{where}: '{scope['public_range']}' is not a subnet: ignored.")
                continue
        else:
            warnings.append(
                f"{where} has no scope: an assertion about 'the network' cannot be "
                f"judged, and would warn about every mapping. Ignored."
            )
            continue

        protocol = str(raw.get('protocol') or '').lower()
        if protocol not in UPSTREAM_PROTOCOLS:
            warnings.append(f"{where}: unknown protocol '{raw.get('protocol')}': ignored.")
            continue

        ports = []
        if protocol != 'icmp':
            declared = raw.get('ports')
            if not isinstance(declared, list) or not declared:
                warnings.append(
                    f"{where}: {protocol} needs a list of ports; an entry about every "
                    f"port of an address is broader than anything anyone verified. Ignored."
                )
                continue
            for port in declared:
                try:
                    number = int(port)
                except (TypeError, ValueError):
                    number = -1
                if not 1 <= number <= 65535:
                    warnings.append(f"{where}: '{port}' is not a port: ignored.")
                    number = None
                if number:
                    ports.append(number)
            if not ports:
                continue

        effect = str(raw.get('effect') or '').lower()
        if effect not in UPSTREAM_EFFECTS:
            warnings.append(f"{where}: 'effect' must be blocked or allowed: ignored.")
            continue

        confidence = str(raw.get('confidence') or '').lower()
        if confidence not in UPSTREAM_CONFIDENCE:
            warnings.append(
                f"{where}: 'confidence' must be verified, declared or suspected. "
                f"Without it the warning cannot say how much to trust it. Ignored."
            )
            continue

        source = str(raw.get('source') or '').strip()
        if not source:
            warnings.append(
                f"{where}: 'source' is required. A constraint nobody is named for "
                f"cannot be questioned, only obeyed. Ignored."
            )
            continue

        date = str(raw.get('date') or '').strip()
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            warnings.append(
                f"{where}: 'date' must be a date (YYYY-MM-DD). This knowledge decays, "
                f"and an undated assertion looks authoritative forever. Ignored."
            )
            continue

        entries.append({
            'public_ip': public_ip,
            'public_range': public_range,
            'protocol': protocol,
            'ports': ports,
            'direction': str(raw.get('direction') or '').lower() or None,
            'effect': effect,
            'confidence': confidence,
            'source': source,
            'date': date,
            'note': raw.get('note'),
        })

    return entries, warnings


def upstream_constraints(entries, public_ip, protocol, public_ports=()):
    """The policy entries that bear on these ports of this address.

    Pure function. Matching is containment on the address and exact on the
    ports: an entry about port 22 says nothing about port 80, and one about an
    address says nothing about its neighbour. Widening either would be the
    false-warning failure Section 7.2 warns against.

    Returns:
        list: (entry, matched ports) pairs, in the order the entries were read.
    """
    try:
        address = ipaddress.ip_address(public_ip)
    except ValueError:
        return []

    matches = []
    for entry in entries or []:
        if entry['protocol'] != protocol:
            continue
        if entry['public_ip'] is not None:
            if entry['public_ip'] != str(address):
                continue
        elif address not in ipaddress.ip_network(entry['public_range']):
            continue

        if protocol == 'icmp':
            matches.append((entry, []))
            continue

        hit = sorted(set(entry['ports']) & set(int(port) for port in public_ports or []))
        if hit:
            matches.append((entry, hit))

    return matches


def format_upstream_warning(entry, ports=(), today=None):
    """Render one constraint as a warning that can be judged rather than obeyed.

    Pure function. It says three things the reader needs and one they do not
    get anywhere else: what is reported, who reported it, and how old that is.
    'declared' and 'suspected' say plainly that nobody measured it -- the
    testbed has no vantage point from which to (7.5).
    """
    what = entry['protocol']
    if ports:
        what += "/" + ",".join(str(port) for port in ports)

    where = entry['public_ip'] or entry['public_range']
    today = today or datetime.date.today()
    age = (today - datetime.date.fromisoformat(entry['date'])).days
    when = f"recorded {entry['date']}"
    if age > 0:
        when += f", {age} day{'s' if age != 1 else ''} ago"

    how = {
        'verified': "measured from outside on that date",
        'declared': "stated by whoever administers the network, never tested",
        'suspected': "inferred, never confirmed",
    }[entry['confidence']]

    message = (
        f"{what} towards {where} is reported {entry['effect']} upstream "
        f"({entry['confidence']}: {how}; source \"{entry['source']}\", {when})."
    )
    if entry.get('note'):
        message += f" Note: {entry['note']}."
    return message


def parse_network_config(config):
    """Read the 'network' section of the configuration into normalised form.

    Pure function. Only two things live here, and both are facts that exist
    nowhere else today: which subnet has a floating-IP gateway, and whether the
    host of a subnet has an interface on a public VLAN -- the prerequisite for
    deploying one (Section 3.4). Subnets themselves are *not* redeclared: they
    are derived from the remotes.

    Malformed entries are reported and dropped rather than guessed at.

    Returns:
        tuple: (network, warnings) where network is
               {'gateways': {subnet: {'scope', 'address'}},
                'subnets': {subnet: {'host', 'public_vlan'}}}.
    """
    warnings = []
    gateways = {}
    subnets = {}

    section = (config or {}).get('network') or {}
    if not isinstance(section, dict):
        return {'gateways': {}, 'subnets': {}}, [
            "The 'network' section of the configuration is not a mapping: ignored."
        ]

    def normalised(subnet, where):
        try:
            return str(ipaddress.ip_network(subnet, strict=False))
        except ValueError:
            warnings.append(f"'{subnet}' in network.{where} is not a subnet: ignored.")
            return None

    for subnet, entry in (section.get('subnets') or {}).items():
        key = normalised(subnet, 'subnets')
        if key is None:
            continue
        entry = entry or {}
        public_vlan = entry.get('public_vlan')
        if public_vlan is not None and not isinstance(public_vlan, bool):
            warnings.append(
                f"network.subnets['{subnet}'].public_vlan is not true or false: "
                f"treated as unknown."
            )
            public_vlan = None
        subnets[key] = {'host': entry.get('host'), 'public_vlan': public_vlan}

    for subnet, entry in (section.get('float_gateways') or {}).items():
        key = normalised(subnet, 'float_gateways')
        if key is None:
            continue
        entry = entry or {}
        if not entry.get('scope'):
            warnings.append(
                f"network.float_gateways['{subnet}'] has no 'scope' "
                f"(remote:project.instance of the gateway): ignored."
            )
            continue
        gateways[key] = {'scope': entry['scope'], 'address': entry.get('address')}
        subnets.setdefault(key, {'host': None, 'public_vlan': None})

    return {'gateways': gateways, 'subnets': subnets}, warnings


def network_subnets(remote_map, network):
    """Merge the subnets derived from the remotes with what configuration adds.

    Pure function. The remotes say which subnets exist; the configuration says
    who hosts them and whether that host has a public VLAN. A subnet known from
    a remote but absent from configuration is kept, with its facts unknown --
    dropping it would make an instance look as if it lived nowhere.

    Returns:
        dict: {subnet: {'host', 'public_vlan', 'remotes': [names]}}.
    """
    subnets = {}

    for remote, remote_info in (remote_map or {}).items():
        subnet = subnet_of_remote(remote_info)
        if subnet is None:
            continue
        entry = subnets.setdefault(subnet, {'host': None, 'public_vlan': None, 'remotes': []})
        entry['remotes'].append(remote)

    for subnet, entry in (network or {}).get('subnets', {}).items():
        merged = subnets.setdefault(subnet, {'host': None, 'public_vlan': None, 'remotes': []})
        merged['host'] = entry.get('host')
        merged['public_vlan'] = entry.get('public_vlan')

    for entry in subnets.values():
        entry['remotes'].sort()

    return subnets


def resolve_float_gateway(instance_address, subnets, gateways):
    """Decide which gw-float serves an address, or why none does.

    Pure function, and total: every address gets an answer, and the four answers
    that are not 'served' differ because the remedy differs (Section 3.4). A
    refusal that says 'not supported' teaches nothing; one that says whether the
    gateway can be deployed, or whether the obstacle is at switch level, tells
    the administrator what to do next.

    Parameters:
        instance_address (str): the private address of the instance.
        subnets (dict): from network_subnets.
        gateways (dict): {subnet: {'scope', 'address'}}.

    Returns:
        FloatGatewayResolution: (outcome, subnet, host, gateway, detail).
    """
    try:
        address = ipaddress.ip_address(str(instance_address).split('/')[0])
    except ValueError:
        return FloatGatewayResolution(
            FLOAT_GATEWAY_UNKNOWN_SUBNET, None, None, None,
            f"'{instance_address}' is not an IP address."
        )

    match = None
    for subnet in subnets:
        try:
            network = ipaddress.ip_network(subnet)
        except ValueError:
            continue
        if address in network:
            # Longest prefix wins: /25 instance ranges overlap /24 host networks.
            if match is None or network.prefixlen > ipaddress.ip_network(match).prefixlen:
                match = subnet

    if match is None:
        return FloatGatewayResolution(
            FLOAT_GATEWAY_UNKNOWN_SUBNET, None, None, None,
            f"Address {address} is in no subnet figo knows: add it to the 'network' "
            f"section of {CONFIG_FILE}, or check the address."
        )

    entry = subnets[match]
    host = entry.get('host')
    named_host = f"'{host}'" if host else "its host"

    if match in gateways:
        gateway = gateways[match]
        where = f" at {gateway['address']}" if gateway.get('address') else ""
        return FloatGatewayResolution(
            FLOAT_GATEWAY_SERVED, match, host, gateway,
            f"Subnet {match} is served by the floating-IP gateway "
            f"'{gateway['scope']}'{where}."
        )

    if entry.get('public_vlan') is True:
        return FloatGatewayResolution(
            FLOAT_GATEWAY_DEPLOYABLE, match, host, None,
            f"Subnet {match} has no floating-IP gateway yet, but {named_host} has a "
            f"public VLAN: deploy one with 'figo net gateway deploy'."
        )

    if entry.get('public_vlan') is False:
        return FloatGatewayResolution(
            FLOAT_GATEWAY_NO_PUBLIC_VLAN, match, host, None,
            f"Subnet {match} cannot have a floating-IP gateway: {named_host} has no "
            f"interface on a public VLAN, which a gateway needs for its macvlan. "
            f"That is a switch-level change, outside figo."
        )

    return FloatGatewayResolution(
        FLOAT_GATEWAY_UNKNOWN_VLAN, match, host, None,
        f"Subnet {match} has no floating-IP gateway, and it is not recorded whether "
        f"{named_host} has a public VLAN. Check, then set 'public_vlan' for that "
        f"subnet in {CONFIG_FILE}."
    )


# --- Talking to a gw-float gateway ------------------------------------------
#
# Read-only. The state of the floating IPs is the config.yaml *inside* the
# gateway container, read through 'floating-ip list --json' (Section 3.2): never
# the example file in the repository, never a parallel registry in figo.

GATEWAY_PROBE_OK = 'ok'
GATEWAY_PROBE_NOT_FOUND = 'not_found'
GATEWAY_PROBE_UNREACHABLE = 'unreachable'
GATEWAY_PROBE_ERROR = 'error'

GatewayProbe = collections.namedtuple('GatewayProbe', 'outcome mappings detail')


def incus_exec_argv(scope, command):
    """Build the incus command line that runs 'command' inside a scoped instance.

    Pure function, and it exists because the two notations look alike and are
    not: figo writes an instance as 'remote:project.instance', while incus wants
    'remote:instance' with the project as an option. Writing the figo form
    straight into an incus command yields 'Instance not found', which reads like
    a missing container rather than a wrong command line.

    Parameters:
        scope (str): 'remote:project.instance', or 'remote:instance' for the
                     default project, or a bare instance name for 'local'.
        command (list): the command to run inside the instance.

    Returns:
        list: the argv of the incus invocation.
    """
    remote, _, rest = scope.rpartition(':')
    project, _, instance = rest.partition('.')
    if not instance:
        project, instance = 'default', project

    target = f"{remote}:{instance}" if remote else instance
    return ['incus', 'exec', target, '--project', project, '--'] + list(command)


def parse_floating_ip_list(stdout):
    """Read the JSON of 'floating-ip list --json' into a list of mappings.

    Pure function. Shape measured on blade3 on 2026-08-28, after the gateway
    was upgraded to the tree that carries the write verbs:

        {"mappings": [{"public", "private", "enabled", "mode", "active",
                       "label", "note",
                       "allow": {"tcp": [{"pub_port", "priv_port"}],
                                 "icmp": ["echo-reply"] | "all"},
                       "drift": {"missing", "extra", "consistent"}}],
         "drift_summary": {"consistent", "inconsistent", "extra_rules"}}

    'enabled' is what the YAML asks for and 'active' what is actually on the
    interface: the gateway keeps them apart on purpose, for an external consumer,
    and figo is that consumer -- so they are carried separately and never merged
    into one 'is it working' flag. 'drift' is a third question and not a
    combination of the first two: it compares the configuration with the
    installed iptables rules, which neither 'enabled' nor 'active' can see. It
    is therefore carried as the gateway reports it and never deduced.

    An absent 'drift' is carried as None, not as consistent: a gateway too old
    to report it has not said the rules are right, and the difference between
    'no drift' and 'nobody looked' is the whole value of the field.

    'allow.icmp' is a list of type names or the string "all", which is how the
    gateway renders 'icmp: true'. The two are kept in separate keys because a
    string is iterable: list("all") is ['a', 'l', 'l'], three ICMP types that do
    not exist, and nothing downstream would report it.

    Returns:
        tuple: (mappings, warnings).
    """
    try:
        payload = json.loads(stdout or '')
    except ValueError as e:
        return [], [f"The gateway did not return valid JSON: {e}"]

    if not isinstance(payload, dict) or 'mappings' not in payload:
        return [], ["The gateway output has no 'mappings' key: unexpected format."]

    mappings = []
    warnings = []
    for entry in payload.get('mappings') or []:
        if not isinstance(entry, dict) or not entry.get('public'):
            warnings.append(f"Skipping a mapping with no public address: {entry!r}.")
            continue
        allow = entry.get('allow') or {}
        icmp_value = allow.get('icmp')
        icmp_all = icmp_value == 'all'
        drift = entry.get('drift')
        drift = {
            'missing': drift.get('missing') or 0,
            'extra': drift.get('extra') or 0,
            'consistent': bool(drift.get('consistent')),
        } if isinstance(drift, dict) else None
        mappings.append({
            'public': entry.get('public'),
            'private': entry.get('private'),
            'enabled': bool(entry.get('enabled')),
            'active': bool(entry.get('active')),
            'mode': entry.get('mode'),
            'label': entry.get('label'),
            'note': entry.get('note'),
            'drift': drift,
            'tcp': [
                (port.get('pub_port'), port.get('priv_port'))
                for port in (allow.get('tcp') or [])
            ],
            'udp': [
                (port.get('pub_port'), port.get('priv_port'))
                for port in (allow.get('udp') or [])
            ],
            'icmp': [] if icmp_all else list(icmp_value or []),
            'icmp_all': icmp_all,
        })

    return mappings, warnings


def summarize_rule_drift(mappings):
    """Count the mappings whose installed rules differ from the configuration.

    Pure function. The gateway answers a question 'enabled' and 'active' cannot:
    those two compare what the configuration asks for with what is on the
    interface, while this one compares the configuration with the iptables rules
    actually installed. A mapping can be enabled, hold its address, and still
    have the wrong rules.

    Returns:
        tuple: (reported, inconsistent). 'reported' is False when no mapping
               carries the field -- a gateway too old to answer -- and the caller
               must show that as unknown, never as zero: 'nobody looked' and 'the
               rules are right' are different answers, and only one of them is
               good news.
    """
    known = [m for m in mappings or [] if m.get('drift') is not None]
    if not known:
        return False, 0
    return True, sum(1 for m in known if not m['drift'].get('consistent'))


def classify_gateway_probe(scope, returncode, stdout, stderr):
    """Turn the result of the gateway query into a distinct outcome.

    Pure function, same reasoning as the GPU discovery taxonomy: 'the gateway
    container is not there', 'the remote does not answer' and 'the command
    failed' are three different situations, and collapsing them hides which one
    the administrator has to fix.
    """
    error_text = (stderr or '').strip()

    if returncode == 0:
        mappings, warnings = parse_floating_ip_list(stdout)
        if warnings and not mappings:
            return GatewayProbe(GATEWAY_PROBE_ERROR, [], "; ".join(warnings))
        detail = f"{len(mappings)} mapping(s) on '{scope}'."
        if warnings:
            detail += " " + " ".join(warnings)
        return GatewayProbe(GATEWAY_PROBE_OK, mappings, detail)

    lowered = error_text.lower()
    # 'instance not found' and not merely 'not found': the command missing
    # *inside* the container reports 'command not found', which is a different
    # fault with a different fix.
    if 'instance not found' in lowered:
        return GatewayProbe(GATEWAY_PROBE_NOT_FOUND, [], (
            f"No gateway instance '{scope}': check the 'scope' recorded for this "
            f"subnet in {CONFIG_FILE}. ({error_text})"
        ))
    if 'connect' in lowered or 'no route to host' in lowered or 'refused' in lowered:
        return GatewayProbe(GATEWAY_PROBE_UNREACHABLE, [], (
            f"Cannot reach the remote hosting '{scope}': {error_text}"
        ))

    return GatewayProbe(GATEWAY_PROBE_ERROR, [], (
        f"Querying the gateway '{scope}' failed (exit {returncode})"
        + (f": {error_text}" if error_text else ".")
    ))


def probe_gateway(scope):
    """Ask a gw-float instance for its floating-IP mappings. Read-only.

    Runs 'floating-ip list' and nothing else: no 'apply', no write. The gateway
    on blade3 is production, and figo has no business changing it while merely
    reporting on it.

    Returns:
        GatewayProbe: (outcome, mappings, message).
    """
    argv = incus_exec_argv(scope, ['floating-ip', 'list', '--json'])
    try:
        result = subprocess.run(argv, capture_output=True, text=True)
    except Exception as e:
        return GatewayProbe(GATEWAY_PROBE_ERROR, [], (
            f"Could not run the gateway query for '{scope}': {e}"
        ))

    return classify_gateway_probe(scope, result.returncode, result.stdout, result.stderr)


def get_pci_addresses (remote):
    """Get the PCI addresses of the GPUs available on the remote node.

    Compatibility wrapper over gpu_inventory for the callers that only want the
    list. None still means "unknown", but a host with no card now returns an
    empty list instead of a failure, which is what it is.

    Returns:    A list of PCI addresses if the inventory could be read, None otherwise.
    """
    discovery = gpu_inventory(remote)
    report_gpu_discovery(discovery)

    if discovery.outcome in (GPU_DISCOVERY_OK, GPU_DISCOVERY_NO_GPU):
        return discovery.pci_addresses
    return None


# Canonical name of a GPU profile: gpu-vm-N-PCI or gpu-cnt-N-PCI, where N is the
# 1-based, human-facing index of the card on that remote. The index is read from
# the name; the PCI address is always read from the device inside the profile,
# never from the name.
GPU_PROFILE_NAME_RE = re.compile(r'^gpu-(vm|cnt)-(\d+)-')


def gpu_devices_of(devices):
    """Return the PCI addresses of the physical GPU devices in a device dictionary.

    'gputype' defaults to 'physical' in Incus, so a device that omits the key is
    taken as physical rather than skipped. A GPU device with no 'pci' cannot be
    accounted for and is left out: figo can only reason about cards it can name.

    Parameters:
        devices (dict): a device dictionary, e.g. an instance's expanded_devices
                        or a profile's devices.

    Returns:
        set: the PCI addresses assigned by those devices.
    """
    return {
        device.get('pci') for device in (devices or {}).values()
        if device.get('type') == 'gpu'
        and device.get('gputype', 'physical') == 'physical'
        and device.get('pci')
    }


def classify_gpu_profile(profile_name, devices):
    """Read one profile the way the read path prescribes: from its device, not its name.

    Pure function. Section 2.2: the 'gpu-vm-' / 'gpu-cnt-' prefix is policy, and
    it is binding only when choosing what to attach or detach; the card a profile
    assigns is always read from the GPU device inside it. A profile named like a
    GPU profile but shaped like something else is reported and left out of the
    offer -- never counted, never guessed at.

    Parameters:
        profile_name (str): the profile name.
        devices (dict): the profile's devices.

    Returns:
        tuple: (kind, card index, PCI address, warning).
               kind is 'vm', 'cnt' or None when the profile is not part of the
               offer; warning is a sentence to log, or None. A profile whose name
               does not start with 'gpu-' returns (None, None, None, None): it is
               not a GPU profile and not figo's business.
    """
    if not profile_name.startswith('gpu-'):
        return None, None, None, None

    pci_addresses = gpu_devices_of(devices)
    if not pci_addresses:
        return None, None, None, (
            "is named like a GPU profile but carries no usable GPU device: ignored"
        )

    if len(pci_addresses) > 1:
        return None, None, None, (
            f"assigns more than one GPU ({', '.join(sorted(pci_addresses))}): only "
            f"canonical one-card profiles are part of the offer"
        )

    pci_address = normalize_pci_address(pci_addresses.pop())

    name_match = GPU_PROFILE_NAME_RE.match(profile_name)
    if not name_match:
        return None, None, pci_address, (
            f"assigns GPU {pci_address} but does not follow the 'gpu-vm-N-PCI' / "
            f"'gpu-cnt-N-PCI' convention: the card it offers cannot be referred to "
            f"by index and is not part of the offer"
        )

    kind = 'vm' if name_match.group(1) == 'vm' else 'cnt'
    return kind, int(name_match.group(2)), pci_address, None


def gpu_offer_details(remote):
    """Return the offer of a remote, keeping the profile that declares each card.

    Same reading as gpu_offer, which is now a view over this one; 'gpu status'
    needs the profile names as well, and reading the profiles twice to get them
    would be two chances to disagree.

    Returns:
        dict: {'vm': {card index: (PCI address, profile name)}, 'cnt': {...}}.
    """
    offer = {'vm': {}, 'cnt': {}}

    client = get_remote_client(remote)
    if not client:
        logger.error(f"Failed to connect to remote '{remote}'.")
        return offer

    for profile in client.profiles.all():
        kind, card_index, pci_address, warning = classify_gpu_profile(
            profile.name, profile.devices
        )
        if warning:
            logger.warning(f"Profile '{profile.name}' on remote '{remote}' {warning}.")
        if kind is None:
            continue
        offer[kind][card_index] = (pci_address, profile.name)

    return offer


def gpu_offer(remote, instance_type):
    """Return the cards a remote offers to an instance type, as {index: pci_address}.

    The offer is declared by the existence of the canonical profiles
    'gpu-vm-N-PCI' (cards offered to VMs) and 'gpu-cnt-N-PCI' (cards offered to
    containers): the prefix is the per-card policy, so a card can be offered to
    VMs, to containers, to both, or to neither. A profile whose name starts with
    'gpu-' but carries no usable GPU device is reported and left out: on the read
    path names never carry semantics, devices do.

    Parameters:
        remote (str): name of the remote.
        instance_type (str): 'vm' or 'container'.

    Returns:
        dict: {card index (int): PCI address (str)}.
    """
    if instance_type == 'vm':
        kind = 'vm'
    elif instance_type == 'container':
        kind = 'cnt'
    else:
        raise ValueError("Invalid instance type. Must be 'vm' or 'container'.")

    return {
        card_index: pci_address
        for card_index, (pci_address, _profile_name) in gpu_offer_details(remote)[kind].items()
    }


def gpu_holders(remote):
    """Return which running instances hold which card on a remote.

    Usage is read from the expanded devices of the running instances of every
    project, so a card counts as held however it was assigned: through a canonical
    figo profile, through a profile with any other name, or through a device
    attached directly with 'incus config device add'. Cards are keyed by PCI
    address, which is local to the remote that enumerates it.

    Instances that are not running hold nothing: figo releases resources on stop.

    Parameters:
        remote (str): name of the remote.

    Returns:
        tuple: (vm_holders, container_holders), each a dict
               {PCI address: [(project name, instance name), ...]}.
    """
    vm_holders = {}
    container_holders = {}

    for project_name, instance in iterator_over_instances(remote):
        if instance.status != "Running":
            continue

        holders = vm_holders if instance.type == "virtual-machine" else container_holders
        for pci_address in gpu_devices_of(instance.expanded_devices):
            holders.setdefault(pci_address, []).append((project_name, instance.name))

    return vm_holders, container_holders


def gpu_usage_by_card(remote):
    """Return every instance that references a card on a remote, whatever its state.

    Companion of gpu_holders, which answers the start-time question -- who holds
    this card *right now*. Here stopped instances count too: because figo releases
    resources on stop, what is merely assigned today is what will contend at the
    next start, and that is the difference between the RUNNING and the ASSIGNED
    column of 'gpu status'.

    Parameters:
        remote (str): name of the remote.

    Returns:
        dict: {PCI address: [(project, instance name, state, 'vm'|'container'), ...]}.
    """
    usage = {}

    for project_name, instance in iterator_over_instances(remote):
        instance_type = 'vm' if instance.type == "virtual-machine" else 'container'
        for pci_address in gpu_devices_of(instance.expanded_devices):
            usage.setdefault(normalize_pci_address(pci_address), []).append(
                (project_name, instance.name, instance.status, instance_type)
            )

    return usage


GpuStatusRow = collections.namedtuple(
    'GpuStatusRow', 'card_index pci cnt_profile vm_profile running assigned held_by note'
)


def build_gpu_status_rows(offer_details, inventory_pci_addresses, usage):
    """Build the per-card rows of 'figo gpu status'.

    Pure function: it receives the offer (which cards are offered, to whom, by
    which profile), the physical inventory read from lspci, and who is using
    what, and merges them into one row per card. The three sources disagree in
    ways that matter, and the row is where that shows: a card can be offered and
    absent (profile left behind after a hardware change), present and not offered
    (assigned by hand, or reserved), used and not offered (the same, seen through
    a running instance).

    Parameters:
        offer_details (dict): {'vm': {index: (pci, profile)}, 'cnt': {...}}.
        inventory_pci_addresses (list or None): what lspci saw; None when the
                                                inventory could not be read at
                                                all, which is a different thing
                                                from an empty one.
        usage (dict): {pci: [(project, name, state, type), ...]}, from gpu_usage_by_card.

    Returns:
        tuple: (rows, notes). rows are GpuStatusRow, cards of the offer first in
               index order, then the cards outside it in PCI order; notes are
               sentences about inconsistencies found while merging.
    """
    notes = []
    cards = {}

    def card_of(pci_address):
        return cards.setdefault(pci_address, {'index': None, 'vm': None, 'cnt': None})

    for kind in ('cnt', 'vm'):
        for card_index, (pci_address, profile_name) in sorted(offer_details.get(kind, {}).items()):
            card = card_of(pci_address)
            card[kind] = profile_name
            if card['index'] is None:
                card['index'] = card_index
            elif card['index'] != card_index:
                notes.append(
                    f"GPU {pci_address} is offered under two different card indexes "
                    f"({card['index']} and {card_index}): the vm and cnt profiles of a "
                    f"card are meant to carry the same index."
                )

    index_owner = {}
    for pci_address, card in cards.items():
        if card['index'] is None:
            continue
        if card['index'] in index_owner and index_owner[card['index']] != pci_address:
            notes.append(
                f"Card index {card['index']} is used by two different GPUs "
                f"({index_owner[card['index']]} and {pci_address}): indexes are meant "
                f"to name one card each."
            )
        index_owner.setdefault(card['index'], pci_address)

    inventory = set(inventory_pci_addresses or [])
    for pci_address in inventory:
        card_of(pci_address)
    for pci_address in usage:
        card_of(pci_address)

    rows = []
    for pci_address, card in cards.items():
        holders = usage.get(pci_address, [])

        running_containers = [h for h in holders if h[3] == 'container' and h[2] == "Running"]
        running_vms = [h for h in holders if h[3] == 'vm' and h[2] == "Running"]

        if running_vms:
            held_by = ", ".join(
                f"VM '{name}' ({project}, vfio)"
                for project, name, _state, _type in sorted(running_vms, key=lambda h: (h[1], h[0]))
            )
        else:
            held_by = "-"

        note = []
        if card['index'] is None:
            note.append("not offered")
        if inventory_pci_addresses is not None and pci_address not in inventory:
            note.append("not in lspci")

        rows.append(GpuStatusRow(
            card_index=card['index'],
            pci=pci_address,
            cnt_profile=card['cnt'] or "-",
            vm_profile=card['vm'] or "-",
            running=len(running_containers),
            assigned=len(holders),
            held_by=held_by,
            note=", ".join(note),
        ))

    rows.sort(key=lambda row: (row.card_index is None, row.card_index or 0, row.pci))
    return rows, notes


def format_gpu_card_instances(row, usage):
    """Render the instance list of one card for 'gpu status -i'.

    Running instances first, because they are the ones holding the card; the
    others follow, since release-on-stop makes them the contention of the next
    start rather than of now.

    Returns:
        str: one line, or the card with an explicit '-' when nothing uses it.
    """
    label = f"CARD {row.card_index if row.card_index is not None else '-'} ({row.pci}):"
    holders = usage.get(row.pci, [])
    if not holders:
        return f"{label}  -"

    # The state is upper-cased as it is in the refusal message of Section 4: in a
    # line about contention, the state is the load-bearing word.
    ordered = sorted(holders, key=lambda h: (h[2] != "Running", h[1], h[0]))
    rendered = ", ".join(
        f"{name} ({project}, {state.upper()})" for project, name, state, _type in ordered
    )
    return f"{label}  {rendered}"


def gpu_start_decision(requested, vm_holders, container_holders, instance_type):
    """Decide whether a start may proceed, given the cards it wants and their holders.

    Pure function: no client, no I/O. A VM takes a card exclusively, through PCI
    passthrough, so it is blocked by any holder and blocks everyone in turn; two
    or more containers share a card by time-slicing, which is normal operation
    and not an error.

    Parameters:
        requested (set): PCI addresses the starting instance wants.
        vm_holders (dict): {PCI address: [(project, name), ...]} held by running VMs.
        container_holders (dict): the same for running containers.
        instance_type (str): 'vm' or 'container', the instance being started.

    Returns:
        tuple: (blocked, shared).
               blocked is a list of (PCI address, holder kind, holders) that
               forbid the start, holder kind being 'vm' or 'container'.
               shared is a list of (PCI address, holders) that the start will
               share with running containers.
    """
    blocked = []
    shared = []

    for pci_address in sorted(requested):
        vms = vm_holders.get(pci_address, [])
        containers = container_holders.get(pci_address, [])

        if vms:
            # The card is bound to vfio-pci for the VM: it is not there for anyone else.
            blocked.append((pci_address, 'vm', vms))
        elif containers and instance_type == 'vm':
            # Passing the card through would unbind the driver under a live container.
            blocked.append((pci_address, 'container', containers))
        elif containers:
            shared.append((pci_address, containers))

    return blocked, shared


def format_instance_list(holders, state=None):
    """Render a list of (project, instance name) couples for a message.

    'state' is appended to each entry when the state is part of the point being
    made -- a refusal has to say that the holder is running right now.
    """
    suffix = f", {state}" if state else ""
    return ", ".join(f"'{name}' (project {project}{suffix})" for project, name in holders)


def plural_gpus(count):
    """'1 GPU' / '2 GPUs', because a message that cannot count is not trusted."""
    return f"{count} GPU" if count == 1 else f"{count} GPUs"


def format_gpu_start_refusal(instance_name, scope, remote, instance_type, blocked,
                             requested_count, free_card_indexes, offer_size,
                             counterpart_offer_size):
    """Compose the message of a start refused because of GPU contention.

    Pure function: it receives facts and returns text. A refusal has to tell the
    administrator three things -- what is in the way, whether there is room
    elsewhere, and which commands reassign the instance -- otherwise the only
    available reaction is to try again, which cannot work.

    Parameters:
        instance_name (str): name of the instance that was to be started.
        scope (str): the instance in 'remote:project.instance' form, for the commands.
        remote (str): name of the remote.
        instance_type (str): 'vm' or 'container', the instance being started.
        blocked (list): the (PCI address, holder kind, holders) triples from
                        gpu_start_decision.
        requested_count (int): how many distinct cards the instance wants.
        free_card_indexes (list): indexes of the cards free for this instance type.
        offer_size (int): how many cards the remote offers to this instance type.
        counterpart_offer_size (int): how many it offers to the other type.

    Returns:
        str: the multi-line message.
    """
    regime = "VMs" if instance_type == 'vm' else "containers"
    other_regime = "containers" if instance_type == 'vm' else "VMs"
    profile_prefix = "gpu-vm-*" if instance_type == 'vm' else "gpu-cnt-*"

    reasons = []
    for pci_address, holder_kind, holders in blocked:
        if holder_kind == 'vm':
            reasons.append(
                f"GPU {pci_address} is held by VM "
                f"{format_instance_list(holders, state='RUNNING')}"
            )
        else:
            reasons.append(
                f"GPU {pci_address} is in use by running container(s) "
                f"{format_instance_list(holders)}"
            )
    lines = [f"Cannot start '{instance_name}': " + "; ".join(reasons) + "."]

    if offer_size == 0:
        supply = (
            f"No card on '{remote}' is offered to {regime}: no {profile_prefix} profile "
            f"exists there"
        )
        if counterpart_offer_size:
            supply += f", the {counterpart_offer_size} cards present are offered to {other_regime} only."
        else:
            supply += "."
        lines.append(supply)
    elif len(free_card_indexes) >= requested_count:
        lines.append(
            f"{plural_gpus(len(free_card_indexes))} free for {regime} on '{remote}' "
            f"(cards {', '.join(str(index) for index in free_card_indexes)}) -- enough for "
            f"this instance (needs {requested_count})."
        )
    else:
        lines.append(
            f"Only {plural_gpus(len(free_card_indexes))} free for {regime} on '{remote}' "
            f"(needs {requested_count}): stop or reassign other instances first."
        )

    if instance_type == 'vm' and any(kind == 'container' for _, kind, _ in blocked):
        lines.append(
            "Passing a card through to a VM would take it away from a running container: "
            "stop or reassign those containers, retrying will not help."
        )

    lines.append(f"To reassign:  figo gpu remove {scope} -a")
    lines.append(f"              figo gpu add {scope}")

    return "\n".join(lines)


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
        instance_type = instance.type # can be 'virtual-machine' or 'container'
        if instance_type == "virtual-machine":
            instance_type = "vm"
        else:
            instance_type = "container"

        # Which cards this instance wants, read from its expanded devices: whatever
        # put the device there -- a canonical profile, any other profile, or a
        # device attached directly -- the instance will find that card in front of
        # it. Deduplicated by PCI address: two profiles for the same card are one
        # card.
        requested_pci_addresses = gpu_devices_of(instance.expanded_devices)

        if requested_pci_addresses:
            vm_holders, container_holders = gpu_holders(remote)
            blocked, shared = gpu_start_decision(
                requested_pci_addresses, vm_holders, container_holders, instance_type
            )

            # All or nothing: an instance that cannot get one of its cards is not
            # started with the others, and every contended card is reported at once
            # so that the administrator sees the whole picture in one message.
            if blocked:
                offer = gpu_offer(remote, instance_type)
                counterpart_offer = gpu_offer(
                    remote, 'container' if instance_type == 'vm' else 'vm'
                )
                # A card is free for a VM when nobody is running on it; for a
                # container, when no VM holds it -- other containers may share.
                free_card_indexes = sorted(
                    index for index, pci_address in offer.items()
                    if not vm_holders.get(pci_address)
                    and (instance_type == 'container' or not container_holders.get(pci_address))
                )
                logger.error(format_gpu_start_refusal(
                    instance_name, f"{remote}:{project}.{instance_name}", remote,
                    instance_type, blocked, len(requested_pci_addresses),
                    free_card_indexes, len(offer), len(counterpart_offer),
                ))
                return False

            for pci_address, containers in shared:
                logger.info(
                    f"GPU {pci_address} shared with {len(containers)} running "
                    f"container(s): {format_instance_list(containers)}."
                )

            # Physical existence is a warning, never a block. The remote may be
            # unreachable over ssh or missing from REMOTE_TO_IP_INFO_MAP (every L1
            # host, today), and refusing to start because we could not verify the
            # hardware is worse than starting and letting Incus give the verdict.
            visible_pci_addresses = get_pci_addresses(remote)
            if visible_pci_addresses is not None:
                for pci_address in sorted(requested_pci_addresses - set(visible_pci_addresses)):
                    logger.warning(
                        f"GPU {pci_address} requested by '{instance_name}' is not visible "
                        f"on remote '{remote}'."
                    )

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


def set_user_key(instance_name, remote, project, key_filename, login=DEFAULT_LOGIN_FOR_INSTANCES, folder='.users', force=False):
    f"""
    Set a public key in the specified instance in the authorized_keys file of the specified user.

    Args:
        instance_name: Name of the instance.
        remote: Remote server name.
        project: Project name.
        key_filename: Filename of the public key on the host (to be combined with folder).
        login: Login name of the user (default: {DEFAULT_LOGIN_FOR_INSTANCES}) for which we set the key.
        folder: Folder path where the key file is located (default: '.users').
        force: If True, start the instance if it's not running and stop it after setting the key.

    Returns:
        True if the key was set successfully, False otherwise.
    """

    def check_to_stop(instance, force, was_started):
        if force and was_started:
            stop_instance(instance.name, remote, project)

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

        was_started = False

        # Check if the instance is running
        if instance.status.lower() != "running":
            if force:
                was_started = start_instance(instance.name, remote, project)
                if not was_started:
                    logger.error(f"Error: Instance '{instance_name}' failed to start.")
                    return False
            else:
                logger.error(f"Error: Instance '{instance_name}' is not running.")
                return False

        # Check if the key already exists in authorized_keys
        exit_code, stdout, _ = exec_command(instance, ['cat', f'/home/{login}/.ssh/authorized_keys'])
        if exit_code == 0:
            existing_keys = stdout.splitlines()
            if public_key in existing_keys:
                logger.info(f"Public key from '{key_filepath}' is already present in /home/{login}/.ssh/authorized_keys.")
                check_to_stop(instance, force, was_started)
                return True
        else:
            logger.info(f"No authorized_keys file found for {login}, proceeding with adding the key.")

        # Create .ssh directory
        exit_code, _, _ = exec_command(instance, ['mkdir', '-p', f'/home/{login}/.ssh'])
        if exit_code != 0:
            check_to_stop(instance, force, was_started)
            return False

        # Create authorized_keys file if not present
        exit_code, _, _ = exec_command(instance, ['touch', f'/home/{login}/.ssh/authorized_keys'])
        if exit_code != 0:
            check_to_stop(instance, force, was_started)
            return False

        # Set permissions
        exit_code, _, _ = exec_command(instance, ['chmod', '600', f'/home/{login}/.ssh/authorized_keys'])
        if exit_code != 0:
            check_to_stop(instance, force, was_started)
            return False

        exit_code, _, _ = exec_command(instance, ['chown', f'{login}:{login}', f'/home/{login}/.ssh/authorized_keys'])
        if exit_code != 0:
            check_to_stop(instance, force, was_started)
            return False

        # Add the public key to authorized_keys
        exit_code, _, _ = exec_command(
            instance, ['sh', '-c', f'echo "{public_key}" >> /home/{login}/.ssh/authorized_keys']
        )
        if exit_code != 0:
            check_to_stop(instance, force, was_started)
            return False

        logger.info(f"Public key from '{key_filepath}' added to /home/{login}/.ssh/authorized_keys in instance '{instance_name}'.")

        check_to_stop(instance, force, was_started)

        return True


    except FileNotFoundError:
        logger.error(f"File '{key_filepath}' not found.")
        return False
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to set user key for instance '{instance_name}': {e}")
        return False
    except Exception as e:
        logger.error(f"An error occurred while setting user key: {e}")
        return False

def get_instance_keys(instance_name, remote, project, login=DEFAULT_LOGIN_FOR_INSTANCES, force=False, full=False, extend=False):
    f"""
    Fetch and display the keys associated with a specific instance and user login.

    Args:
        instance_name: Name of the instance.
        remote: Remote server name.
        project: Project name.
        login: Login name of the user (default: {DEFAULT_LOGIN_FOR_INSTANCES}).
        force: If True, start the instance if it is not running and stop it after fetching keys.
        full: If True, include the full key as an additional column.
        extend: If True, adapt the output column width to the content.

    Returns:
        None: Outputs the keys information directly to the CLI.
    """
    try:
        # Get the specified instance in the project and remote
        remote_client = get_remote_client(remote, project_name=project)
        if not remote_client:
            logger.error(f"Failed to connect to remote '{remote}' and project '{project}'.")
            return

        instance = remote_client.instances.get(instance_name)

        was_started = False

        # Check if the instance is running
        if instance.status.lower() != "running":
            if force:
                was_started = start_instance(instance.name, remote, project)
                if not was_started:
                    logger.error(f"Error: Instance '{instance_name}' failed to start.")
                    return
            else:
                logger.error(f"Error: Instance '{instance_name}' is not running.")
                return

        # Fetch the contents of the authorized_keys file
        exit_code, stdout, _ = exec_command(instance, ['cat', f'/home/{login}/.ssh/authorized_keys'])
        if exit_code != 0:
            logger.info(f"No authorized_keys file found for user '{login}' in instance '{instance_name}'.")
            return

        # Define columns for output
        if full:
            COLS = [('KEY TYPE', 12), ('KEY ID', 30), ('KEY', 70)]
        else:
            COLS = [('KEY TYPE', 12), ('KEY ID', 30)]

        add_header_line_to_output(COLS)

        keys = []
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                key_type, key_id = parts[0], parts[2]
                key = parts[1] if full and len(parts) > 1 else None
                keys.append((key_type, key_id, key))

        if keys:
            for key_data in keys:
                row = list(key_data) if full else key_data[:2]
                add_row_to_output(COLS, row)
        else:
            logger.info(f"No valid keys found in authorized_keys for user '{login}' in instance '{instance_name}'.")

        flush_output(extend=extend)

        if force and was_started:
            stop_instance(instance.name, remote, project)

    except Exception as e:
        logger.error(f"An error occurred while retrieving keys for instance '{instance_name}': {e}")


def assign_ip_address(remote, mode="next"):
    """Assign a new IP address based on the highest assigned IP address or the first available hole.
    
    Used by the 'set_ip' and by the 'get_ip_and_gw' functions

    mode: "next" assigns the next available IP address,
            "hole" assigns the first available hole starting from a base IP address
            as specified in the REMOTE_TO_IP_INFO_MAP.

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

        for instance_state_dict in iterator_over_instance_dicts(remote, project["name"]):
            ip_addresses = get_ip_addresses(instance_state_dict)
            assigned_ips.extend(ip_addresses)
            # add the additional IP addresses held by the instance, if any
            # (addresses of nested QEMU VMs, inner containers, extra addresses on its own NIC)
            assigned_ips.extend(
                [entry['ip'] for entry in
                 get_additional_ips_from_config(instance_state_dict.get("config"))])
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

def set_ip(instance_name, remote, project, ip_address_and_prefix_len=None, gw_address=None,
           nic_device_name=None, hole=False):
    """Set a static IP address and gateway for a stopped instance.

    Args: 
    - instance_name: Name of the instance.
    - remote: Remote server name.
    - project: Project name.
    - ip_address_and_prefix_len: IP address and prefix length. If None, the address is assigned automatically.
    - gw_address: Gateway address. If None, the default gateway for the remote is used.
    - nic_device_name: NIC device name. If None, the default NIC device name is used.
    - hole: If True, assign the first available hole starting from the base IP address.
    
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
        my_mode = "hole" if hole else "next"
        ip_address = assign_ip_address(remap_remote, mode=my_mode)
        prefix_length = get_prefix_len(remap_remote)

    if ip_address is None or prefix_length is None:
        logger.error(f"Error: Failed to assign IP address for instance '{instance_name}'.")
        return False

    if gw_address :
        if not is_valid_ip(gw_address):
            logger.error(f"Error: gw address '{gw_address}' is not a valid IP address.")
            return False
    else:
        gw_address = get_gw_address(remap_remote)

    if gw_address is None:
        logger.error(f"Error: Gateway address not found for remote '{remap_remote}'. "+
                     f"Remapped from '{remote}'" if remap_remote != remote else "")
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

def get_ip_and_gw(ip_address_and_prefix_len, gw_address, remote, mode="next"):
    """
    Determine the IP address and gateway for an instance based on inputs and defaults.

    Args:
    - ip_address_and_prefix_len: A string containing the IP address and prefix length (e.g., "192.168.1.10/24").
    - gw_address: The gateway address, if provided.
    - remote: The remote from which the IP address and gateway are to be assigned.
    - mode: The mode for assigning the IP address (can be "next" or "hole").

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

        ip_address = assign_ip_address(remap_remote, mode=mode)
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

def add_user_data_config_info(config, login_pubkey_filename, ssh_prikey_filename, login, sshfs_user_name):
    """
    Adds 'user.user-data' to the config as valid cloud-init YAML.
    """
    try:

        public_key_content = None
        if login_pubkey_filename:
            if not os.path.isfile(login_pubkey_filename):
                raise FileNotFoundError(f"Login public key file '{login_pubkey_filename}' does not exist.")
            with open(login_pubkey_filename, "r") as key_file:
                public_key_content = key_file.read().strip()

        ssh_private_key_content = None
        if ssh_prikey_filename:
            if not os.path.isfile(ssh_prikey_filename):
                raise FileNotFoundError(f"SSH private key file '{ssh_prikey_filename}' does not exist.")
            with open(ssh_prikey_filename, "r") as prikey_file:
                ssh_private_key_content = prikey_file.read().rstrip("\n")

        # --- build cloud-init structure ---
        user_entry = {
            "name": login,
            "shell": "/bin/bash",
            "lock_passwd": True,
            "gecos": "Ubuntu",
            "groups": ["adm", "audio", "cdrom", "dialout", "dip", "floppy", "lxd", "netdev",
                       "plugdev", "sudo", "video"],
            "sudo": ['ALL=(ALL) NOPASSWD:ALL'],
        }
        if public_key_content:
            user_entry["ssh-authorized-keys"] = [public_key_content]

        cloud_cfg = {
            "users": [user_entry],
        }

        # Only add sshfs-related parts if ssh_prikey_filename is provided
        if ssh_private_key_content:
            cloud_cfg["packages"] = ["sshfs"]

            # runcmd supports both strings and lists; we use strings for readability.
            cloud_cfg["runcmd"] = [
                'echo "10.202.9.201 file-server" >> /etc/hosts',
                'echo "10.202.9.201 file-server" >> /etc/cloud/templates/hosts.debian.tmpl',
                f"mkdir -p /home/{login}/.ssh",
                # heredoc block
                "\n".join([
                    f"cat <<'EOF' > /home/{login}/.ssh/id_ed25519",
                    ssh_private_key_content,
                    "EOF",
                ]),
                f"chmod 600 /home/{login}/.ssh/id_ed25519",
                f"chown -R {login}:{login} /home/{login}/.ssh",
                f"mkdir -p /home/{login}/mnt",
                f"chown {login}:{login} /home/{login}/mnt",
                # mount unit creation block
                "\n".join([
                    f"U_UID=$(id -u {login})",
                    f"U_GID=$(id -g {login})",
                    f'UNIT_FILE="/etc/systemd/system/home-{login}-mnt.mount"',
                    'cat <<EOF > "$UNIT_FILE"',
                    "[Unit]",
                    "Description=SSHFS Mount (Cloud-Init Auto)",
                    "Requires=network-online.target",
                    "After=network-online.target",
                    "",
                    "[Mount]",
                    f"What={sshfs_user_name}@file-server:/data",
                    f"Where=/home/{login}/mnt",
                    "Type=fuse.sshfs",
                    "",
                    "Options=_netdev,allow_other,default_permissions,reconnect,cache=yes,kernel_cache,"
                    "Compression=no,max_conns=4,ServerAliveInterval=15,ServerAliveCountMax=3,"
                    "StrictHostKeyChecking=no,Ciphers=aes128-gcm@openssh.com,entry_timeout=60,"
                    "attr_timeout=60,IdentityFile=/home/{login}/.ssh/id_ed25519,uid=$U_UID,gid=$U_GID"
                    .replace("{login}", login),
                    "",
                    "[Install]",
                    "WantedBy=multi-user.target",
                    "EOF",
                ]),
                "systemctl daemon-reload",
                f"systemctl enable --now home-{login}-mnt.mount",
            ]

        # --- dump as valid cloud-init YAML ---
        user_data_yaml = "#cloud-config\n" + yaml.safe_dump(
            cloud_cfg,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
        )

        config["config"]["user.user-data"] = user_data_yaml
        logger.info(f"Added user.user-data to the config for user '{login}'.")

    except Exception as e:
        raise Exception(f"Failed to add user.user-data to config: {e}")

    return config


def add_authorized_keys_to_config_old(config, key_filename, login):
    """
    Adds 'user.user-data' to the config if key_filename is provided.

    Note that adding user-data to the config will overwrite any existing user-data.
    For this reason, this function also sets other fields in the user configuration
    in addition to the public key, namely the shell, lock_passwd, gecos, groups, and sudo fields.
    These fields are set to default values for an Ubuntu user and normally they are
    taken from the cloud-init file: /etc/cloud/cloud.cfg

    Args:
        config (dict): The configuration dictionary for instance creation.
        key_filename (str): Path to the public key file.
        login (str): The username to associate the public key with.
    
    Returns:
        dict: Updated configuration.
    """
    if key_filename:
        try:
            # Verify that the key file exists
            if not os.path.isfile(key_filename):
                raise FileNotFoundError(f"Key file '{key_filename}' does not exist.")
            
            # Read the public key content
            with open(key_filename, 'r') as key_file:
                public_key_content = key_file.read().strip()
            
            # Add user-data to the config
            config['config']['user.user-data'] = f"""
            #cloud-config
            users:
              - name: {login}
                ssh-authorized-keys:
                  - {public_key_content}
                shell: /bin/bash
                lock_passwd: True
                gecos: Ubuntu
                groups: [adm, audio, cdrom, dialout, dip, floppy, lxd, netdev, plugdev, sudo, video]
                sudo: ["ALL=(ALL) NOPASSWD:ALL"]
            """
            logger.info(f"Added public key content from '{key_filename}' to the config for user '{login}'.")
        except Exception as e:
            raise ValueError(f"Failed to add public key to config: {e}")
    
    return config


def create_instance(instance_name, image, remote_name, project, instance_type, 
                    ip_address_and_prefix_len=None, gw_address=None, nic_device_name=None,
                    profiles=[], create_project_flag=False, hole=False,
                    login_pubkey_filename=None, sshfs_prikey_filename=None,
                    folder = USER_DIR, login=DEFAULT_LOGIN_FOR_INSTANCES,
                    sshfs_user_name=None):
    """Create a new instance from a local or remote image with specified configurations.

    It assigns a static IP address and gateway to the instance.

    Args:
    - instance_name: Name of the instance.
    - image: Image source. If it starts with 'local:', it uses a local image; otherwise, it defaults to 'remote:image'.
    - remote_name: Remote server name.
    - project: Project name.
    - instance_type: Type of the instance (can be 'vm' or 'container').
    - ip_address: Static IP address for the instance.
    - gw_address: Gateway address for the instance.
    - nic_device_name: Optional NIC device name for the instance.
    - instance_size: Optional size profile for the instance.
    - create_project_flag: If True, create the project if it does not exist.
    - hole: If True, assign the first available hole starting from the base IP address 
      otherwise assign the next IP address after the highest assigned.
    - login_pubkey_filename: Filename of the public key to set in the instance, None if no public key is to be set.
    - sshfs_prikey_filename: Filename of the private key to set for SSHFS mounting, None if no private key is to be set.
    - folder: Folder path where the key file is located (default: USER_DIR).
    - login: Login name of the user for which the key is set (default: 'ubuntu').

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
            alias_or_fingerprint = image.split(':')[1]
            logger.info(f"Creating instance '{instance_name}' from local image '{alias_or_fingerprint}'.")

            image_found = False
            # Retrieve the local image by alias
            try:
                image = remote_client.images.get_by_alias(alias_or_fingerprint)
                logger.info(f"Found local image with alias '{alias_or_fingerprint}', with fingerprint '{image.fingerprint}'.")
                image_found = True
            except pylxd.exceptions.LXDAPIException:
                pass
            
            if not image_found:
                try:
                    # Retrieve the local image by fingerprint
                    image = remote_client.images.get(alias_or_fingerprint)
                    logger.info(f"Found local image with fingerprint '{alias_or_fingerprint}'.")
                    image_found = True

                except pylxd.exceptions.LXDAPIException:
                    pass
            
            if not image_found:
                logger.error(f"Local image '{alias_or_fingerprint}' not found.")
                return False

            # Use the fingerprint instead of the alias
            config_source = {
                'type': 'image',
                'fingerprint': image.fingerprint  # Use the fingerprint of the local image
            }

        else:
            # Remote image (format: remote:image)
            image_server, alias_or_fingerprint = image.split(':')
            logger.info(f"Creating instance '{instance_name}' from remote image '{alias_or_fingerprint}' on server '{image_server}'.")

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
                'alias': alias_or_fingerprint
            }

        if not nic_device_name:
            device_name = DEFAULT_VM_NIC if instance_type == "vm" else DEFAULT_CNT_NIC
        else:
            device_name = nic_device_name  # Use the specified NIC device name
        
        my_mode = "hole" if hole else "next"
        try:
            ip_address_and_prefix_len, gw_address = get_ip_and_gw(ip_address_and_prefix_len, 
                                                                  gw_address, remote_name, mode=my_mode)
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

        # Add the public key to the configuration
        login_pubkey_filepath = None
        if login_pubkey_filename:
            # create the file path
            login_pubkey_filepath = os.path.join(folder, login_pubkey_filename)

        # Add the SSHFS private key to the configuration
        sshfs_prikey_filepath = None
        if sshfs_prikey_filename:
            # create the file path
            sshfs_prikey_filepath = os.path.join(folder, sshfs_prikey_filename)
       
        config = add_user_data_config_info(config, login_pubkey_filepath, 
                                            sshfs_prikey_filepath, login, sshfs_user_name)

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

    Args:
    - instance_name: Name of the instance.
    - remote: Remote server name.
    - project: Project name.
    - force: If True, stop the instance if it is running before deleting it.
    
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

def show_gpu_status(remote, extend=False, instances=False):
    """Show the GPUs of a remote, one row per card.

    Section 5.3. The single row of aggregate counters it replaces could not be
    right: it counted profiles instead of cards, so a card shared by two
    containers counted twice, and it said nothing about *which* card was free,
    nor to whom -- a card offered only to containers is not available to a VM,
    however free it is.

    The three sources are merged by build_gpu_status_rows: the offer (profiles),
    the physical inventory (lspci) and the usage (expanded devices of the
    instances, all projects, every state). When the inventory cannot be read the
    table is still built from the other two, with a note saying what is missing:
    an L1 host, where discovery does not work yet, must still show its cards.

    Args:
    - remote: The remote server name.
    - extend: If True, adapt the output column width to the content.
    - instances: If True, list the instances of each card under the table.
    """
    discovery = gpu_inventory(remote)
    report_gpu_discovery(discovery)

    inventory_pci_addresses = (
        discovery.pci_addresses
        if discovery.outcome in (GPU_DISCOVERY_OK, GPU_DISCOVERY_NO_GPU)
        else None
    )

    offer_details = gpu_offer_details(remote)
    usage = gpu_usage_by_card(remote)

    rows, notes = build_gpu_status_rows(offer_details, inventory_pci_addresses, usage)

    COLS = [('CARD', 5), ('PCI', 9), ('CNT-PROFILE', 17), ('VM-PROFILE', 17),
            ('RUNNING', 8), ('ASSIGNED', 9), ('HELD BY', 38), ('NOTE', 14)]
    add_header_line_to_output(COLS)
    for row in rows:
        add_row_to_output(COLS, [
            str(row.card_index) if row.card_index is not None else "-",
            row.pci,
            row.cnt_profile,
            row.vm_profile,
            str(row.running),
            str(row.assigned),
            row.held_by,
            row.note,
        ])
    flush_output(extend=extend)

    if not rows:
        logger.info(f"No GPU is offered, present or in use on remote '{remote}'.")

    if instances:
        print()
        for row in rows:
            print(format_gpu_card_instances(row, usage))

    if inventory_pci_addresses is None:
        logger.warning(
            f"Physical inventory unavailable on remote '{remote}': the table shows the "
            f"cards known from profiles and instances, and a card present but neither "
            f"offered nor in use cannot appear."
        )

    for note in notes:
        logger.warning(note)


def list_gpu_profiles(client, extend=False):
    """List all GPU profiles on the remote node implicitly associated with the client.
    
    Args:
    - client: The client object associated with the remote node.
    - extend: If True, adapt the output column width to the content.
    """
    gpu_profiles = [
        profile.name for profile in client.profiles.all() if profile.name.startswith("gpu-")
    ]
    COLS = [('TOTAL', 10), ('PROFILES', 30)]
    add_header_line_to_output(COLS)
    add_row_to_output(COLS, [str(len(gpu_profiles)), ", ".join(gpu_profiles)])
    flush_output(extend=extend)

def add_gpu_profile(instance_name, remote='local', project='default'):
    """
    Add a GPU profile to a specified instance within an optional remote and project scope.

    This function checks if the given instance exists within the specified project and 
    remote, ensures that the instance is in a stopped state, and then adds an available 
    GPU profile to it if possible.

    Args:
        instance_name (str): The name of the instance to which the GPU profile will be added.
        remote (str, optional): The remote server where the instance is located. Defaults to 'local'.
        project (str, optional): The project under which the instance resides. Defaults to 'default'.

    Returns:
        bool: True if the GPU profile was added successfully, False otherwise.
    """
    try:
        full_instance_name = f"{remote}:{project}.{instance_name}" 
        logger.info(f"Adding GPU profile to instance '{full_instance_name}'...")

        # Get the client for the remote and project
        client = get_remote_client(remote, project_name=project)

        # Fetch the instance
        instance = client.instances.get(instance_name)

        if instance.status.lower() != "stopped":
            logger.error(f"Instance '{full_instance_name}' is running or in error state.")
            return False

        instance_profiles = instance.profiles
        
        # we list the profiles of the instance and we keep only the gpu profiles
        gpu_profiles_for_instance = [
            profile for profile in instance_profiles if profile.startswith("gpu-")
        ]
        
        available_pci_addresses = get_pci_addresses(remote)
        if available_pci_addresses is None:
            logger.error(f"Failed to retrieve available PCI addresses from remote '{remote}'.")
            return False
        
        total_gpus = len(available_pci_addresses)

        if len(gpu_profiles_for_instance) >= total_gpus:
            logger.error(f"Instance '{full_instance_name}' already has the maximum number of GPU profiles.")
            return False

        if instance.type == "virtual-machine":
            start_prefix = "gpu-vm-"
        else:
            start_prefix = "gpu-cnt-"
            
        all_profiles = get_all_profiles(client)
        # we take all GPU profiles on the remote for the specific instance type
        # we keep only the gpu profiles that are not already assigned to the instance
        available_gpu_profiles = [
            profile for profile in all_profiles if profile.startswith(start_prefix)
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

def remove_gpu_all_profiles(instance_name, remote='local', project='default'):
    """Remove all GPU profiles from an instance.
    
    Returns: True if the GPU profiles were removed successfully, False otherwise.
    """

    try:
        full_instance_name = f"{remote}:{project}.{instance_name}" 
        logger.info(f"Removing all GPU profiles from instance '{full_instance_name}'...")

        # Get the client for the remote and project
        client = get_remote_client(remote, project_name=project)

        # Fetch the instance
        instance = client.instances.get(instance_name)

        if instance.status.lower() != "stopped":
            logger.error(f"Instance '{instance_name}' is running or in error state.")
            return False

        instance_profiles = instance.profiles
        gpu_profiles_for_instance = [
            profile for profile in instance_profiles if profile.startswith("gpu-")
        ]

        if not gpu_profiles_for_instance:
            logger.error(f"Instance '{instance_name}' has no GPU profiles to remove.")
            return False

        for gpu_profile in gpu_profiles_for_instance:
            instance_profiles.remove(gpu_profile)

        instance.profiles = instance_profiles
        instance.save(wait=True)

        logger.info(f"Removed all GPU profiles from instance '{instance_name}'.")

        return True
    
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(
            f"Failed to remove GPU profiles from instance '{instance_name}': {e}"
        )
        return False

def remove_gpu_profile(instance_name, remote='local', project='default'):
    """Remove a GPU profile from an instance.
    
    Args:
    - instance_name: The name of the instance from which to remove the GPU profile.
    - remote: The remote server name.
    - project: The project name.

    Returns: True if the GPU profile was removed successfully, False otherwise.
    """
    try:
        full_instance_name = f"{remote}:{project}.{instance_name}"
        logger.info(f"Removing GPU profile from instance '{full_instance_name}'...")

        # Get the client for the remote and project
        client = get_remote_client(remote, project_name=project)

        if not client:
            logger.error(f"Failed to connect to remote '{remote}' and project '{project}'.")
            return False

        instance = client.instances.get(instance_name)
        if instance.status.lower() != "stopped":
            logger.error(f"Instance '{instance_name}' is running or in error state.")
            return False

        instance_profiles = instance.profiles
        gpu_profiles_for_instance = [
            profile for profile in instance_profiles if profile.startswith("gpu-")
        ]

        if not gpu_profiles_for_instance:
            logger.error(f"Instance '{instance_name}' has no GPU profiles to remove.")
            return False

        profile_to_remove = gpu_profiles_for_instance[0]
        instance_profiles.remove(profile_to_remove)
        instance.profiles = instance_profiles
        instance.save(wait=True)

        logger.info(f"Removed GPU profile '{profile_to_remove}' from instance '{instance_name}'.")

        return True
    
    except pylxd.exceptions.LXDAPIException as e:
        logger.error(f"Failed to remove GPU profile from instance '{instance_name}': {e}")
        return False

def show_gpu_pci_addresses(remote='local'):
    """Print the PCI addresses of the NVIDIA cards physically present on a remote.

    Section 7 applies here as well: a host with no card answered the question and
    returns True, while unreachable, not configured and failed are reported for
    what they are. The previous version printed the raw Python list -- 'None'
    included -- which said nothing about which of the four had happened.

    Returns:    True if the inventory could be read, False otherwise.
    """
    discovery = gpu_inventory(remote)
    report_gpu_discovery(discovery)

    if discovery.outcome == GPU_DISCOVERY_OK:
        logger.info(
            f"GPUs on remote '{remote}': {', '.join(discovery.pci_addresses)}"
        )
        return True

    if discovery.outcome == GPU_DISCOVERY_NO_GPU:
        logger.info(discovery.detail)
        return True

    return False


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
        logger.info(yaml.dump(profile_data, default_flow_style=False))
    except pylxd.exceptions.NotFound:
        logger.error(f"Profile '{profile_name}' not found in project '{project}' on remote '{remote}'.")
        return False
    except Exception as e:
        logger.error(f"Failed to retrieve profile '{profile_name}': {e}")
        return False
    
    return True

# dictionary to store the instances associated with each profile
profiles_instances_dict = {}


def list_profiles_specific(remote, project, profile_name=None, COLS=None, remote_client=None,
                           recurse_instances=False):
    """List all profiles on a specific remote and project optionally with a match on profile_name
    
    For each profile, list the associated instances.

    Args:
    - remote (str): The name of the remote.
    - project (str): The name of the project.
    - profile_name (str, optional): The name of the profile to match.
    - COLS (list, optional): The columns to display.
    - remote_client (pylxd.Client, optional): An existing pylxd client for the remote.
        If provided, it will be used instead of creating a new client.
    - recurse_instances (bool, optional): If True, list the instances associated with inherited profiles.
    
    Returns:    False if fetching the profiles failed, True otherwise.
    """
    global profiles_instances_dict

    client = remote_client if remote_client else get_remote_client(remote, project_name=project)
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
        
        if not recurse_instances:
            instances = client.instances.all()
            associated_instances = [
                instance.name for instance in instances
                if profile.name in instance.profiles
            ]
            associated_instances_str = ', '.join(associated_instances) if associated_instances else 'None'
        else:
            associated_instances = profiles_instances_dict.get((remote, profile.name), [])
            associated_instances_str = ', '.join([f"{project}:{instance}" for project, instance in associated_instances]) if associated_instances else 'None'

        context = f"{remote}:{project}" 
        add_row_to_output(COLS, [profile.name, context, associated_instances_str])

    return True

def check_profiles_feature(remote, project, remote_client=None):
    """
    Check if the 'features.profiles' value is True for the specified project on the remote.
    If True, profiles are managed within the project; 
    If False, profiles are inherited from the default project.

    Args:
    - remote (str): The name of the remote.
    - project (str): The name of the project.
    - remote_client (pylxd.Client, optional): An existing pylxd client for the remote. 
      If provided, it will be used instead of creating a new client.

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

def list_profiles(remote, project, profile_name=None, inherited=False, extend=False, recurse_instances=False):
    """
    List profiles overall or on specific remote and project optionally with a match on profile_name.

    - If remote and project are not specified, list all profiles on all remotes and projects.
    - If remote is specified but project is not, list all profiles on the remote.
    - If project is specified but remote is not, list all profiles on the project on all remotes.
    - If remote and project are specified, list all profiles on the remote and project.
    - If `inherited` is False, skip profiles from projects which inherit profiles from default.
    - extend: If True, adapts the output column width to the content.
    - recurse_instances: If True, list the instances associated with inherithed profiles.

    Returns:    False if fetching the profiles failed, True otherwise.
    """
    global profiles_instances_dict

    COLS = [('PROFILE', 25), ('CONTEXT', 25), ('INSTANCES', 80)]
    add_header_line_to_output(COLS)

    if recurse_instances:
        # reset the dictionary to store the instances associated with each profile
        profiles_instances_dict = {}
        # the key of the profiles_instances_dict is a tuple (remote, profile_name)
        # the value is a list of tuple (project, instance) associated with the profile        

        # for each remote
        for my_remote in get_incus_remotes():
            # check to skip all the remote nodes of type images
            if get_incus_remotes()[my_remote]["Protocol"] == "simplestreams":
                continue
            # for each project
            for my_project in iterator_over_projects(my_remote):
                remote_client = wrap_get_remote_client(my_remote, project_name=my_project['name'], 
                                                       raise_project_not_found=True, show_info=False)
                if not remote_client:
                    logger.error(f"Failed to retrieve client for '{my_remote}:{my_project['name']}'.")
                    return False
                # get all the instances in the project
                instances = remote_client.instances.all()
                for instance in instances:
                    # get the profiles of the instance
                    instance_profiles = instance.profiles
                    # for each profile in the instance_profiles
                    for profile in instance_profiles:
                        # add the instance to the list of instances associated with the profile
                        if (my_remote, profile) not in profiles_instances_dict:
                            profiles_instances_dict[(my_remote, profile)] = []
                        profiles_instances_dict[(my_remote, profile)].append((my_project["name"], instance.name))

    if remote:
        # check if remote exists in the incus remotes
        if remote not in get_incus_remotes():
            logger.error(f"Remote '{remote}' not found.")
            return False
        # check if the remote is reachable
        test_projects = get_projects(remote, timeout=4)
        if not test_projects:
            logger.error(f"Remote '{remote}' is not reachable.")
            return False

    # use a set to store the remote nodes that failed to retrieve the projects
    set_of_errored_remotes = set()

    if remote and project:
        remote_client = wrap_get_remote_client(remote, project_name=project, 
                                               raise_project_not_found=True, show_info=False)
        if not remote_client:
            logger.error(f"Failed to retrieve client for '{remote}:{project}'.")
            return False

        profiles_managed_separately_for_project = check_profiles_feature(remote, project,
                                                                         remote_client=remote_client)
        if profiles_managed_separately_for_project is None:
            logger.error(f"Failed to check the 'features.profiles' value for '{remote}:{project}'.")
            return False  # Error occurred while checking the target project
        if not inherited and not profiles_managed_separately_for_project:
            return False  # Skip profiles from projects where `features.profiles` is False
        list_profiles_specific(remote, project, profile_name, COLS, remote_client=remote_client,
                               recurse_instances=recurse_instances)

    elif remote:  # list all profiles on the remote as project is not specified

        for project in iterator_over_projects(remote):
            remote_client = wrap_get_remote_client(remote, project_name=project["name"], 
                                                   raise_project_not_found=True, show_info=False)
            if not remote_client:
                logger.error(f"Failed to retrieve client for '{remote}:{project}'.")
                return False
            profiles_managed_separately_for_project = check_profiles_feature(remote, project["name"], 
                                                                             remote_client=remote_client)
            if profiles_managed_separately_for_project is None:
                logger.error(f"Failed to check the 'features.profiles' value for '{remote}:{project}'.")
                return False  # Error occurred while checking the target project            
            if not inherited and not profiles_managed_separately_for_project:
                continue
            list_profiles_specific(remote, project["name"], profile_name, COLS, remote_client=remote_client,
                                   recurse_instances=recurse_instances)

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
                list_profiles_specific(my_remote_node, project, profile_name, COLS, remote_client=remote_client,
                                       recurse_instances=recurse_instances)
            else: # all the projects
                all_projects = get_projects(my_remote_node, timeout=4)
                if not all_projects:
                    set_of_errored_remotes.add(my_remote_node)
                    continue

                for my_project in all_projects:
                    remote_client = wrap_get_remote_client(my_remote_node, project_name=my_project["name"], 
                                                           raise_project_not_found=True, show_info=False)
                    if not remote_client:
                        logger.error(f"Failed to retrieve client for '{my_remote_node}:{project}'.")
                        return False
                    profiles_managed_separately_for_project = check_profiles_feature(my_remote_node, my_project["name"],
                                                                                     remote_client=remote_client)
                    if profiles_managed_separately_for_project is None:
                        logger.error(f"Failed to check the 'features.profiles' value for '{remote}:{project}'.")
                        return False  # Error occurred while checking the target project                              
                    if not inherited and not profiles_managed_separately_for_project:
                        continue
                    list_profiles_specific(my_remote_node, my_project["name"], profile_name, COLS,
                                           remote_client=remote_client, recurse_instances=recurse_instances)
    
    flush_output(extend=extend)
    if set_of_errored_remotes:
        logger.error(f"Error: Failed connection to remote(s): {', '.join(set_of_errored_remotes)}")

def import_profile(remote, project, profile_name, yaml_file, overwrite=False):
    """
    Import a profile from a YAML file into the specified remote/project.

    This is a wrapper around:
      incus profile create <profile>
      cat <yaml_file> | incus profile edit <profile>

    Args:
        remote (str): incus remote (or None)
        project (str): incus project (or None)
        profile_name (str): profile name
        yaml_file (str): path to YAML file
        overwrite (bool): if True, skip profile creation
    """

    if not os.path.isfile(yaml_file):
        logger.error(f"YAML file not found: {yaml_file}")
        return False

    # Incus scoping:
    # - Remote is expressed as "<remote>:<profile>" (except "local")
    # - Project is expressed via "--project <project>"
    incus_project_args = []
    if project:
        incus_project_args = ["--project", project]

    if remote and remote != "local":
        scoped_profile = f"{remote}:{profile_name}"
    else:
        scoped_profile = profile_name

    if not overwrite:
        cmd_create = ["incus"] + incus_project_args + ["profile", "create", scoped_profile]

        logger.debug("Running: %s", " ".join(cmd_create))
        result = subprocess.run(
            cmd_create,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            # If profile already exists, continue
            if "already exists" not in result.stderr.lower():
                logger.error(result.stderr.strip())
                return False

    cmd_edit = ["incus"] + incus_project_args + ["profile", "edit", scoped_profile]

    logger.debug("Running: %s < %s", " ".join(cmd_edit), yaml_file)

    with open(yaml_file, "r") as f:
        result = subprocess.run(
            cmd_edit,
            stdin=f,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

    if result.returncode != 0:
        logger.error(result.stderr.strip())
        return False

    return True

def copy_profile(source_remote, source_project, source_profile, target_remote, target_project, target_profile):
    """Copy a profile from one location to another with error handling, including the description.

    Args:
    - source_remote (str): The source remote name.
    - source_project (str): The source project name.
    - source_profile (str): The source profile name.
    - target_remote (str): The target remote name.
    - target_project (str): The target project name.
    - target_profile (str): The target profile name.
    
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

def display_default_init_profiles():
    """Display the default profiles to be transferred during remote initialization."""
    global DEFAULT_PROFILES_TO_TRANSFER
    logger.info("Default profiles to be transferred during remote initialization:")
    for profile in DEFAULT_PROFILES_TO_TRANSFER:
        logger.info(f" - {profile}")


def initialize_remote_profiles(remote, profiles_to_transfer=None):
    """
    Initialize a remote by transferring profiles from local:default to remote:default.

    Parameters:
        remote (str): Name of the remote to initialize. Can be specified as 'my_remote' or 'my_remote:'.
        profiles_to_transfer (list, optional): List of profiles to transfer. If None, use the default hard-coded list.

    Returns:
        bool: True if initialization is successful, False otherwise.
    """
    # Use global default profiles if custom profiles are not provided
    global DEFAULT_PROFILES_TO_TRANSFER
    profiles_to_transfer = profiles_to_transfer or DEFAULT_PROFILES_TO_TRANSFER

    # Ensure remote name is valid
    remote = remote.rstrip(":")
    if not check_remote_name(remote):
        logger.error(f"Invalid remote name: {remote}")
        return False

    try:
        for profile_name in profiles_to_transfer:
            # Copy the profile from local to the specified remote
            logger.info(f"Transferring profile '{profile_name}' to remote '{remote}'...")
            success = copy_profile(
                source_remote="local",
                source_project="default",
                source_profile=profile_name,
                target_remote=remote,
                target_project="default",
                target_profile=profile_name
            )

            if success:
                logger.info(f"Profile '{profile_name}' successfully transferred to remote '{remote}'.")
            else:
                logger.warning(f"Failed to transfer profile '{profile_name}' to remote '{remote}'.")
    except Exception as e:
        logger.error(f"Error during remote profile initialization: {str(e)}")
        return False

    logger.info(f"Remote '{remote}' successfully initialized with profiles.")
    return True

#############################################
###### figo user command functions ##########
#############################################

def get_ip_address_of_user(username, fingerprint):
    """Get the IP address of a user based on the WireGuard configuration file.

    Args:
    - username (str): The username of the user.
    - fingerprint (str): The fingerprint of the user's certificate.

    Returns:
    - str: The IP address of the user or a string starting with "?" if it was not
      possibile to find IP address.
    """

    # Construct the path to the WireGuard configuration file
    file_path = os.path.join(os.path.expanduser(USER_DIR), f"{username}.conf")

    # Check if the file exists
    if not os.path.exists(file_path):
        return f"?no file {username}.conf"

    # Read the WireGuard configuration file
    with open(file_path, 'r') as file:
        for line in file:
            if line.startswith('Address ='):
                ip_address = line.split('=')[1].strip().split('/')[0]
                return ip_address

    return f"?no ip in {username}.conf"


def list_users(client, full=False, extend=False, ip=False):
    """List all users with optional full details (email, name, and org).
    
    Args:
    - client: The client object associated with the remote node.
    - full: If True, display full details (email, name, and org).
    - extend: If True, adapt the output column width to the content.
    - ip: If True, display the IP address of the user.
    """

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

        email = description_parts[0]
        real_name = description_parts[1]
        org = description_parts[2]
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
    COLS = [('NAME', 20), ('FINGERPRINT', 12)]
    if ip:
        COLS += [('VPN IP', 15)]
    if full:
        COLS += [('TYPE', 4), ('ADMIN', 5), ('EMAIL', 30), ('REAL NAME', 20),
                      ('ORGANIZATION', 15), ('PROJECTS', 20)]
        
    add_header_line_to_output(COLS)

    # Print sorted certificates
    for cert in certificates_info:
        output_row = [cert["name"], cert["fingerprint"]]
        if ip:
            user_ip = get_ip_address_of_user(cert["name"], cert["fingerprint"])
            output_row.append(user_ip if user_ip else "?")
        if full:
            output_row += [cert["type"], cert["admin"], cert["email"], cert["real_name"],
                           cert["org"], cert["projects"]]    
        add_row_to_output(COLS, output_row)

    flush_output(extend=extend)

def get_wg_client_ip_address(ip_next=False):
    """ Get an available IP address for a WireGuard client.
    
    Args: 
    - ip_next (bool, optional): If True, generate the next available IP address, otherwise
        use the first available hole in the IP address range. 
    
    Look for IP addresses assigned to WireGuard clients in the .conf files in the USER_DIR directory.
    If no IP addresses are found, start from BASE_IP_FOR_WG_VPN.

    Returns: 
    - str: The next available IP address for a WireGuard client
    - None if an error occurs

    """
    #TODO maybe this function could return None in same more cases
    #TODO maybe this function could return None if the maximum number of clients is reached

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
        # If no IP addresses are found, start from the base IP address
        return BASE_IP_FOR_WG_VPN
    
    # Convert IP addresses to ip_address objects and sort
    ip_addresses = sorted([ipaddress.ip_address(ip) for ip in ip_addresses])

    if ip_next:
        # Find the next available IP address
        last_ip = ip_addresses[-1]
        next_ip = last_ip + 1
    else:
        # Find the first available hole in the IP address range
        next_ip = None
        skip=0
        previous_ip = None #Used to check if there are duplicate addresses

        for i, ip in enumerate(ip_addresses):
            if previous_ip == ip:
                logger.error(f"Duplicate address detected : {ip}")
                return None
            previous_ip = ip
            if ip < ipaddress.ip_address(BASE_IP_FOR_WG_VPN):
                skip += 1
                continue
            if ip != ipaddress.ip_address(BASE_IP_FOR_WG_VPN) + i - skip:
                next_ip = ipaddress.ip_address(BASE_IP_FOR_WG_VPN) + i - skip
                break
        if next_ip == None:
            # If no holes are found, use the next IP address after the last one
            last_ip = ip_addresses[-1]
            next_ip = last_ip + 1
            if next_ip < ipaddress.ip_address(BASE_IP_FOR_WG_VPN):
                next_ip = ipaddress.ip_address(BASE_IP_FOR_WG_VPN)
    return str(next_ip)

def format_wireguard_client_config(private_key, ip_address, server_public_key=None,
                                   allowed_ips=None, endpoint=None):
    """Render the WireGuard client configuration handed to a user.

    Pure function: facts in, text out, so that the file a user receives can be
    frozen by a test. The [Peer] section is deployment configuration -- server
    key, allowed range, endpoint -- and a silent change there produces a client
    that looks configured and cannot connect, which is exactly the failure the
    duplicated server key made possible before it was removed.

    The three peer values default to the module constants; they are parameters
    so that a test can render the file without depending on this installation.

    Parameters:
        private_key (str): the client's private key.
        ip_address (str): the client's address inside the VPN, without prefix.
        server_public_key (str), allowed_ips (str), endpoint (str): the peer,
            defaulting to WG_SERVER_PUB_KEY, AllowedIPs and Endpoint.

    Returns:
        str: the content of the .conf file.
    """
    server_public_key = WG_SERVER_PUB_KEY if server_public_key is None else server_public_key
    allowed_ips = AllowedIPs if allowed_ips is None else allowed_ips
    endpoint = Endpoint if endpoint is None else endpoint

    return f"""[Interface]
PrivateKey = {private_key}
Address = {ip_address}/24

[Peer]
PublicKey = {server_public_key}
AllowedIPs = {allowed_ips}
Endpoint = {endpoint}
"""


def generate_wireguard_config(username, ip_address=None, ip_next=False):
    """
    Generate WireGuard configuration for a user, saving both the private key in the config file
    and the public key in a separate .wgpub file.

    Args:
    - username (str): Username for which to generate the WireGuard configuration.
    - ip_address (str, optional): IP address to assign to the user. If not provided, a new one is generated.
    - ip_next (bool, optional): If True, generate the next available IP address, otherwise
        use the first available hole in the IP address range.

    Returns:
    - Tuple containing the public key and IP address assigned to the user if successful, or (None, None) otherwise.
    """
    try:
        # If no IP address is provided, generate a new one
        if not ip_address:
            ip_address = get_wg_client_ip_address(ip_next=ip_next)
            if ip_address is None:
                logger.error("Failed to generate IP address for WireGuard client.")
                return None, None

        # Generate the private and public keys using wg
        key_file = f"{username}.tempkey"
        private_key = subprocess.check_output(f"wg genkey | tee {key_file}", shell=True).decode('utf-8').strip()
        public_key = subprocess.check_output(f"wg pubkey < {key_file}", shell=True).decode('utf-8').strip()

        config_content = format_wireguard_client_config(private_key, ip_address)
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

def generate_key_pair_for_web_access(user_name, crt_file, temp_key_file, pfx_file, pfx_password=None):
    """Generate key pair (CRT and PFX files) for the user to be used for web access.

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
            with open(temp_key_file, "wb") as key_out:
                key_out.write(private_key.private_bytes(
                    cryptography.hazmat.primitives.serialization.Encoding.PEM,
                    cryptography.hazmat.primitives.serialization.PrivateFormat.TraditionalOpenSSL,
                    cryptography.hazmat.primitives.serialization.NoEncryption()
                ))
        except IOError as e:
            logger.error(f"Failed to write private key to {temp_key_file}: {e}")
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
            "-inkey", temp_key_file,
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
            subprocess.run(["rm", temp_key_file], check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to delete key file {temp_key_file}: {e.stderr.strip()}")
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

def generate_ssh_key_pair(username, private_key_file, email=None):
    """
    Generate an Ed25519 SSH key pair for the user.

    Args:
    - username (str): Username for whom the keys are being generated.
    - private_key_file (str): Full path to the private key file.
    - email (str, optional): Email address to add to the public key as a comment.
    
    The public key is saved to a file with the same name as the private key file,
    but with the .pub extension.

    Returns:
    True if the key pair was generated successfully, False otherwise.
    """
    try:
        identifier = f"{FIGO_PREFIX}{email}" if email else f"{FIGO_PREFIX}{username}{FIGO_FAKE_DOMAIN}"
        # Generate the private key using ssh-keygen
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", private_key_file, "-N", "", "-C", identifier],
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
    It is optionally executed in the add_user function, if the command line argument -s, --set_vpn is provided.

    Args:
    - public_key (str): The WireGuard public key of the new VPN user.
    - ip_address (str): The allowed IP address (without prefix) for the VPN user
    - vpnuser (str): The VPN username, added as a comment for identification.
    - username (str, optional): The SSH username to connect to the MikroTik switch. Default is SSH_MIKROTIK_USER_NAME.
    - host (str, optional): The IP address or hostname of the MikroTik switch. Default is SSH_MIKROTIK_HOST.
    - port (int, optional): The SSH port for the MikroTik switch. Default is SSH_MIKROTIK_PORT.
    - interface (str, optional): The WireGuard interface on the MikroTik switch. Default is WG_INTERFACE.
    - keepalive (str, optional): The persistent keepalive interval. Default is WG_VPN_KEEPALIVE.

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

def remove_wireguard_vpn_user_on_mikrotik(vpnuser, username=SSH_MIKROTIK_USER_NAME, 
                                          host=SSH_MIKROTIK_HOST, port=SSH_MIKROTIK_PORT):
    """
    Removes a WireGuard VPN user configuration from a MikroTik switch.

    Args:
    - vpnuser (str): The VPN username to identify and remove the WireGuard peer.
    - username (str, optional): The SSH username to connect to the MikroTik switch. Default is SSH_MIKROTIK_USER_NAME.
    - host (str, optional): The IP address or hostname of the MikroTik switch. Default is SSH_MIKROTIK_HOST.
    - port (int, optional): The SSH port for the MikroTik switch. Default is SSH_MIKROTIK_PORT.

    Returns:
    - bool: True if the removal is successful, False otherwise.
    """

    try:
        # Set up the SSH client and connect to the MikroTik switch
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Automatically add the host key

        logger.info(f"Connecting to MikroTik switch at {host}...")
        ssh_client.connect(hostname=host, username=username, port=port)

        # Find the WireGuard peer by comment (vpnuser)
        find_command = (
            f'/interface wireguard peers print where comment="{vpnuser}"'
        )

        logger.info(f"Executing command on MikroTik: {find_command}")

        # Execute the find command
        stdin, stdout, stderr = ssh_client.exec_command(find_command)

        # Read output and error from the command execution
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        # Check for errors
        if error:
            logger.error(f"Error while finding WireGuard peer on MikroTik: {error}")
            return False

        # Parse the peer ID from the output
        peer_id = None
        for line in output.splitlines():
            if vpnuser in line:
                peer_id = line.split()[0]  # Assuming the first column is the peer ID
                break

        if not peer_id:
            logger.error(f"WireGuard peer with comment '{vpnuser}' not found.")
            return False

        # Build the WireGuard removal command
        remove_command = (
            f'/interface wireguard peers remove [find where comment="{vpnuser}"]'
        )

        logger.info(f"Executing command on MikroTik: {remove_command}")

        # Execute the remove command
        stdin, stdout, stderr = ssh_client.exec_command(remove_command)

        # Read output and error from the command execution
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        # Check for errors
        if error:
            logger.error(f"Error while removing WireGuard peer on MikroTik: {error}")
            return False

        # Log successful removal
        logger.info(f"WireGuard VPN user '{vpnuser}' removed successfully.")
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
    ip_next=False,
    set_vpn=False,
    project=None,
    email=None,
    name=None,
    org=None,
    keys=False,
    sshfs_keys=False,   
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
    - ip_next (bool, optional): Specifies if the next available IP address should be used for the WireGuard user, 
      (if wireguard is True) otherwise the first available hole in the IP range will be used.
    - set_vpn (bool, optional): Specifies if the user has to be added to the wireguard access node 
      (e.g. the MikroTik switch).
    - project (str, optional): Name of the existing project to restrict the certificate to.
      if not provided, a project will be created with the name 'figo-<user_name>'.
    - email (str, optional): Email address of the user.
    - name (str, optional): Name of the user.
    - org (str, optional): Organization of the user.
    - keys (bool, optional): If True, generate an additional Ed25519 SSH key pair for the user.
    - sshfs_keys (bool, optional): If True, generate SSHFS compatible SSH key pair for the user.

    This function performs the following steps:
    1. Check if the user already exists in the certificates.
    2. Check if the project exists on the remote server.
    3. Generate a new key pair and certificate if cert_file is not provided.
    4. Optionally generate an additional SSH key pair.
    4.1. Optionally generate an SSHFS compatible SSH key pair.
    5. Create a project for the user if not an admin and project is not provided.
    6. Add the user certificate to Incus.
    7. Generate WireGuard configuration if wireguard is True, assigning a new IP address.
    8. Add the user to the WireGuard VPN on the MikroTik switch if set_vpn is True.
    9. Create a .zip file with all the generated files.
       
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
        temp_key_file = os.path.join(directory, f"{user_name}.temp_key")
        if not generate_key_pair_for_web_access(user_name, crt_file, temp_key_file, pfx_file):
            logger.error(f"Failed to generate key pair and certificate for user: {user_name}")
            return False
        logger.info(f"Generated certificate and key pair for user: {user_name}")

    # Optionally generate additional SSH key pair if `keys` flag is set
    if keys:
        # Generate Ed25519 key pair for SSH login
        ssh_key_file = os.path.join(directory, f"{user_name}.{SSH_KEY_FILE_SUFFIX}")
        if not generate_ssh_key_pair(user_name, ssh_key_file, email=email):
            logger.error(f"Failed to generate SSH key pair for user: {user_name}")
            return False

    # Optionally generate SSHFS compatible SSH key pair if `sshfs_keys` flag is set
    if sshfs_keys:
        # Generate RSA key pair for SSHFS login
        sshfs_key_file = os.path.join(directory, f"{user_name}.{SSHFS_KEY_FILE_SUFFIX}")
        if not generate_ssh_key_pair(user_name, sshfs_key_file, email=email):
            logger.error(f"Failed to generate SSHFS key pair for user: {user_name}")
            return False

    # Create a project for the user in the main server (local)
    # if the user is not an admin and the project is not provided
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

    if not certificate_added:
        logger.error(f"Error: Failed to add certificate to Incus.")
        if project_created:
            delete_project("local", project_name)
        return False

    if wireguard:
        wg_public_key, wg_ip_address = generate_wireguard_config(user_name, ip_next=ip_next)
        if not wg_public_key:
            logger.error("Failed to generate WireGuard configuration.")
            return False
    
    # Create a .zip file with all the generated files in the directory
    zip_file = os.path.join(directory, f"{user_name}.zip")  # Create a .zip file with all the generated files
    with zipfile.ZipFile(zip_file, 'w') as zipf:
        zipf.write(crt_file, os.path.basename(crt_file))
        zipf.write(pfx_file, os.path.basename(pfx_file))
        if keys:
            zipf.write(ssh_key_file, os.path.basename(ssh_key_file))
            zipf.write(f"{ssh_key_file}.pub", os.path.basename(f"{ssh_key_file}.pub"))
            

        if wireguard:
            zipf.write(os.path.join(directory, f"{user_name}.conf"), f"{user_name}.conf")
            zipf.write(os.path.join(directory, f"{user_name}.wgpub"), f"{user_name}.wgpub") # Add the public key file to the .zip
            

    # Add the user to the WireGuard VPN on the MikroTik switch

    if set_vpn:
        if not wireguard:
            logger.error("Error: Cannot set VPN without generating WireGuard configuration.")
            return False
        
        if not add_wireguard_vpn_user_on_mikrotik(wg_public_key, wg_ip_address, user_name):
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

def delete_user(user_name, client, purge=False, removefiles=False, removevpn=False):
    """
    Delete a user from the system.

    Parameters:
    - username: Username of the user to delete
    - client: pylxd.Client instance
    - purge: If True, delete associated projects even if the user does not exist
    - removefiles: If True, remove files associated with the user in the USER_DIR
    - removevpn: If True, remove the user from the WireGuard VPN on the MikroTik switch
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

    # Remove the user from the WireGuard VPN on the MikroTik switch if the flag is set
    if removevpn:
        if not remove_wireguard_vpn_user_on_mikrotik(user_name):
            logger.warning(f"Failed to remove user '{user_name}' from WireGuard VPN on MikroTik.")

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
    """Lists the available Incus remotes and their addresses.
    
    Args:
    - full (bool): If True, display full information about each remote.
    - extend (bool): If True, adapt the column width to the content.
    """
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
    """List projects on the specified remote and project scope.
    
    Args:
    - remote_name (str): Name of the remote node.
    - project (str): Name of the project.
    - extend (bool): If True, adapt the output column width to the content.
    
    """

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
###### figo operation command functions #####
############################################# 

def get_create_instance_progress(remote_node, project_name, operation_id):
    """ Retrieve the progress of a create instance operation.
    
    Args:
    - remote_node (str): The name of the remote node.
    - project_name (str): The name of the project.
    - operation_id (str): The operation ID.
    """

    try:
        #use pylxd to get the operation progress
        remote_client = get_remote_client(remote_node, project_name=project_name)
        if not remote_client:
            logger.error(f"Failed to retrieve client for remote '{remote_node}', project_name '{project_name}'.")
            return "N/A"
        
        operation = remote_client.operations.get(operation_id)
        if operation is None:
            logger.error(f"Operation '{operation_id}' not found.")
            return "N/A"
        if operation.metadata is None:
            logger.error(f"Metadata for operation '{operation_id}' not found.")
            return "N/A"
        
        return operation.metadata.get("download_progress", "N/A")

    except Exception as e:
        logger.error(f"An error occurred while retrieving the progress of the create instance operation: {e}")
        return "N/A"

def get_operations(COLS, remote_node=None, project_name=None, output_format="csv", filter_progress=False, progress=False):
    """
    Retrieve operations for the specified remote node and project.

    Parameters:
    - COLS (list): List of tuples containing column names and widths.
    - remote_node (str): The name of the remote node.
    - project_name (str): The name of the project.
    - output_format (str): Format of the output (table, compact, csv).
    - filter_progress (bool): If True, display only create instance operations.
    - progress (bool): If True, display the progress of create instance operations.

    Only the csv format is fully supported for now.

    Returns:
    - bool: True if operations are retrieved successfully, False otherwise.
    """
    try:
        # Validate remote_node
        if not remote_node or ":" in remote_node.strip():
            logger.error(f"Invalid remote_node format: '{remote_node}'. Remote names must not contain ':' characters.")
            return False

        # Validate project_name
        if project_name and any(char in project_name for char in [":", "/", " "]):
            logger.error(f"Invalid project_name format: '{project_name}'. Project names must not contain ':', '/', or spaces.")
            return False
        
        if project_name == '':
            logger.error(f"Invalid project_name format: '{project_name}'. Project names must not be empty.")

        # Validate output_format
        valid_formats = ["table", "compact", "csv"]
        if output_format not in valid_formats:
            logger.error(f"Invalid output format: '{output_format}'. Valid options are: {', '.join(valid_formats)}.")
            return False

        # Construct the command
        command = f"incus operation list {shlex.quote(remote_node)}:"
        if project_name:
            command += f" --project {shlex.quote(project_name)}"
        command += f" --format {shlex.quote(output_format)}"

        # Execute the command using subprocess
        result = subprocess.run(shlex.split(command), capture_output=True, text=True)

        # Check for errors in command execution
        if result.returncode != 0:
            logger.error(f"Command failed with error: {result.stderr.strip()}")
            return False

        # Process the output
        output_lines = result.stdout.strip().splitlines()
        if not output_lines:
            return True

        # Handle output based on the format
        if output_format == "csv":
            for line in output_lines:
                # split the line by comma
                line_tokens = line.split(",")
                if line_tokens[2] == "Creating instance":
                    if progress:
                        # add the progress of the create instance operation
                        line_tokens.append(get_create_instance_progress(remote_node, project_name,line_tokens[0]))
                else:
                    if filter_progress:
                        continue
                    if progress:
                        # add "" for the progress of the operation
                        line_tokens.append("")
                # add the remote_node and project_name as first element in line_tokens
                line_tokens.insert(0, f"{remote_node}:{project_name}")
                add_row_to_output(COLS, line_tokens)

        elif output_format == "compact":
            i = 0
            for line in output_lines:
                if i > 0:
                    add_row_to_output(COLS, [f"{remote_node}:{project_name}",line])                
                i += 1

        elif output_format == "table":
            i = 0
            for line in output_lines:
                if i >= 3 and i % 2 == 1:
                    add_row_to_output(COLS, [f"{remote_node}:{project_name}",line])                
                i += 1

        return True

    except Exception as e:
        logger.error(f"An error occurred while retrieving operations: {e}")
        return False


def display_operation_status(remote_node, project_name, filter_progress=False, progress=False, extend=False):
    """
    Display the staus of the operations based on the provided scope (remote and project).

    If remote_node is None, then all remotes are considered.
    If project_name is None, then all projects are considered.
    If both remote_node and project_name are None, then all operations are considered.
    
    The output is displayed in a table format.

    This function is not optimized, because it calls get_operations() for each remote and project combination.
    In turn, get_operations() calls the incus operation list command for each remote and project combination.
    This can be optimized by calling the incus operation list command only once for each remote by using the --all-projects flag.

    Parameters:
    - remote_node (str): Remote name.
    - project (str): Project name.
    - filter_progress (bool): If True, display only create instance operations.
    - progress (bool): If True, display the progress of create instance operations.
    - extend (bool): If True, adapt the column width to the content.
    """

    COLS = [('REMOTE:PROJECT',25),('OP ID',15),('TYPE',10),('DESCRIPTION',18),('STATE',8),('CANC.',6),('CREATED',20)]
    if progress:
        COLS.append(('PROGRESS',25))
   
    # Add header to output
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

                        # Get operations for the specified project_name
                        result = get_operations(COLS, remote_node=my_remote_node, project_name=my_project_name,
                                                filter_progress=filter_progress, progress=progress)
                        if not result:
                            set_of_errored_remotes.add(my_remote_node)
                        
            else: # project_name is not None
                # Get instances for the specified project_name
                result = get_operations(COLS, remote_node=my_remote_node, project_name=project_name,
                                        filter_progress=filter_progress, progress=progress)
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
                    result = get_operations(COLS, remote_node=remote_node, project_name=my_project_name,
                                            filter_progress=filter_progress, progress=progress)
                    if not result:
                        set_of_errored_remotes.add(remote_node)
        else: # remote_node is not None and project_name is not None
            # Get instances from the specified remote node and project
            result = get_operations(COLS, remote_node=remote_node, project_name=project_name,
                                    filter_progress=filter_progress, progress=progress)
            if not result:
                set_of_errored_remotes.add(remote_node)
    flush_output(extend=extend) 

    if set_of_errored_remotes:
        logger.error(f"Error: Failed to retrieve projects from remote(s): {', '.join(set_of_errored_remotes)}")

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
    f"""
    Adds a route on a Linux VPN access node using the ip route command.

    Args:
    - dst_address (str): The destination address in CIDR format (e.g., '10.202.128.0/24').
    - gateway (str): The gateway address for the route (e.g., '10.202.9.2').
    - dev (str): The interface (e.g., 'vlan403') to use for the route.
    - username (str, optional): The SSH username to connect to the Linux router. Default is {DEFAULT_LOGIN_FOR_INSTANCES}.
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
###### figo storage command functions #######
############################################# 

# Placeholder implementations (to be filled in)
def storage_enroll(args):
    logger.info(f"[STORAGE] Enrolling {args.fileserver_name} ({args.ip_address}) as {args.backend_fs}, \
user={args.ssh_user}, mount={args.mount_path}, pool={args.pool_name} - NOT IMPLEMENTED YET")

def storage_delete(args):
    logger.info(f"[STORAGE] Deleting fileserver {args.fileserver_name} - NOT IMPLEMENTED YET")

def storage_list():
    logger.info("[STORAGE] Listing fileservers - NOT IMPLEMENTED YET")   


from pathlib import Path
from io import StringIO

STORAGE_REGISTRY_PATH = "storage/servers.yaml"

def storage_set_quota(args):
    logger.info(f"[STORAGE] Setting quota {args.quota_size} for user {args.user} on {args.fileserver_name}")
    username = args.user
    quota = args.quota_size
    fileserver_name = args.fileserver_name

    # Load file server registry from YAML
    with open(STORAGE_REGISTRY_PATH, "r") as f:
        registry = yaml.safe_load(f)
    server_info = registry["fileservers"].get(fileserver_name)
    if not server_info:
        raise ValueError(f"Fileserver '{fileserver_name}' not found in registry.")

    mountpoint = server_info["mount_path"]
    poolname = server_info["pool_name"]
    fileserver_ip = server_info["ip"]
    ssh_user = server_info["ssh_user"]
    dataset = f"{poolname}/{username}"
    mountfolder = f"{mountpoint}/{username}"

    key_src = Path("users") / f"{username}.{SSHFS_KEY_FILE_SUFFIX}.pub"
    if not key_src.exists():
        raise FileNotFoundError(f"Missing key file: {key_src}")

    with paramiko.SSHClient() as ssh:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=fileserver_ip, username=ssh_user)

        def run(cmd):
            logger.info(f"[REMOTE CMD] {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode()
            err = stderr.read().decode()
            if stdout.channel.recv_exit_status() != 0:
                raise RuntimeError(f"Command failed: {cmd}\n{err}")
            return out

        try:
            # Check if dataset exists
            result = ssh.exec_command(f"zfs list {dataset}")[1].channel.recv_exit_status()
            if result != 0:
                run(f"sudo zfs create {dataset}")

            # Set quota
            run(f"sudo zfs set quota={quota} {dataset}")

            # Create system user if not exists
            run(f"id -u {username} || sudo useradd -M -s /usr/sbin/nologin {username}")

            # Create data directory
            run(f"sudo mkdir -p {mountfolder}/data")

            # Set ownership
            run(f"sudo chown {username}:{username} {mountfolder}/data")

            remote_tmp_path = f"/tmp/{username}"
            remote_final_path = f"/etc/ssh/authorized_keys/{username}"

            # Copy to /tmp via SFTP
            sftp = ssh.open_sftp()
            sftp.put(str(key_src), remote_tmp_path)
            sftp.close()

            # Move with sudo and set permissions
            run(f"sudo mv {remote_tmp_path} {remote_final_path}")
            run(f"sudo chown {username}:{username} {remote_final_path}")
            run(f"sudo chmod 0600 {remote_final_path}")

            # Write SFTP-only config
            sftp_conf = f"""Match User {username}
    ChrootDirectory {mountfolder}
    ForceCommand internal-sftp
    AllowTcpForwarding no
    X11Forwarding no
"""
            remote_conf_path = f"/etc/ssh/sshd_config.d/70-{username}-sftp.conf"
            run(f"echo '{sftp_conf}' > /tmp/70-{username}-sftp.conf")
            run(f"sudo mv /tmp/70-{username}-sftp.conf {remote_conf_path}")
            run(f"sudo chown root:root {remote_conf_path}")
            run(f"sudo chmod 0644 {remote_conf_path}")
            run("sudo systemctl restart ssh")

            logger.info(f"[OK] Quota set and user configured on remote: {username} -> {quota}")

        except Exception as e:
            logger.info(f"[ERROR] {e}")

def storage_discard(args):
    logger.info(f"[STORAGE] Discarding user {args.user} from {args.fileserver_name}")


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

def check_remote_name(remote_name):
    """
    Check validity of a remote name according to Incus naming conventions.

    Args:
        remote_name (str): The name of the remote to validate.

    Returns:
        bool: True if the remote name is valid, False otherwise.
    """
    if remote_name is None:
        return False

    # Remote name may contain lowercase letters, numbers, hyphens, and underscores.
    # Cannot start or end with a hyphen or underscore.
    if not re.match(r'^[a-z0-9]+([-_][a-z0-9]+)*$', remote_name):
        logger.error(f"Error: Invalid remote name '{remote_name}'. Remote names must contain only lowercase letters, "
                     "numbers, hyphens, and underscores, and cannot start or end with a hyphen or underscore.")
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
        "instance",
        help="Manage instances.",
        description=(
            "Manage instances, including creating, listing, starting, stopping, setting IP addresses, "
            "adding public keys, and executing bash commands.\n\n"
            "The `instance` command allows precise control of instance operations, with support for "
            "remote and project scope specification. You can also create instances with custom profiles, "
            "assign static IP addresses, and set up authorized keys for users."
        ),
        epilog="Use 'figo instance <command> -h' for detailed help on a specific subcommand.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    instance_subparsers = instance_parser.add_subparsers(dest="instance_command")

    # Add common options for remote, project, user, and relax mode
    def add_common_arguments(parser):
        parser.add_argument("-r", "--remote", help="Specify the remote server name")
        parser.add_argument("-p", "--project", help="Specify the project name")
        parser.add_argument(
            "-u", "--user",
            help="Specify the username to infer the project and the key file name. Relevant for commands such as list, start, stop, and set_key."
        )
        parser.add_argument(
            "-x", "--relax",
            action="store_true",
            help="Avoid inferring the project from the user argument. The user is only used to derive the key file."
        )

    # Add common options for IP, gateway, and NIC
    def add_common_ip_gw_nic_arguments(parser):
        parser.add_argument("-i", "--ip", help="Specify a static IP address for the instance")
        parser.add_argument("-g", "--gw", help="Specify the gateway address for the instance")
        parser.add_argument(
            "-n", "--nic",
            help=(
                "Specify the NIC name for the instance. Used in `create` and `set_ip` subcommands.\n"
                "Default: 'eth0' for containers, 'enp5s0' for VMs."
            )
        )

    # List command
    instance_list_parser = instance_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List instances in the system, with options to specify scope, remote, and project.",
        description="List instances, optionally specifying a scope, remote server, or project.\n"
                    "The scope can include 'remote:project.', 'project.', or 'remote:'.\n"
                    "Use the -f/--full option to display more detailed information.\n"
                    "Use the -e/--extend option to extend column width for better readability.\n"
                    "Use the -j/--join option to combine the context and instance name into a single field for display.\n"
                    "Use the -a/--additional option to show one row for each additional IP address held by an instance.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance list\n"
            "  figo instance list remote:project.\n"
            "  figo instance list project. -r remote_name\n"
            "  figo instance list -f --extend\n"
            "  figo instance list -j\n"
            "  figo instance list -a"
    )
    instance_list_parser.add_argument(
        "-f", "--full", action="store_true", help="Show full details of instance profiles"
    )
    instance_list_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit content"
    )
    instance_list_parser.add_argument(
        "-j", "--join", action="store_true",
        help="Join the context and instance name into a single field."
    )
    instance_list_parser.add_argument(
        "-a", "--additional", action="store_true",
        help="Expand each instance holding additional IP addresses into one row per address,\n"
             "and add the NAME and MAC columns."
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
                    "If the scope is not provided in the instance name, the -r/--remote and -p/--project options can be used.\n"
                    "If the filename is not provided and the -u/--user option is provided,\n"
                    "the public key is derived from the user's default key location.\n"
                    "By default, the project is inferred from the user, but this behavior can be overridden using the -x/--relax option,\n"
                    "which skips the consistency check between the user and project and only uses the user to determine the key file",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance set_key instance_name\n"
            "  figo instance set_key instance_name key_filename\n"
            "  figo instance set_key remote:project.instance_name key_filename -r remote_name -p project_name"
    )
    set_key_parser.add_argument("instance_name", help="Name of the instance. Can include remote and project scope.")
    set_key_parser.add_argument(
        "key_filename",
        nargs="?",
        default=None,
        help="Optional filename of the public key on the host. If not provided, the system uses a default based on -u/--user parameter."
    )
    set_key_parser.add_argument(
        "-l", "--login", default=DEFAULT_LOGIN_FOR_INSTANCES,
        help=f"Specify the user login name for which we are setting the key "
        "(default: {DEFAULT_LOGIN_FOR_INSTANCES})."
    )
    set_key_parser.add_argument(
        "-d", "--dir", default=USER_DIR,
        help=f"Specify the directory path where the key file is located (default: {USER_DIR})."
    )
    set_key_parser.add_argument(
        "-f", "--force", action="store_true",
        help="Start the instance if not running, then stop after setting the key."
    )
    add_common_arguments(set_key_parser)


    # Show Keys command
    show_keys_parser = instance_subparsers.add_parser(
        "show_keys",
        help="List the keys associated with an instance.",
        description="List the keys associated with a specific instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "If the scope is not provided in the instance name, the -r/--remote and -p/--project options can be used.\n"
                    "Use the -l/--login option to specify the user login, the -f/--force option to start the instance if it is not running, and the -k/--keys option to show the full key details.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance show_keys instance_name\n"
            "  figo instance show_keys remote:project.instance_name -l user_login\n"
            "  figo instance show_keys instance_name -f -r remote_name -p project_name\n"
            "  figo instance show_keys instance_name -k --extend"
    )
    show_keys_parser.add_argument(
        "instance_name",
        help="Name of the instance to list keys for. Can include remote and project scope."
    )
    show_keys_parser.add_argument(
        "-l", "--login",
        default=DEFAULT_LOGIN_FOR_INSTANCES,
        help=f"Specify the user login name for which we are showing the keys "
        "(default: {DEFAULT_LOGIN_FOR_INSTANCES})."
    )
    show_keys_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Start the instance if not running (and then stops it)."
    )
    show_keys_parser.add_argument(
        "-k", "--keys",
        action="store_true",
        help="Show full key details, including the full key content."
    )
    show_keys_parser.add_argument(
        "-e", "--extend",
        action="store_true",
        help="Extend column widths to fit content for better readability."
    )
    add_common_arguments(show_keys_parser)

    # Set IP command
    set_ip_parser = instance_subparsers.add_parser(
        "set_ip",
        help="Set a static IP address and gateway for a stopped instance.",
        description="Set a static IP address and gateway for a stopped instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "If the IP address/prefix len is not provided, an available IP address will be assigned with the default prefix len associated with the remote.\n"
                    "By default, the next IP address after the highest assigned IP is chosen, but using --hole assigns the first available gap in the IP range.\n"
                    "If the gateway is not provided, the default gateway associated with the remote will be used.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance set_ip instance_name -i 192.168.1.10/24 -g 192.168.1.1\n"
            "  figo instance set_ip remote:project.instance_name -i 10.0.0.5/24 -g 10.0.0.1\n"
            "  figo instance set_ip my_remote:my_project.instance_name --hole\n"
            "  figo instance set_ip remote:project.instance_name  # Automatically assigns an available IP and default gateway"
    )
    set_ip_parser.add_argument(
        "instance_name",
        help="Name of the instance to set the IP address for. Can include remote and project scope."
    )
    set_ip_parser.add_argument(
        "-o", "--hole",
        action="store_true",
        help="Assign the first available IP address hole in the range, rather than the next sequential IP."
    )
    add_common_arguments(set_ip_parser)
    add_common_ip_gw_nic_arguments(set_ip_parser)

    # Additional IP command, with its own list/add/remove subcommands
    additional_ip_parser = instance_subparsers.add_parser(
        "additional_ip",
        aliases=["aip"],
        help="Manage the additional IP addresses held by an instance.",
        description="Manage the additional IP addresses held by an instance.\n"
                    "Besides the address configured on the instance itself, an instance can hold further\n"
                    "addresses of the same subnet: addresses used by nested QEMU virtual machines it runs,\n"
                    "by containers started inside it, or extra addresses on its own NIC.\n"
                    "Registering them makes the IPAM aware that they are taken, so that they are never\n"
                    "handed out to another instance.\n"
                    "figo records these addresses, it does NOT configure anything inside the instance.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance additional_ip list\n"
            "  figo instance additional_ip add my_instance --mac auto -n gob0\n"
            "  figo instance additional_ip remove my_instance 10.202.9.214"
    )
    additional_ip_subparsers = additional_ip_parser.add_subparsers(dest="additional_ip_command")

    # Additional IP: list
    additional_ip_list_parser = additional_ip_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List the additional IP addresses held by an instance, or by all instances in a scope.",
        description="List the additional IP addresses held by an instance.\n"
                    "If the instance name is omitted, the additional addresses of all the instances\n"
                    "in the scope are listed.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance additional_ip list\n"
            "  figo instance additional_ip list my_instance\n"
            "  figo instance additional_ip list remote:project.my_instance\n"
            "  figo instance additional_ip list -r remote_name --extend"
    )
    additional_ip_list_parser.add_argument(
        "instance_name", nargs="?",
        help="Name of the instance. Can include remote and project scope.\n"
             "If omitted, all the instances in the scope are listed."
    )
    additional_ip_list_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit content"
    )
    add_common_arguments(additional_ip_list_parser)

    # Additional IP: add
    additional_ip_add_parser = additional_ip_subparsers.add_parser(
        "add",
        aliases=["a"],
        help="Register an additional IP address held by an instance.",
        description="Register an additional IP address held by an instance.\n"
                    "If the IP address is not provided, an available one is assigned and printed.\n"
                    "By default the next address after the highest assigned one is chosen, but using\n"
                    "--hole assigns the first available gap in the IP range.\n"
                    "The command fails if the address is already in use, or outside the subnet of the remote.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance additional_ip add my_instance\n"
            "  figo instance additional_ip add my_instance --mac auto -n gob0\n"
            "  figo instance additional_ip add remote:project.my_instance 10.202.9.214 --mac 52:54:00:ca:09:d6\n"
            "  figo instance additional_ip add my_instance --hole --mac auto -n justin"
    )
    additional_ip_add_parser.add_argument(
        "instance_name",
        help="Name of the instance holding the address. Can include remote and project scope."
    )
    additional_ip_add_parser.add_argument(
        "ip_address", nargs="?",
        help="IP address to register, without prefix length (e.g. 10.202.9.214).\n"
             "If omitted, an available address is assigned by figo and printed."
    )
    additional_ip_add_parser.add_argument(
        "--mac",
        help="MAC address to record for the entry. Use the literal value 'auto' to have it derived\n"
             "deterministically from the IP address. If omitted, no MAC address is recorded."
    )
    additional_ip_add_parser.add_argument(
        "-n", "--name",
        help="A free-form label recording what the address is used for."
    )
    additional_ip_add_parser.add_argument(
        "-o", "--hole",
        action="store_true",
        help="Assign the first available IP address hole in the range, rather than the next sequential IP.\n"
             "Only meaningful when the IP address is not provided."
    )
    add_common_arguments(additional_ip_add_parser)

    # Additional IP: remove
    additional_ip_remove_parser = additional_ip_subparsers.add_parser(
        "remove",
        aliases=["r"],
        help="Remove one additional IP address registration from an instance, or all of them.",
        description="Remove one additional IP address registration from an instance, or all of them.\n"
                    "Exactly one of the IP address and --all must be provided.\n"
                    "Removing a registration only frees the address for future allocation: whatever was\n"
                    "using it is not stopped nor reconfigured.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance additional_ip remove my_instance 10.202.9.214\n"
            "  figo instance additional_ip remove remote:project.my_instance 10.202.9.214\n"
            "  figo instance additional_ip remove my_instance --all"
    )
    additional_ip_remove_parser.add_argument(
        "instance_name",
        help="Name of the instance. Can include remote and project scope."
    )
    additional_ip_remove_parser.add_argument(
        "ip_address", nargs="?",
        help="IP address to remove. Must not be given together with --all."
    )
    additional_ip_remove_parser.add_argument(
        "-a", "--all", action="store_true",
        help="Remove every additional address registered for the instance."
    )
    add_common_arguments(additional_ip_remove_parser)

    # Create command
    create_parser = instance_subparsers.add_parser(
        "create",
        aliases=["c"],
        help="Create a new instance, specifying the instance name, image, type, and optional profiles.",
        description="Create a new instance.\n"
                    "The instance name can include remote and project scope in the format 'remote:project.instance_name'.\n"
                    "Specify the image, instance type, optional profiles, and the option to create the project if it does not exist.\n"
                    "If the IP address is not provided, an available IP address is automatically assigned with the default prefix length for the remote.\n"
                    "By default, the next IP address after the highest assigned IP is chosen, but using --hole assigns the first available gap in the IP range.\n"
                    "The -k/--key option allows adding a public key to the instance's authorized_keys for a user specified with -u/--user.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
            "  figo instance create instance_name image_name\n"
            "  figo instance create remote:project.instance_name image_name -t vm\n"
            "  figo instance create instance_name image_name -r remote_name -p project_name\n"
            "  figo instance create instance_name image_name -f profile1,profile2\n"
            "  figo instance create instance_name image_name -m --hole\n"
            "  figo instance create instance_name image_name -u user -k\n"
            "  figo instance create instance_name image_name -u user -s\n"
            "  figo instance create instance_name image_name -u user -k -l newlogin"
    )
    create_parser.add_argument(
        "instance_name",
        help="Name of the new instance.\n"
            "Can include remote and project scope in the format 'remote:project.instance_name'."
    )
    create_parser.add_argument(
        "image",
        help="Image source to create the instance from. Format: 'remote:image' or 'image'."
    )
    create_parser.add_argument(
        "-t", "--type", choices=["vm", "container", "cnt"], default="container",
        help="Specify the instance type: 'vm', 'container', or 'cnt' (default: 'container')."
    )
    create_parser.add_argument(
        "-f", "--profile",
        help="Comma-separated list of profiles to apply to the instance."
    )
    create_parser.add_argument(
        "-m", "--make_project", action="store_true",
        help="Create the project if it does not exist on the remote specified."
    )
    create_parser.add_argument(
        "-o", "--hole",
        action="store_true",
        help="Assign the first available IP address hole in the range, rather than the next sequential IP."
    )
    create_parser.add_argument(
        "-k", "--key",
        action="store_true",
        help="Add the user's public key to the instance's authorized_keys file. Requires -u/--user."
    )
    create_parser.add_argument(
        "-s", "--storage",
        action="store_true",
        help=(
        "Enable predefined per-user external storage via SSHFS automount at creation time.\n"
        "Mount definitions are taken from figo configuration variables and the required SSH private key\n"
        "is injected into the instance during creation."
        )
    )
    create_parser.add_argument(
        "-l", "--login",
        default=DEFAULT_LOGIN_FOR_INSTANCES,
        help=f"Specify the user login name on the instance for which the key provides access "
        "(default: {DEFAULT_LOGIN_FOR_INSTANCES})."
    )
    add_common_arguments(create_parser)
    add_common_ip_gw_nic_arguments(create_parser)

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
    bash_parser.add_argument("-t", "--timeout", type=int, default=30, help="Total timeout in seconds for retries (default: 30)")
    bash_parser.add_argument("-a", "--attempts", type=int, default=3, help="Number of retry attempts to connect (default: 3)")
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
    list_instances(remote_node, project_name=project_name, instance_scope=instance_scope,
                   full=args.full, extend=args.extend, join=args.join,
                   additional=getattr(args, 'additional', False))

def _get_instance_object(remote, project, instance):
    """Fetch a pylxd instance object, logging the reason when it cannot be obtained.

    Returns: the instance object, or None on failure.
    """
    client_instance = get_remote_client(remote, project_name=project)
    if not client_instance:
        logger.error(f"Failed to connect to remote '{remote}', project '{project}'.")
        return None
    try:
        return client_instance.instances.get(instance)
    except Exception as e:
        logger.error(f"Error: instance '{instance}' not found in '{remote}:{project}': {e}")
        return None

def handle_additional_ip_list(args):
    """Handle 'figo instance additional_ip list'."""
    COLS = [('INSTANCE',16), ('CONTEXT',25), ('IP ADDRESS',16), ('NAME',12), ('MAC',17)]

    def iterate_targets():
        """Yield (remote, project, instance_scope) triples covering the requested scope."""
        if args.instance_name:
            remote, project, instance = parse_instance_scope(args.instance_name, args.remote, args.project)
            if instance is None:
                return
            yield remote, project, instance
            return

        if args.remote:
            remotes = [args.remote]
        else:
            all_remotes = get_incus_remotes() or {}
            # skip the image servers, they hold no instances
            remotes = [name for name, info in all_remotes.items()
                       if info.get("Protocol") != "simplestreams"]

        for remote in remotes:
            if args.project:
                yield remote, args.project, None
            else:
                projects = get_projects(remote_name=remote)
                if projects is None:
                    logger.error(f"Error: Failed to retrieve the projects of remote '{remote}'.")
                    continue
                for project in projects:
                    yield remote, project["name"], None

    add_header_line_to_output(COLS)

    found = False
    for remote, project, instance_scope in iterate_targets():
        for instance_state_dict in iterator_over_instance_dicts(remote, project, instance_scope):
            for entry in get_additional_ips_from_config(instance_state_dict.get("config")):
                found = True
                add_row_to_output(COLS, [instance_state_dict.get("name", "Unknown"),
                                         f"{remote}:{project}",
                                         entry['ip'],
                                         entry['name'] or '',
                                         entry['mac'] or ''])

    flush_output(extend=args.extend)

    if not found:
        logger.info("No additional IP addresses are registered in the specified scope.")
    return True

def handle_additional_ip_add(args):
    """Handle 'figo instance additional_ip add'."""
    remote, project, instance = parse_instance_scope(args.instance_name, args.remote, args.project)
    if instance is None:
        return False

    # The subnet of the remote is needed both to validate a user-provided address and to detect
    # the exhaustion of the range when figo assigns one.
    gw_address = get_gw_address(remote)
    prefix_len = get_prefix_len(remote)
    if gw_address is None or prefix_len is None:
        return False

    # Either validate the address provided by the user, or let figo assign one. The two paths
    # report a failure differently: an address out of the subnet is a mistake of the caller,
    # while an assigned address out of the subnet means the range has been used up.
    if args.ip_address:
        if not is_valid_ip(args.ip_address):
            logger.error(f"Error: Invalid IP address '{args.ip_address}'.")
            return False
        ip_address = args.ip_address
        if not is_same_subnet(ip_address, gw_address, prefix_len):
            logger.error(f"Error: IP address '{ip_address}' is not in the subnet of remote '{remote}'.")
            return False
    else:
        ip_address = assign_ip_address(remote, mode="hole" if args.hole else "next")
        if ip_address is None:
            logger.error(f"Error: Failed to assign an IP address on remote '{remote}'.")
            return False
        if not is_same_subnet(ip_address, gw_address, prefix_len):
            logger.error(f"Error: No IP address is left to assign on remote '{remote}': "
                         f"the range of the subnet {gw_address}/{prefix_len} is used up.")
            return False

    # The address must not be in use, no matter what holds it: an instance, the additional
    # addresses of any instance, or the nested instances of an L1 host.
    assigned_ips = retrieve_assigned_ips(remote)
    if assigned_ips is None:
        return False
    if ip_address in assigned_ips:
        logger.error(f"Error: IP address '{ip_address}' is already in use on remote '{remote}'.")
        return False

    mac_address = None
    if args.mac:
        if args.mac.lower() == 'auto':
            mac_address = derive_mac_from_ip(ip_address)
            if mac_address is None:
                return False
        elif is_valid_mac(args.mac):
            mac_address = args.mac.lower()
        else:
            logger.error(f"Error: Invalid MAC address '{args.mac}'.")
            return False

    instance_object = _get_instance_object(remote, project, instance)
    if instance_object is None:
        return False

    if not add_additional_ip(instance_object, ip_address, mac=mac_address, name=args.name):
        return False

    logger.info(f"Additional IP address '{ip_address}' registered for instance "
                f"'{remote}:{project}.{instance}'"
                + (f" with MAC '{mac_address}'" if mac_address else "") + ".")
    # Print the address, and nothing else, on stdout: the log goes to stderr, so the command can
    # be used as IP=$(figo instance additional_ip add ...) whatever flags were passed. The shape
    # of this line must not depend on the options, or it stops being usable in a script.
    print(ip_address)
    return True

def handle_additional_ip_remove(args):
    """Handle 'figo instance additional_ip remove'."""
    if bool(args.ip_address) == bool(args.all):
        logger.error("Error: provide either an IP address or --all, but not both.")
        return False

    remote, project, instance = parse_instance_scope(args.instance_name, args.remote, args.project)
    if instance is None:
        return False

    if args.ip_address and not is_valid_ip(args.ip_address):
        logger.error(f"Error: Invalid IP address '{args.ip_address}'.")
        return False

    instance_object = _get_instance_object(remote, project, instance)
    if instance_object is None:
        return False

    if args.all:
        return clear_additional_ip_list(instance_object)
    return remove_additional_ip(instance_object, args.ip_address)

def handle_instance_additional_ip(args):
    """Handle the 'additional_ip' subcommand group for instances."""
    if not args.additional_ip_command:
        logger.error("Error: No additional_ip subcommand provided. "
                     "Use 'figo instance additional_ip --help' to see the available subcommands.")
        return False

    # Derive the project from the user, consistently with the other instance subcommands.
    if getattr(args, 'user', None) and not args.relax:
        user_project = derive_project_from_user(args.user)
        if user_project:
            if args.project and user_project != args.project:
                logger.error(f"Error: Conflict between derived project '{user_project}' from user "
                             f"'{args.user}' and provided project '{args.project}'.")
                return False
            args.project = user_project

    if args.additional_ip_command in ["list", "l"]:
        return handle_additional_ip_list(args)
    elif args.additional_ip_command in ["add", "a"]:
        return handle_additional_ip_add(args)
    elif args.additional_ip_command in ["remove", "r"]:
        return handle_additional_ip_remove(args)

    logger.error(f"Error: Unknown additional_ip subcommand '{args.additional_ip_command}'.")
    return False

def handle_instance_command(args, parser_dict):
    if not args.instance_command:
        parser_dict['instance_parser'].print_help()
        return

    def parse_instance_scope_for_all(instance_name, provided_remote, provided_project):
        """Parse the instance name to extract remote, project, and instance for the '--all' option of the stop command."""
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

    def derive_pub_key_from_user(user, folder):
        """Derive the non-SSHFS public key filename from the user."""

        # list all files that start with '<user>', end with '.pub' and do NOT contain 'sshfs'
        files = [
            f for f in os.listdir(folder)
            if f.startswith(f"{user}")
            and f.endswith(".pub")
            and "sshfs" not in f
        ]

        if len(files) == 0:
            logger.error(f"Error: No public key file found for user '{user}'.")
            return None
        elif len(files) > 1:
            logger.error(f"Error: Multiple public key files found for user '{user}'.")
            return None
        else:
            return files[0]

    def derive_priv_sshfs_key_from_user(user, folder):
        """Derive the private SSHFS key filename from the user."""

        # list all files that start with '<user>', contain 'sshfs' and do not end with '.pub'
        files = [
            f for f in os.listdir(folder)
            if f.startswith(f"{user}")
            and "sshfs" in f
            and not f.endswith(".pub")
        ]

        if len(files) == 0:
            logger.error(f"Error: No SSHFS private key file found for user '{user}'.")
            return None
        elif len(files) > 1:
            logger.error(f"Error: Multiple SSHFS private key files found for user '{user}'.")
            return None
        else:
            return files[0]
    
    # Validate the IP address and prefix length
    # check before if the ip attribute exists in args to avoid error
    if hasattr(args, 'ip') and args.ip and not is_valid_ip_prefix_len(args.ip):
        logger.error(f"Error: Invalid IP address or prefix length '{args.ip}'.")
        return

    # Validate the gateway address if provided
    # check before if the gw attribute exists in args to avoid error
    if hasattr(args, 'gw') and args.gw and not is_valid_ip(args.gw):
        logger.error(f"Error: Invalid gateway address '{args.gw}'.")
        return

    if args.instance_command in ["list", "l"]:
        handle_instance_list(args)
    elif args.instance_command in ["additional_ip", "aip"]:
        handle_instance_additional_ip(args)
    else:
        provided_user = None
        
        user_project = None
        
        if 'user' in args and args.user:
            # Store the provided user for later use
            provided_user = args.user
            if not args.relax:
                # Handle project based on user if provided
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

                if not provided_user and not args.key_filename:
                    logger.error("Error: Must provide a user or a key filename.")
                    return
                
                if args.key_filename:
                    my_key_filename = args.key_filename
                else:
                    # provided_user is not None
                    my_key_filename = derive_pub_key_from_user(provided_user, folder) 
                    if my_key_filename is None:
                        return
                    
                set_user_key(instance, remote, project, my_key_filename, login=login, folder=folder, force=force)

            elif args.instance_command == "show_keys":
                # Extract the parameters with defaults applied
                login = args.login
                force = args.force

                # Call the function to display keys, relying on its internal error handling
                get_instance_keys(
                    instance,
                    remote,
                    project,
                    login=login,
                    force=force,
                    full=args.keys,  # Corresponds to -k/--keys
                    extend=args.extend  # Corresponds to -e/--extend
                )

            elif args.instance_command == "set_ip":
                # if args.hole and args.ip return error
                if args.hole and args.ip:
                    logger.error("Error: Cannot use both --hole and --ip options together.")
                    return

                set_ip(instance, remote, project, 
                    ip_address_and_prefix_len=args.ip, gw_address=args.gw, nic_device_name=args.nic, hole=args.hole)
            elif args.instance_command in ["create", "c"]:
                # if args.hole and args.ip return error
                if args.hole and args.ip:
                    logger.error("Error: Cannot use both --hole and --ip options together.")
                    return

                if args.key:
                    if not args.user:
                        logger.error("Error: -k/--key requires -u/--user to specify the public key owner.")
                        return
                    my_pubkey_filename = derive_pub_key_from_user(args.user, USER_DIR) 
                    if my_pubkey_filename is None:
                        return

                if args.storage:
                    if not args.user:
                        logger.error("Error: -s/--storage requires -u/--user to specify the storage owner.")
                        return
                    my_sshfs_key_filename = derive_priv_sshfs_key_from_user(args.user, USER_DIR)
                    if my_sshfs_key_filename is None:
                        logger.error("Error: Cannot proceed without a valid SSHFS private key file.")
                        return

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
                                profiles=profiles, create_project_flag=args.make_project, hole=args.hole,
                                login_pubkey_filename=my_pubkey_filename if args.key else None,
                                sshfs_prikey_filename=my_sshfs_key_filename if args.storage else None,
                                folder = USER_DIR, login=args.login, sshfs_user_name=args.user)
            elif args.instance_command in ["delete", "del", "d"]:
                delete_instance(instance, remote, project, force=args.force)
            elif args.instance_command in ["bash", "b"]:
                exec_instance_bash(instance, remote, project, force=args.force, timeout=args.timeout,
                                   max_attempts=args.attempts)
            else:
                logger.error(f"Unknown instance subcommand: {args.instance_command}")

#############################################
###### figo gpu command CLI #################
#############################################

# --- The default-gateway invariant (Section 3.3) ----------------------------
#
# An instance reached through a floating IP must have the serving gw-float as
# its default gateway: the return path goes back through the gateway, where
# conntrack knows the flow. The value is read *per instance* and never deduced
# from the subnet -- measured on 2026-08-26, instances on the same subnet have
# different default gateways depending on whether they hold a floating IP.

FLOAT_INVARIANT_OK = 'ok'
FLOAT_INVARIANT_VIOLATED = 'violated'
FLOAT_INVARIANT_UNKNOWN = 'unknown'
FLOAT_INVARIANT_NOT_CHECKED = 'not_checked'

GATEWAY_READ_OK = 'ok'
GATEWAY_READ_UNAVAILABLE = 'unavailable'
GATEWAY_READ_ERROR = 'error'

DefaultGatewayRead = collections.namedtuple('DefaultGatewayRead', 'outcome gateways detail')


def parse_default_gateways(stdout):
    """Return the gateways named by the output of 'ip route show default'.

    Pure function. A list, not a single value: more than one default route is
    unusual and is exactly the kind of thing worth showing rather than
    collapsing into the first entry.
    """
    gateways = []
    for line in (stdout or '').splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == 'default' and fields[1] == 'via':
            gateways.append(fields[2])
    return gateways


def classify_default_gateway_read(scope, returncode, stdout, stderr):
    """Turn the result of reading an instance's default route into an outcome.

    Pure function. 'The instance did not answer' is not 'the instance has no
    default gateway': a stopped instance, a virtual machine without the incus
    agent and a genuine failure all leave the invariant *unknown*, and reporting
    unknown as a violation would produce false alarms on instances that are
    perfectly fine.
    """
    error_text = (stderr or '').strip()

    if returncode == 0:
        gateways = parse_default_gateways(stdout)
        if not gateways:
            return DefaultGatewayRead(GATEWAY_READ_OK, [], (
                f"'{scope}' has no default route."
            ))
        return DefaultGatewayRead(GATEWAY_READ_OK, gateways, (
            f"'{scope}' routes by default via {', '.join(gateways)}."
        ))

    lowered = error_text.lower()
    if ('not running' in lowered or 'instance is not running' in lowered
            or 'agent' in lowered or 'instance not found' in lowered):
        return DefaultGatewayRead(GATEWAY_READ_UNAVAILABLE, [], (
            f"Cannot read the default route of '{scope}': {error_text}"
        ))

    return DefaultGatewayRead(GATEWAY_READ_ERROR, [], (
        f"Reading the default route of '{scope}' failed (exit {returncode})"
        + (f": {error_text}" if error_text else ".")
    ))


def probe_default_gateway(scope):
    """Read the default gateway of an instance. Read-only.

    Runs 'ip route show default' inside the instance and nothing else.
    """
    argv = incus_exec_argv(scope, ['ip', 'route', 'show', 'default'])
    try:
        result = subprocess.run(argv, capture_output=True, text=True)
    except Exception as e:
        return DefaultGatewayRead(GATEWAY_READ_ERROR, [], (
            f"Could not read the default route of '{scope}': {e}"
        ))

    return classify_default_gateway_read(scope, result.returncode, result.stdout, result.stderr)


def float_invariant_status(mapping, instance, gateway_read, expected_gateway):
    """Decide whether an instance still satisfies the default-gateway invariant.

    Pure function.

    Parameters:
        mapping (dict): the floating-IP mapping, from parse_floating_ip_list.
        instance (dict): the holding instance, or None if no instance holds the
                         private address.
        gateway_read (DefaultGatewayRead): the result of reading its route, or None.
        expected_gateway (str): the address of the gw-float serving the subnet.

    Returns:
        tuple: (status, detail).
    """
    if not (mapping.get('enabled') or mapping.get('active')):
        return FLOAT_INVARIANT_NOT_CHECKED, (
            f"{mapping['public']} is neither enabled nor active: the invariant does "
            f"not apply until it is turned on."
        )

    if instance is None:
        return FLOAT_INVARIANT_UNKNOWN, (
            f"No instance figo knows holds {mapping['private']}, so its default "
            f"gateway cannot be checked."
        )

    if gateway_read is None or gateway_read.outcome != GATEWAY_READ_OK:
        detail = gateway_read.detail if gateway_read else "the route was not read"
        return FLOAT_INVARIANT_UNKNOWN, (
            f"Cannot tell whether '{instance['name']}' satisfies the invariant: {detail}"
        )

    if not gateway_read.gateways:
        return FLOAT_INVARIANT_VIOLATED, (
            f"'{instance['name']}' has no default route, so traffic returning through "
            f"{mapping['public']} cannot reach the gateway."
        )

    if expected_gateway and expected_gateway not in gateway_read.gateways:
        return FLOAT_INVARIANT_VIOLATED, (
            f"'{instance['name']}' routes by default via "
            f"{', '.join(gateway_read.gateways)}, not via the gateway "
            f"{expected_gateway} that serves {mapping['public']}: the return path "
            f"does not pass through the gateway, so the mapping cannot work."
        )

    return FLOAT_INVARIANT_OK, (
        f"'{instance['name']}' routes by default via {expected_gateway}."
    )


def index_instances_by_address(instance_records):
    """Index instances by every private address they hold.

    Pure function. 'Holds' includes the addresses declared in the instance's
    network configuration *and* those recorded as additional (nested VMs, inner
    containers, extra addresses on the NIC): a floating IP can point at any of
    them, and an index built on the first kind alone would report a mapping as
    orphaned when it is not.

    Returns:
        tuple: (index, warnings) where index is {address: [record, ...]}.
    """
    index = {}
    warnings = []

    for record in instance_records or []:
        for address in list(record.get('addresses') or []) + list(record.get('additional') or []):
            address = str(address).split('/')[0]
            holders = index.setdefault(address, [])
            holders.append(record)
            if len(holders) == 2:
                names = ", ".join(f"'{holder['name']}'" for holder in holders)
                warnings.append(
                    f"Address {address} is claimed by more than one instance ({names}): "
                    f"figo reports the first, but the duplicate is worth fixing."
                )

    return index, warnings


def select_gateway_for_remote(gateways, remote):
    """Pick the gateway that serves a remote, and say so when the choice is not unique.

    Pure function, shared by the read and the write paths: a write must act on
    exactly the gateway the reports describe, and two copies of this choice
    would be two chances for them to disagree.

    Returns:
        tuple: (subnet, gateway, warnings). gateway is None when the remote has
               no gateway configured, and the warning says where to declare one.
    """
    serving = {
        subnet: gateway for subnet, gateway in (gateways or {}).items()
        if gateway['scope'].split(':')[0] == remote
    }
    if not serving:
        return None, None, [
            f"No floating-IP gateway is configured on remote '{remote}': declare it "
            f"under network.float_gateways in {CONFIG_FILE}."
        ]

    subnet = sorted(serving)[0]
    gateway = serving[subnet]
    warnings = []
    if len(serving) > 1:
        warnings.append(
            f"Remote '{remote}' has more than one gateway configured; using "
            f"'{gateway['scope']}' for subnet {subnet}."
        )
    return subnet, gateway, warnings


def floating_ip_write_argv(scope, verb, public_ip, note=None, options=()):
    """Build the argv that runs one write verb of the gateway tool in its container.

    Pure function. '--note' goes with 'disable' only: the gateway accepts it
    nowhere else, and a mapping turned off with nobody recording why is the
    case that field exists for.
    """
    command = ['floating-ip', verb, public_ip] + list(options)
    if note is not None:
        if verb != 'disable':
            raise ValueError(f"'{verb}' does not take a note")
        command += ['--note', note]
    return incus_exec_argv(scope, command)


# The verbs that can start serving traffic. They are gated on the invariant;
# 'disable' and 'close', which can only stop traffic, never are -- refusing to
# stop a broken mapping would withhold the remedy from whoever is applying it.
FLOAT_VERBS_THAT_SERVE = ('enable', 'open', 'replace', 'add')


# The verbs that record who owns a mapping and why. They change no rule, so
# they are the only writes figo does not follow with an apply -- and the only
# ones that can be run against a live gateway without a flush window.
FLOAT_VERBS_WITHOUT_RULES = ('label', 'note')


def float_bookkeeping_options(text=None, clear=False):
    """Build the argument of 'label' and 'note': the text, or --clear.

    Pure function. Exactly one of the two, and giving both is an error rather
    than a precedence rule: a bookkeeping field says who owns a mapping and why
    it is the way it is, and clearing one by accident loses a fact nobody
    recorded twice.
    """
    if clear:
        if text:
            raise ValueError("a text and --clear cannot both be given")
        return ['--clear']
    if not text:
        raise ValueError("a text is required unless --clear is given")
    return [text]


def public_ports_of(spec):
    """The public side of a port list, as the operator typed it. Pure function.

    '8443:443' maps public 8443 to private 443, and what the outside network
    sees -- the only thing an upstream constraint can be about -- is the public
    one. Unparseable items are skipped here and refused by the gateway, which
    owns that syntax.
    """
    ports = []
    for item in (spec or '').split(','):
        head = item.strip().split(':')[0].strip()
        if not head:
            continue
        try:
            ports.append(int(head))
        except ValueError:
            continue
    return ports


def float_port_options(tcp=None, udp=None, icmp=None):
    """Build the protocol options of a port verb, in a stable order.

    Pure function. The values are passed to the gateway as they were typed:
    what a port list may contain, and what '--icmp all' means, is the gateway's
    semantics, and a second parser here would be a second thing to keep in
    step with it.
    """
    options = []
    for flag, value in (('--tcp', tcp), ('--udp', udp), ('--icmp', icmp)):
        if value:
            options += [flag, value]
    return options


def find_instance_by_reference(records, reference):
    """Find the instance a mapping should point at, from what the operator typed.

    Pure function. Accepts 'name', 'project.name' or 'remote:project.name', and
    refuses an ambiguous reference instead of picking one: two instances with
    the same name in different projects are ordinary here, and which of them
    gets a public address is not a guess figo may make on its own.

    Returns:
        tuple: (instance, error). Exactly one of the two is not None.
    """
    wanted = reference.rpartition(':')[2]
    project, _, name = wanted.partition('.')
    if not name:
        project, name = None, project

    matches = [
        record for record in records or []
        if record['name'] == name and (project is None or record['project'] == project)
    ]
    if not matches:
        return None, (
            f"No instance '{reference}' on this remote: 'figo instance list' shows "
            f"the ones figo can see."
        )
    if len(matches) > 1:
        names = ", ".join(f"{m['project']}.{m['name']}" for m in matches)
        return None, (
            f"'{reference}' matches more than one instance ({names}): say which one "
            f"as 'project.name'."
        )
    return matches[0], None


def address_in_subnet(addresses, subnet):
    """The addresses of an instance that belong to the gateway's subnet.

    Pure function. An instance can hold several addresses, and only one of them
    can be behind a given gateway; returning the list rather than a choice lets
    the caller refuse an ambiguous case instead of mapping a public address to
    whichever came first.
    """
    network = ipaddress.ip_network(subnet)
    found = []
    for address in addresses or []:
        bare = address.split('/')[0]
        try:
            if ipaddress.ip_address(bare) in network:
                found.append(bare)
        except ValueError:
            continue
    return found


def float_add_options(private, tcp=None, udp=None, icmp=None, label=None,
                      all_ports=False):
    """Build the options of 'add'.

    Pure function. A mapping written with no 'allow' forwards everything to the
    instance, so the gateway requires the whitelist to be stated -- or
    '--all-ports' to be asked for by name. figo refuses the same way rather than
    defaulting: no instance should be opened to the Internet because a flag was
    forgotten.
    """
    if all_ports and (tcp or udp or icmp):
        raise ValueError("--all-ports and a list of ports cannot both be given")

    options = ['--private', private]
    if all_ports:
        options.append('--all-ports')
    else:
        ports = float_port_options(tcp, udp, icmp)
        if not ports:
            raise ValueError(
                "one of --tcp, --udp, --icmp is required, or --all-ports to forward "
                "everything"
            )
        options += ports
    if label:
        options += ['--label', label]
    return options


def float_write_is_noop(verb, row, note=None, text=None, clear=False):
    """True when figo can already tell the write would change nothing.

    Pure function, and deliberately narrow: it answers only where the whole
    effect of the verb is a single value figo has already read -- the boolean of
    'enable' and 'disable', the string of 'label' and 'note'. What 'open' or
    'replace' would change is a list the gateway renders in its own style, and
    deciding here whether that is a no-op would mean re-implementing its
    semantics in a second place.

    A note passed to 'disable' is always a change: it is written even when the
    state already matches, which is the point of recording why.
    """
    if note is not None:
        return False
    if verb == 'enable':
        return bool(row.get('enabled'))
    if verb == 'disable':
        return not row.get('enabled')
    if verb in FLOAT_VERBS_WITHOUT_RULES:
        return row.get(verb) == (None if clear else text)
    return False


def format_allow(mapping):
    """Render what a mapping allows, in one line, for the report after a write."""
    if mapping.get('mode') == 'open':
        return "everything (no allow)"

    parts = []
    for protocol in ('tcp', 'udp'):
        ports = mapping.get(protocol) or []
        if ports:
            parts.append(f"{protocol} " + ", ".join(
                str(pub) if pub == priv else f"{pub}:{priv}" for pub, priv in ports
            ))
    if mapping.get('icmp_all'):
        parts.append("icmp all")
    elif mapping.get('icmp'):
        parts.append("icmp " + ", ".join(mapping['icmp']))

    return "; ".join(parts) or "nothing"


def float_write_decision(verb, public_ip, row, invariant=None, invariant_detail=None,
                         upstream=()):
    """Decide whether figo may run a write verb on a mapping, and say why not.

    Pure function. 'row' is the joined row for that public address, or None when
    the gateway holds no mapping for it.

    Deliberately asymmetric, and this is the point of it: a write that *starts*
    serving traffic is refused when a precondition figo can check itself does
    not hold, while a write that *stops* it never is. Refusing to disable a
    broken mapping would withhold the remedy from the person applying it --
    'disable' is one of the remedies.

    Section 7.3 of the network model: refuse what figo can verify, warn about
    what it cannot. So a violated invariant is a refusal, and an invariant that
    could not be read at all is a warning that lets the write through.

    Returns:
        tuple: (refusals, warnings). No refusals means the write may proceed.
    """
    refusals, warnings = [], []

    for entry, ports in upstream or []:
        if entry.get('effect') != 'blocked':
            continue
        warnings.append(
            format_upstream_warning(entry, ports)
            + f" The mapping will be created and will look correct; it may not be "
            f"reachable from outside. figo cannot test that from inside the testbed: "
            f"every machine here is on the wrong side of the constraint."
        )

    def as_sentence(text):
        """One message is built from two, and the first does not always end in a
        full stop: without this they arrive glued together mid-sentence."""
        text = (text or "").strip()
        if text and text[-1] not in ".!?":
            text += "."
        return text

    def judge_invariant():
        detail = as_sentence(invariant_detail)
        if invariant == FLOAT_INVARIANT_VIOLATED:
            refusals.append(
                f"{detail} Serving more traffic through {public_ip} would "
                f"produce a mapping that looks right and does not work. Fix the "
                f"default route of the instance first, or leave the mapping off."
            )
        elif invariant in (FLOAT_INVARIANT_UNKNOWN, FLOAT_INVARIANT_NOT_CHECKED):
            warnings.append(
                (detail or "The default-gateway invariant could not be checked.")
                + f" figo cannot verify it, so it does not refuse: {public_ip} will be "
                f"turned on and may not work. Check with 'figo net float show {public_ip}'."
            )

    # 'add' reads the presence of a mapping the other way round: for every other
    # verb an absent mapping is the refusal, here it is the precondition.
    if verb == 'add':
        if row is not None:
            refusals.append(
                f"{public_ip} is already mapped to {row.get('private')}. "
                f"'figo net float remove {public_ip}' deletes that mapping, and "
                f"'figo net float replace' changes what it allows."
            )
        else:
            judge_invariant()
        return refusals, warnings

    if row is None:
        refusals.append(
            f"No mapping for {public_ip} on this gateway. 'figo net float list' "
            f"shows the addresses it holds, and 'figo net float add' is the verb "
            f"that creates one."
        )
        return refusals, warnings

    # Opening a port on a mapping that is off starts nothing, so it is not
    # gated: the check belongs to the moment the mapping is turned on.
    serves_now = verb == 'enable' or (
        verb in FLOAT_VERBS_THAT_SERVE and bool(row.get('enabled'))
    )
    if not serves_now:
        return refusals, warnings

    judge_invariant()
    return refusals, warnings


def write_float_mapping(remote, verb, public_ip, options=(), note=None, dry_run=False,
                        text=None, clear=False, instance_reference=None,
                        add_options=None, requested=None):
    """Run one write verb of the gateway on a mapping, then apply and re-read.

    The single write path of figo towards a gateway. It reports what it
    measured afterwards rather than what it asked for: the gateway is the
    authority on its own state.

    What the verbs mean is not re-implemented here. The gateway refuses 'open'
    on a mapping with no 'allow' -- adding the first port would close every
    other one -- and says so, pointing at 'replace'; figo carries that refusal
    to the operator instead of holding a second copy of the rule that could
    drift from it.
    """
    _subnets, gateways, warnings = figo_network()
    subnet, gateway, selection_warnings = select_gateway_for_remote(gateways, remote)
    for warning in warnings + selection_warnings:
        logger.warning(warning)
    if gateway is None:
        return

    probe = probe_gateway(gateway['scope'])
    if probe.outcome != GATEWAY_PROBE_OK:
        logger.error(probe.detail)
        return

    records = collect_instance_records(remote)
    address_index, index_warnings = index_instances_by_address(records)
    for warning in index_warnings:
        logger.warning(warning)
    rows = build_float_rows(probe.mappings, address_index)
    row = next((r for r in rows if r.get('public') == public_ip), None)

    # The invariant has to be read on purpose here. A mapping about to be
    # enabled is off, and the read path skips the route of a mapping that is
    # neither enabled nor active -- exactly the state this command starts from.
    invariant, invariant_detail = None, None
    if row is not None and verb in FLOAT_VERBS_THAT_SERVE:
        instance = row.get('instance')
        gateway_read = None
        if instance and instance['status'] == "Running":
            gateway_read = probe_default_gateway(instance['scope'])
        invariant, invariant_detail = float_invariant_status(
            dict(row, enabled=True), instance, gateway_read, gateway.get('address')
        )

    # 'add' is the one verb whose target is named by the operator rather than
    # read from the gateway: the mapping does not exist yet, so the instance,
    # the private address and the options all have to be resolved first.
    if verb == 'add' and row is None:
        instance, error = find_instance_by_reference(records, instance_reference)
        if error:
            logger.error(error)
            return

        candidates = address_in_subnet(
            list(instance.get('addresses') or []) + list(instance.get('additional') or []),
            subnet
        )
        if len(candidates) != 1:
            logger.error(
                f"'{instance_reference}' holds {len(candidates)} addresses on {subnet} "
                f"({', '.join(candidates) or 'none'}), and a mapping needs exactly one: "
                f"a floating IP points at a single address behind this gateway."
            )
            return
        private = candidates[0]

        try:
            options = float_add_options(private, **(add_options or {}))
        except ValueError as e:
            logger.error(f"'add' cannot be built: {e}.")
            return

        gateway_read = None
        if instance['status'] == "Running":
            gateway_read = probe_default_gateway(instance['scope'])
        invariant, invariant_detail = float_invariant_status(
            {'public': public_ip, 'private': private, 'enabled': True, 'active': False},
            instance, gateway_read, gateway.get('address')
        )

    upstream = []
    if requested and verb in FLOAT_VERBS_THAT_SERVE:
        policy, policy_warnings = parse_upstream_policy(load_figo_config())
        for warning in policy_warnings:
            logger.warning(warning)
        for protocol in ('tcp', 'udp'):
            upstream += upstream_constraints(
                policy, public_ip, protocol, public_ports_of(requested.get(protocol))
            )
        if requested.get('icmp'):
            upstream += upstream_constraints(policy, public_ip, 'icmp')

    refusals, write_warnings = float_write_decision(
        verb, public_ip, row, invariant, invariant_detail, upstream
    )
    for warning in write_warnings:
        logger.warning(warning)
    if refusals:
        for refusal in refusals:
            logger.error(refusal)
        return

    if row is not None and float_write_is_noop(verb, row, note, text=text, clear=clear):
        if verb in FLOAT_VERBS_WITHOUT_RULES:
            current = row.get(verb)
            logger.info(
                f"The {verb} of {public_ip} is already "
                + (f"'{current}'" if current else "empty")
                + ": nothing to do."
            )
        else:
            state = 'enabled' if verb == 'enable' else 'disabled'
            logger.info(
                f"{public_ip} is already {state}: nothing to do, and nothing applied."
            )
        return

    argv = floating_ip_write_argv(gateway['scope'], verb, public_ip, note, options)
    apply_argv = incus_exec_argv(gateway['scope'], ['floating-ip', 'apply'])

    changes_rules = verb not in FLOAT_VERBS_WITHOUT_RULES

    if dry_run:
        logger.info("Dry run: nothing was changed. figo would run, in this order:")
        logger.info("  " + " ".join(argv))
        if changes_rules:
            logger.info("  " + " ".join(apply_argv))
        else:
            logger.info(f"  (and no apply: '{verb}' changes no rule)")
        return

    result = subprocess.run(argv, capture_output=True, text=True)
    if (result.stdout or '').strip():
        # stdout is block-buffered when it is a pipe and stderr is not, so
        # without this flush the summary logged below reaches the reader before
        # the gateway output it summarises. Measured on the real gateway.
        print(result.stdout.rstrip(), flush=True)
    if result.returncode != 0:
        logger.error(
            f"The gateway refused '{verb} {public_ip}': "
            f"{(result.stderr or result.stdout or '').strip()}. Nothing was applied, "
            f"so its rules are unchanged."
        )
        return

    if changes_rules:
        applied = subprocess.run(apply_argv, capture_output=True, text=True)
    else:
        applied = None
    if applied is not None and applied.returncode != 0:
        logger.error(
            f"The configuration was changed but 'floating-ip apply' failed: "
            f"{(applied.stderr or applied.stdout or '').strip()}. The gateway now asks "
            f"for something its rules do not do -- run 'floating-ip apply' inside "
            f"'{gateway['scope']}', and see 'figo net float show {public_ip}'."
        )
        return

    after = probe_gateway(gateway['scope'])
    if after.outcome != GATEWAY_PROBE_OK:
        logger.warning(
            f"The change was applied but re-reading the gateway failed: {after.detail}"
        )
        return

    new_row = next((m for m in after.mappings if m.get('public') == public_ip), None)

    if verb == 'remove':
        if new_row is not None:
            logger.error(
                f"{public_ip} is still on the gateway after 'remove', which should not "
                f"happen: read it with 'figo net float show {public_ip}'."
            )
        else:
            logger.info(
                f"{public_ip} is gone. {len(after.mappings)} mapping(s) left on the "
                f"gateway, rules reinstalled."
            )
        return

    if new_row is None:
        logger.warning(
            f"The change was applied but {public_ip} is no longer in the gateway's "
            f"answer, which should not happen: read it with 'figo net float list'."
        )
        return

    if not changes_rules:
        value = new_row.get(verb)
        logger.info(
            f"The {verb} of {public_ip} is now "
            + (f"'{value}'." if value else "empty.")
            + " No rule changed, so nothing was applied."
        )
        return

    logger.info(
        f"{public_ip} now allows {format_allow(new_row)} -- "
        f"enabled={new_row['enabled']}, active={new_row['active']}, "
        f"rules {format_rule_drift(new_row.get('drift'))}."
    )


def build_float_rows(mappings, address_index):
    """Join the gateway's mappings with the instances figo knows.

    Pure function. Every mapping produces a row, including one whose private
    address belongs to no instance figo can see: an orphaned mapping is a fact
    about the gateway, and dropping it would hide it.

    Returns:
        list: one dict per mapping, with the mapping fields plus 'instance'.
    """
    rows = []
    for mapping in mappings or []:
        holders = address_index.get(mapping.get('private')) or []
        row = dict(mapping)
        row['instance'] = holders[0] if holders else None
        rows.append(row)
    return rows


def collect_instance_records(remote):
    """Collect what figo knows about the instances of a remote. Read-only.

    Returns:
        list: dicts with name, project, scope, status, type, addresses, additional.
    """
    records = []

    for project_name, instance in iterator_over_instances(remote):
        config = getattr(instance, 'config', None) or {}
        # get_ip_device_pairs reads a mapping; a pylxd object exposes .config.
        addresses = get_ip_addresses({'config': config, 'name': instance.name})
        additional = [entry['ip'] for entry in get_additional_ips_from_config(config)]

        records.append({
            'name': instance.name,
            'project': project_name,
            'scope': f"{remote}:{project_name}.{instance.name}",
            'status': instance.status,
            'type': 'vm' if instance.type == "virtual-machine" else 'container',
            'addresses': addresses,
            'additional': additional,
        })

    return records


#############################################
###### figo net command functions       #####
#############################################

def figo_network(config=None):
    """Return the network view figo works with: subnets, gateways, warnings.

    Assembled from the remotes figo already knows and the deployment
    configuration, which adds only what cannot be derived.
    """
    config = load_figo_config() if config is None else config
    network, warnings = parse_network_config(config)
    subnets = network_subnets(REMOTE_TO_IP_INFO_MAP, network)
    return subnets, network['gateways'], warnings


def show_gateway_list(extend=False):
    """List the subnets figo knows and the floating-IP gateway serving each.

    Reads configuration only: no remote is contacted. The STATUS column is the
    outcome of the resolution of Section 3.4, so a subnet without a gateway says
    whether one can be deployed or not.
    """
    subnets, gateways, warnings = figo_network()

    COLS = [('SUBNET', 19), ('HOST', 11), ('PUBLIC VLAN', 12), ('REMOTES', 18),
            ('GATEWAY', 26), ('ADDRESS', 15), ('STATUS', 14)]
    add_header_line_to_output(COLS)

    for subnet in sorted(subnets, key=lambda name: ipaddress.ip_network(name)):
        entry = subnets[subnet]
        # Resolve from an address inside the subnet: the resolution is the same
        # for every address it contains, and this keeps one code path.
        probe_address = str(next(ipaddress.ip_network(subnet).hosts()))
        resolution = resolve_float_gateway(probe_address, subnets, gateways)
        gateway = gateways.get(subnet) or {}
        public_vlan = entry.get('public_vlan')
        add_row_to_output(COLS, [
            subnet,
            entry.get('host') or "-",
            {True: "yes", False: "no", None: "unknown"}[public_vlan],
            ", ".join(entry.get('remotes') or []) or "-",
            gateway.get('scope') or "-",
            gateway.get('address') or "-",
            resolution.outcome,
        ])

    flush_output(extend=extend)

    if not subnets:
        logger.info("No subnet is known: figo derives them from the remotes.")
    for warning in warnings:
        logger.warning(warning)


def show_gateway_status(remote=None, extend=False):
    """Query each configured gw-float and report what it holds. Read-only.

    Args:
    - remote: restrict to the gateways hosted on this remote.
    - extend: adapt the column width to the content.
    """
    subnets, gateways, warnings = figo_network()

    selected = {
        subnet: gateway for subnet, gateway in gateways.items()
        if remote is None or gateway['scope'].split(':')[0] == remote
    }

    if not selected:
        where = f" on remote '{remote}'" if remote else ""
        logger.info(
            f"No floating-IP gateway is configured{where}: declare it under "
            f"network.float_gateways in {CONFIG_FILE}, or deploy one."
        )
        return

    # DRIFT and RULES are two different questions: DRIFT is the configuration
    # against the interface, RULES the configuration against the installed
    # iptables rules, as the gateway reports them. A gateway that does not
    # report the second shows '-' rather than 0.
    COLS = [('SUBNET', 19), ('GATEWAY', 26), ('STATE', 14), ('MAPPINGS', 9),
            ('ENABLED', 8), ('ACTIVE', 7), ('DRIFT', 6), ('RULES', 6)]
    add_header_line_to_output(COLS)

    probes = {}
    for subnet in sorted(selected, key=lambda name: ipaddress.ip_network(name)):
        gateway = selected[subnet]
        probe = probe_gateway(gateway['scope'])
        probes[subnet] = probe

        enabled = [m for m in probe.mappings if m['enabled']]
        active = [m for m in probe.mappings if m['active']]
        drift = [m for m in probe.mappings if m['enabled'] != m['active']]
        reported, rule_drift = summarize_rule_drift(probe.mappings)

        add_row_to_output(COLS, [
            subnet,
            gateway['scope'],
            probe.outcome,
            str(len(probe.mappings)) if probe.outcome == GATEWAY_PROBE_OK else "-",
            str(len(enabled)) if probe.outcome == GATEWAY_PROBE_OK else "-",
            str(len(active)) if probe.outcome == GATEWAY_PROBE_OK else "-",
            str(len(drift)) if probe.outcome == GATEWAY_PROBE_OK else "-",
            (str(rule_drift) if reported else "-")
            if probe.outcome == GATEWAY_PROBE_OK else "-",
        ])

    flush_output(extend=extend)

    for subnet, probe in probes.items():
        if probe.outcome != GATEWAY_PROBE_OK:
            logger.error(probe.detail)
            continue
        for mapping in probe.mappings:
            if mapping['enabled'] != mapping['active']:
                logger.warning(
                    f"Drift on '{selected[subnet]['scope']}': {mapping['public']} -> "
                    f"{mapping['private']} is enabled={mapping['enabled']} but "
                    f"active={mapping['active']} -- what the configuration asks for "
                    f"is not what is on the interface."
                )
            drift = mapping.get('drift')
            if drift and not drift.get('consistent'):
                logger.warning(
                    f"Rule drift on '{selected[subnet]['scope']}': {mapping['public']} "
                    f"-> {mapping['private']} has {drift['missing']} rule(s) missing "
                    f"and {drift['extra']} extra -- the configuration and the "
                    f"installed rules disagree. 'floating-ip apply' on the gateway "
                    f"reinstalls them."
                )
        if probe.mappings and not summarize_rule_drift(probe.mappings)[0]:
            logger.info(
                f"The gateway '{selected[subnet]['scope']}' does not report rule "
                f"drift: RULES is shown as '-' because nobody measured it, not "
                f"because the rules are right. Upgrading the gateway fills it in."
            )

    for warning in warnings:
        logger.warning(warning)


def gather_float_state(remote):
    """Read the floating-IP state of a remote and join it with what figo knows.

    Read-only throughout: 'floating-ip list' on the gateway, the instance list
    through the API, and 'ip route show default' inside the instances that hold
    a live mapping. Nothing is applied, nothing is written.

    Returns:
        tuple: (rows, gateway_address, probe, warnings). rows carry the mapping,
               the holding instance and the invariant verdict.
    """
    subnets, gateways, warnings = figo_network()

    _subnet, gateway, selection_warnings = select_gateway_for_remote(gateways, remote)
    warnings = warnings + selection_warnings
    if gateway is None:
        return [], None, None, warnings

    probe = probe_gateway(gateway['scope'])
    if probe.outcome != GATEWAY_PROBE_OK:
        return [], gateway.get('address'), probe, warnings

    records = collect_instance_records(remote)
    address_index, index_warnings = index_instances_by_address(records)
    warnings.extend(index_warnings)

    rows = build_float_rows(probe.mappings, address_index)

    for row in rows:
        instance = row['instance']
        gateway_read = None
        # The route is read only where the verdict can differ: a mapping that is
        # neither enabled nor active does not need it, and an instance that is not
        # running cannot answer.
        if (row.get('enabled') or row.get('active')) and instance and instance['status'] == "Running":
            gateway_read = probe_default_gateway(instance['scope'])
        row['invariant'], row['invariant_detail'] = float_invariant_status(
            row, instance, gateway_read, gateway.get('address')
        )

    return rows, gateway.get('address'), probe, warnings


def format_rule_drift(drift):
    """Render one mapping's rule drift for a human, keeping unknown distinct."""
    if drift is None:
        return "not reported"
    if drift.get('consistent'):
        return "consistent"
    return f"{drift.get('missing', 0)} missing, {drift.get('extra', 0)} extra"


def float_row_as_dict(row):
    """Render one row for --json: no objects, no tuples, stable key names."""
    instance = row.get('instance') or {}
    return {
        'public': row.get('public'),
        'private': row.get('private'),
        'enabled': row.get('enabled'),
        'active': row.get('active'),
        'mode': row.get('mode'),
        'tcp': [{'pub_port': pub, 'priv_port': priv} for pub, priv in row.get('tcp') or []],
        'udp': [{'pub_port': pub, 'priv_port': priv} for pub, priv in row.get('udp') or []],
        'icmp': row.get('icmp') or [],
        'icmp_all': bool(row.get('icmp_all')),
        'label': row.get('label'),
        'note': row.get('note'),
        'drift': row.get('drift'),
        'instance': instance.get('name'),
        'project': instance.get('project'),
        'status': instance.get('status'),
        'invariant': row.get('invariant'),
        'invariant_detail': row.get('invariant_detail'),
    }


def show_float_list(remote, as_json=False, extend=False):
    """List the floating IPs of a remote, joined with the instances holding them."""
    rows, _gateway_address, probe, warnings = gather_float_state(remote)

    if probe is not None and probe.outcome != GATEWAY_PROBE_OK:
        logger.error(probe.detail)
        return

    if as_json:
        print(json.dumps([float_row_as_dict(row) for row in rows], indent=2))
    else:
        COLS = [('PUBLIC IP', 16), ('PRIVATE IP', 15), ('INSTANCE', 16), ('PROJECT', 18),
                ('STATE', 8), ('ENABLED', 8), ('ACTIVE', 7), ('INVARIANT', 12)]
        add_header_line_to_output(COLS)
        for row in rows:
            instance = row.get('instance') or {}
            add_row_to_output(COLS, [
                row.get('public') or "-",
                row.get('private') or "-",
                instance.get('name') or "-",
                instance.get('project') or "-",
                (instance.get('status') or "-")[:3].lower(),
                "yes" if row.get('enabled') else "no",
                "yes" if row.get('active') else "no",
                row.get('invariant') or "-",
            ])
        flush_output(extend=extend)

        if not rows:
            logger.info(f"The gateway on '{remote}' holds no floating-IP mapping.")

    # The point of the join is what it finds wrong; say it out loud rather than
    # leaving it to whoever reads a column.
    for row in rows:
        if row.get('enabled') != row.get('active'):
            logger.warning(
                f"Drift on {row['public']}: enabled={row['enabled']} but "
                f"active={row['active']} -- the configuration and the interface "
                f"disagree, someone edited without applying."
            )
        if row.get('invariant') == FLOAT_INVARIANT_VIOLATED:
            logger.warning(row['invariant_detail'])
        elif row.get('invariant') == FLOAT_INVARIANT_UNKNOWN:
            logger.info(row['invariant_detail'])

    for warning in warnings:
        logger.warning(warning)


def show_float_show(remote, public_ip, as_json=False, extend=False):
    """Show one floating IP in full: ports, holder, invariant."""
    rows, _gateway_address, probe, warnings = gather_float_state(remote)

    if probe is not None and probe.outcome != GATEWAY_PROBE_OK:
        logger.error(probe.detail)
        return

    matching = [row for row in rows if row.get('public') == public_ip]
    if not matching:
        known = ", ".join(sorted(row.get('public') or "" for row in rows)) or "none"
        logger.error(
            f"No mapping for {public_ip} on the gateway of '{remote}'. Known: {known}."
        )
        return

    row = matching[0]
    if as_json:
        print(json.dumps(float_row_as_dict(row), indent=2))
        return

    instance = row.get('instance') or {}
    ports = ", ".join(
        f"{pub}->{priv}" for pub, priv in row.get('tcp') or []
    ) or "-"
    udp_ports = ", ".join(
        f"{pub}->{priv}" for pub, priv in row.get('udp') or []
    ) or "-"

    COLS = [('FIELD', 18), ('VALUE', 62)]
    add_header_line_to_output(COLS)
    for field, value in [
        ('public ip', row.get('public') or "-"),
        ('private ip', row.get('private') or "-"),
        ('instance', instance.get('name') or "-"),
        ('project', instance.get('project') or "-"),
        ('state', instance.get('status') or "-"),
        ('enabled', "yes" if row.get('enabled') else "no"),
        ('active', "yes" if row.get('active') else "no"),
        ('mode', row.get('mode') or "-"),
        ('label', row.get('label') or "-"),
        ('note', row.get('note') or "-"),
        ('rules', format_rule_drift(row.get('drift'))),
        ('tcp', ports),
        ('udp', udp_ports),
        ('icmp', "all" if row.get('icmp_all')
                 else (", ".join(row.get('icmp') or []) or "-")),
        ('invariant', row.get('invariant') or "-"),
    ]:
        add_row_to_output(COLS, [field, str(value)])
    flush_output(extend=extend)

    print()
    print(row.get('invariant_detail') or "")

    for warning in warnings:
        logger.warning(warning)


def create_net_parser(subparsers):
    net_parser = subparsers.add_parser(
        "net",
        help="Inspect the network: floating-IP gateways and public IP mappings.",
        description="Report on the floating-IP gateways serving the instance subnets,\n"
                    "and on the public IP mappings they hold. Read-only in this release.",
        epilog="Use 'figo net <command> -h' for detailed help on a specific command.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    net_subparsers = net_parser.add_subparsers(dest="net_command")

    gateway_parser = net_subparsers.add_parser(
        "gateway",
        help="Floating-IP gateways: which subnet each one serves, and its state.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    gateway_subparsers = gateway_parser.add_subparsers(dest="gateway_command")

    gateway_list_parser = gateway_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List the known subnets and the gateway serving each one.",
        description="List every subnet figo knows, derived from the remotes, with the\n"
                    "floating-IP gateway serving it and whether one could be deployed.\n"
                    "Reads configuration only: no remote is contacted.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo net gateway list\n"
               "  figo net gateway list --extend"
    )
    gateway_list_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit the content"
    )

    gateway_status_parser = gateway_subparsers.add_parser(
        "status",
        help="Query the configured gateways and report the mappings they hold.",
        description="Ask each configured gw-float for its floating-IP mappings and report\n"
                    "how many are enabled, how many are active, where the two differ, and\n"
                    "how many have rules that do not match the configuration. A gateway too\n"
                    "old to report that last one shows '-' rather than 0.\n"
                    "Read-only: it runs 'floating-ip list', never 'apply'.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo net gateway status\n"
               "  figo net gateway status blade3"
    )
    gateway_status_parser.add_argument(
        "remote",
        nargs="?",
        default=None,
        help="Restrict to the gateways hosted on this remote."
    )
    gateway_status_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit the content"
    )

    float_parser = net_subparsers.add_parser(
        "float",
        help="Public (floating) IP mappings held by the gateways.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    float_subparsers = float_parser.add_subparsers(dest="float_command")

    float_list_parser = float_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List the floating IPs and the instances holding them.",
        description="Read the mappings from the gateway serving a remote and join them\n"
                    "with what figo knows: holding instance, project, state. Reports\n"
                    "'enabled' (what the configuration asks) against 'active' (what is on\n"
                    "the interface), and whether each instance still satisfies the\n"
                    "default-gateway invariant. Read-only.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo net float list blade3\n"
               "  figo net float list blade3 --json"
    )
    float_list_parser.add_argument(
        "remote", nargs="?", default="blade3",
        help="Remote whose gateway to read. Defaults to 'blade3'."
    )
    float_list_parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Emit JSON instead of a table"
    )
    float_list_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit the content"
    )

    float_show_parser = float_subparsers.add_parser(
        "show",
        aliases=["s"],
        help="Show one floating IP in full.",
        description="Ports, holding instance and invariant status of a single mapping.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo net float show 160.80.105.35\n"
               "  figo net float show 160.80.105.35 --json"
    )
    float_show_parser.add_argument("public_ip", help="The public address of the mapping")
    float_show_parser.add_argument(
        "-r", "--remote", default="blade3",
        help="Remote whose gateway to read. Defaults to 'blade3'."
    )
    float_show_parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Emit JSON instead of a table"
    )
    float_show_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit the content"
    )

    float_enable_parser = float_subparsers.add_parser(
        "enable",
        help="Turn a mapping on, and apply.",
        description="Ask the gateway to enable a mapping, then reinstall its rules.\n"
                    "Refuses if the instance holding the private address does not route\n"
                    "by default through that gateway (3.3): the mapping would look right\n"
                    "and not work. Warns and proceeds when figo cannot check, because a\n"
                    "check it could not make is not a reason to block the operator.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo net float enable 160.80.105.43\n"
               "  figo net float enable 160.80.105.43 --dry-run"
    )
    float_enable_parser.add_argument("public_ip", help="The public address of the mapping")
    float_enable_parser.add_argument(
        "-r", "--remote", default="blade3",
        help="Remote whose gateway holds the mapping. Defaults to 'blade3'."
    )
    float_enable_parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print the commands figo would run in the gateway, and change nothing"
    )

    float_disable_parser = float_subparsers.add_parser(
        "disable",
        help="Turn a mapping off, and apply.",
        description="Ask the gateway to disable a mapping, then reinstall its rules.\n"
                    "Never refused on the default-gateway invariant: turning a mapping\n"
                    "off is one of the remedies for a broken one.\n"
                    "--note records why, in the mapping itself.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo net float disable 160.80.105.43\n"
               "  figo net float disable 160.80.105.43 --note \"upstream has not allowed 22\""
    )
    float_disable_parser.add_argument("public_ip", help="The public address of the mapping")
    float_disable_parser.add_argument(
        "--note", default=None,
        help="Record why the mapping is being turned off, in the mapping itself"
    )
    float_disable_parser.add_argument(
        "-r", "--remote", default="blade3",
        help="Remote whose gateway holds the mapping. Defaults to 'blade3'."
    )
    float_disable_parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print the commands figo would run in the gateway, and change nothing"
    )

    for verb, summary, detail in (
        ("open", "Add ports to an existing mapping, and apply.",
         "Add ports or ICMP types to what a mapping already allows, then\n"
         "reinstall its rules. The gateway refuses to open the first port of a\n"
         "mapping that has no 'allow': that would create a whitelist and close\n"
         "everything else, and it points at 'replace' instead."),
        ("close", "Remove ports from an existing mapping, and apply.",
         "Remove ports or ICMP types from what a mapping allows, then reinstall\n"
         "its rules. Never refused on the default-gateway invariant: closing a\n"
         "port only takes traffic away."),
        ("replace", "Set the whole port list of a mapping, and apply.",
         "Replace what a mapping allows with exactly what is given, then\n"
         "reinstall its rules. This is the verb that may create a whitelist on a\n"
         "mapping that had none, which is why 'open' refuses to."),
    ):
        port_parser = float_subparsers.add_parser(
            verb,
            help=summary,
            description=detail + "\n"
                        "At least one of --tcp, --udp or --icmp is required.",
            formatter_class=argparse.RawTextHelpFormatter,
            epilog="Examples:\n"
                   f"  figo net float {verb} 160.80.105.36 --tcp 8080,8443:443\n"
                   f"  figo net float {verb} 160.80.105.36 --icmp echo-request --dry-run"
        )
        port_parser.add_argument("public_ip", help="The public address of the mapping")
        port_parser.add_argument(
            "--tcp", default=None,
            help="Comma-separated TCP ports, '8080' or '8443:443' to remap"
        )
        port_parser.add_argument(
            "--udp", default=None, help="Comma-separated UDP ports"
        )
        port_parser.add_argument(
            "--icmp", default=None,
            help="ICMP type names, or 'all'; 'none' is accepted by replace only"
        )
        port_parser.add_argument(
            "-r", "--remote", default="blade3",
            help="Remote whose gateway holds the mapping. Defaults to 'blade3'."
        )
        port_parser.add_argument(
            "--dry-run", action="store_true", dest="dry_run",
            help="Print the commands figo would run in the gateway, and change nothing"
        )

    for verb, what in (
        ("label", "who owns a mapping"),
        ("note", "why a mapping is the way it is"),
    ):
        book_parser = float_subparsers.add_parser(
            verb,
            help=f"Record {what}.",
            description=f"Record {what}, in the mapping itself.\n"
                        "Until these fields existed the only record was a YAML comment,\n"
                        "which no program could read and any rewrite could lose.\n"
                        "Changes no rule, so nothing is applied and no traffic is touched.",
            formatter_class=argparse.RawTextHelpFormatter,
            epilog="Examples:\n"
                   f"  figo net float {verb} 160.80.105.36 \"web-team\"\n"
                   f"  figo net float {verb} 160.80.105.36 --clear"
        )
        book_parser.add_argument("public_ip", help="The public address of the mapping")
        book_parser.add_argument(
            "text", nargs="?", default=None, help=f"The {verb} to record"
        )
        book_parser.add_argument(
            "--clear", action="store_true", help=f"Remove the {verb} instead"
        )
        book_parser.add_argument(
            "-r", "--remote", default="blade3",
            help="Remote whose gateway holds the mapping. Defaults to 'blade3'."
        )
        book_parser.add_argument(
            "--dry-run", action="store_true", dest="dry_run",
            help="Print the command figo would run in the gateway, and change nothing"
        )

    float_add_parser = float_subparsers.add_parser(
        "add",
        help="Create a mapping towards an instance, and apply.",
        description="Create a floating-IP mapping towards an instance, then install\n"
                    "its rules. The public address is required and never guessed:\n"
                    "figo knows the private subnets, but which public addresses are\n"
                    "free is recorded nowhere, and there is more than one pool.\n"
                    "One of --tcp, --udp, --icmp is required, or --all-ports asked for\n"
                    "by name: a mapping written without them forwards everything.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo net float add myinst 160.80.105.44 --tcp 80,443\n"
               "  figo net float add figo-x.myinst 160.80.105.44 --all-ports --dry-run"
    )
    float_add_parser.add_argument(
        "instance", help="Instance the mapping points at: 'name' or 'project.name'"
    )
    float_add_parser.add_argument("public_ip", help="The public address to map")
    float_add_parser.add_argument("--tcp", default=None, help="Comma-separated TCP ports")
    float_add_parser.add_argument("--udp", default=None, help="Comma-separated UDP ports")
    float_add_parser.add_argument(
        "--icmp", default=None, help="ICMP type names, or 'all'"
    )
    float_add_parser.add_argument(
        "--all-ports", action="store_true", dest="all_ports",
        help="Forward everything to the instance, asked for by name"
    )
    float_add_parser.add_argument("--label", default=None, help="Who owns this mapping")
    float_add_parser.add_argument(
        "-r", "--remote", default="blade3",
        help="Remote whose gateway will hold the mapping. Defaults to 'blade3'."
    )
    float_add_parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print the commands figo would run in the gateway, and change nothing"
    )

    float_remove_parser = float_subparsers.add_parser(
        "remove",
        help="Delete a mapping, and apply.",
        description="Delete a floating-IP mapping and reinstall the rules. The gateway\n"
                    "takes the comment lines above the mapping with it -- left behind\n"
                    "they would sit above the next one and name the wrong owner -- and\n"
                    "leaves a backup.\n"
                    "Never refused on the default-gateway invariant: removing a mapping\n"
                    "only takes traffic away.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo net float remove 160.80.105.44\n"
               "  figo net float remove 160.80.105.44 --dry-run"
    )
    float_remove_parser.add_argument("public_ip", help="The public address of the mapping")
    float_remove_parser.add_argument(
        "-r", "--remote", default="blade3",
        help="Remote whose gateway holds the mapping. Defaults to 'blade3'."
    )
    float_remove_parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print the commands figo would run in the gateway, and change nothing"
    )

    return net_parser


def create_gpu_parser(subparsers):
    gpu_parser = subparsers.add_parser(
        "gpu",
        help="Manage GPUs and GPU profiles across instances and remotes.",
        description="Perform various GPU management tasks, such as checking status, listing profiles, "
                    "adding or removing GPU profiles from instances, and retrieving PCI addresses of available GPUs.\n"
                    "Supports scoped operations with remote and project options.",
        epilog="Use 'figo gpu <command> -h' for detailed help on a specific command.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    gpu_subparsers = gpu_parser.add_subparsers(dest="gpu_command")

    # GPU Status with extended column option and optional remote
    status_gpu_parser = gpu_subparsers.add_parser(
        "status",
        help="Show the current status of GPUs, including their availability and usage.",
        description="Show the GPUs of a remote, one row per card: which profiles offer it to\n"
                    "containers and to VMs, how many running containers use it, how many\n"
                    "instances are assigned to it in any state, and the VM holding it, if any.\n"
                    "If no remote is specified, defaults to 'local'.\n"
                    "Use -i/--instances to list the instances of each card, and -e/--extend to\n"
                    "adjust column width for better readability.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo gpu status\n"
               "  figo gpu status my_remote:\n"
               "  figo gpu status my_remote: -i\n"
               "  figo gpu status --extend"
    )
    status_gpu_parser.add_argument(
        "remote",
        nargs="?",
        default="local",
        help="Specify the remote name for the GPU status. Defaults to 'local'."
    )
    status_gpu_parser.add_argument(
        "-e", "--extend", action="store_true", help="Extend column width to fit the content"
    )
    status_gpu_parser.add_argument(
        "-i", "--instances", action="store_true",
        help="List, under the table, the instances assigned to each card"
    )

    # List GPU profiles with optional remote
    list_gpu_parser = gpu_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List GPU profiles configured in the system.",
        description="List all GPU profiles configured on a specified remote.\n"
                    "If no remote is specified, defaults to 'local'.\n"
                    "Use the -e/--extend option to adjust column width for better readability.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo gpu list\n"
               "  figo gpu list my_remote:\n"
               "  figo gpu list --extend"
    )
    list_gpu_parser.add_argument(
        "remote",
        nargs="?",
        default="local",
        help="Specify the remote name for the GPU list. Defaults to 'local'."
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
        "-a", "--all", action="store_true", help="Remove all GPU profiles from the instance."
    )

    # PCI Address command
    pci_addr_parser = gpu_subparsers.add_parser(
        "pci_addr",
        help="Display PCI addresses of GPUs available on a specific remote.",
        description="Display PCI addresses of GPUs available on a specified remote.\n"
                    "If no remote is specified, it defaults to 'local'.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo gpu pci_addr my_remote\n"
               "  figo gpu pci_addr\n"
    )
    pci_addr_parser.add_argument(
        "remote",
        nargs="?",
        default="local",
        help="Specify the remote name for displaying GPU PCI addresses. Defaults to 'local'."
    )

    # Aliases for main parser
    subparsers._name_parser_map["gp"] = gpu_parser
    subparsers._name_parser_map["g"] = gpu_parser

    return gpu_parser



def handle_net_command(args, parser_dict):
    """Handle subcommands of 'figo net'. Read-only in this release."""

    def fix_remote_name(remote_name):
        return remote_name.rstrip(':') if remote_name else remote_name

    if not args.net_command:
        parser_dict['net_parser'].print_help()
        return

    if args.net_command == "gateway":
        if not args.gateway_command:
            parser_dict['net_parser'].print_help()
        elif args.gateway_command in ["list", "l"]:
            show_gateway_list(extend=args.extend)
        elif args.gateway_command == "status":
            show_gateway_status(remote=fix_remote_name(args.remote), extend=args.extend)

    elif args.net_command == "float":
        if not args.float_command:
            parser_dict['net_parser'].print_help()
        elif args.float_command in ["list", "l"]:
            show_float_list(fix_remote_name(args.remote), as_json=args.as_json,
                            extend=args.extend)
        elif args.float_command in ["show", "s"]:
            show_float_show(fix_remote_name(args.remote), args.public_ip,
                            as_json=args.as_json, extend=args.extend)
        elif args.float_command in ["enable", "disable"]:
            write_float_mapping(fix_remote_name(args.remote), args.float_command,
                                args.public_ip,
                                note=getattr(args, 'note', None),
                                dry_run=args.dry_run)
        elif args.float_command == "add":
            write_float_mapping(
                fix_remote_name(args.remote), "add", args.public_ip,
                instance_reference=args.instance,
                add_options={'tcp': args.tcp, 'udp': args.udp, 'icmp': args.icmp,
                             'label': args.label, 'all_ports': args.all_ports},
                requested={'tcp': args.tcp, 'udp': args.udp, 'icmp': args.icmp},
                dry_run=args.dry_run)
        elif args.float_command == "remove":
            write_float_mapping(fix_remote_name(args.remote), "remove", args.public_ip,
                                dry_run=args.dry_run)
        elif args.float_command in ["label", "note"]:
            try:
                options = float_bookkeeping_options(args.text, args.clear)
            except ValueError as e:
                logger.error(
                    f"'{args.float_command}' takes a text or --clear: {e}."
                )
            else:
                write_float_mapping(fix_remote_name(args.remote), args.float_command,
                                    args.public_ip, options=options,
                                    text=args.text, clear=args.clear,
                                    dry_run=args.dry_run)
        elif args.float_command in ["open", "close", "replace"]:
            options = float_port_options(args.tcp, args.udp, args.icmp)
            requested = {'tcp': args.tcp, 'udp': args.udp, 'icmp': args.icmp}
            if not options:
                logger.error(
                    f"'{args.float_command}' needs at least one of --tcp, --udp or "
                    f"--icmp: with none of them it would ask the gateway to change "
                    f"nothing."
                )
            else:
                write_float_mapping(fix_remote_name(args.remote), args.float_command,
                                    args.public_ip, options=options,
                                    requested=requested, dry_run=args.dry_run)


def handle_gpu_command(args, parser_dict):
    """
    Handle subcommands for managing GPUs, including status, list, add, and remove.
    """

    def fix_remote_name(remote_name):
        """Fix the remote name by removing any trailing ':'."""
        return remote_name.rstrip(':')
    
    if not args.gpu_command:
        parser_dict['gpu_parser'].print_help()
    elif args.gpu_command == "status":
        remote = args.remote
        remote = fix_remote_name(remote)

        client = get_remote_client(remote)
        if client:
            show_gpu_status(remote, extend=args.extend, instances=args.instances)
        else:
            logger.error(f"Failed to retrieve GPU status for remote '{remote}'.")
    elif args.gpu_command in ["list", "l"]:
        remote = args.remote
        remote = fix_remote_name(remote)

        client = get_remote_client(remote)
        if client:
            list_gpu_profiles(client, extend=args.extend)
        else:
            logger.error(f"Failed to list GPU profiles for remote '{remote}'.")

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
            my_result = add_gpu_profile(instance, remote=remote, project=project)
            if my_result:
                logger.info(f"Successfully added GPU profile to instance '{instance}'.")
            else:
                logger.error(f"Failed to add GPU profile to instance '{instance}'.")

        elif args.gpu_command == "remove":
            # Parse the instance scope and validate
            remote, project, instance = parse_instance_scope(
                args.instance_name, provided_remote=args.remote, provided_project=args.project
            )
            if remote is None or project is None or instance is None:
                logger.error("Error: Invalid instance name.")
                return  # Error already printed in parse_instance_scope

            # Proceed with removing the GPU profile(s)
            if args.all:
                my_result = remove_gpu_all_profiles(instance, remote=remote, project=project)
            else:
                my_result = remove_gpu_profile(instance, remote=remote, project=project)

            if my_result:
                logger.info(f"Successfully removed GPU profile(s) from instance '{instance}'.")
            else:
                logger.error(f"Failed to remove GPU profile(s) from instance '{instance}'.")

        elif args.gpu_command == "pci_addr":
            # Handle the remote argument and normalize input
            remote = args.remote
            if remote and remote.endswith(":"):
                remote = remote[:-1]  # Remove trailing colon for consistency
            remote = remote or "local"  # Default to 'local' if not specified

            # Validate the remote name
            if not check_remote_name(remote):
                logger.error(f"Error: Invalid remote name '{remote}'.")
                return

            # Retrieve PCI addresses for GPUs available on the remote. The reason of
            # a failure -- unreachable, not configured, command error -- has already
            # been reported by the discovery: a generic line on top would bury it.
            show_gpu_pci_addresses(remote)



#############################################
###### figo profile command CLI #############
#############################################

def create_profile_parser(subparsers):
    profile_parser = subparsers.add_parser(
        "profile",
        help="Manage profiles",
        description="Manage and manipulate profiles for instances, including listing, copying, deleting, dumping, displaying, and initializing profiles on remotes.",
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

    # Profile dump command
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

    # Import command
    import_parser = profile_subparsers.add_parser(
        "import",
        help="Import a profile from a YAML file.",
        description="Import a profile from a YAML file into Incus.\n"
                    "Wrapper for:\n"
                    "  incus profile create <profile>\n"
                    "  cat <yaml> | incus profile edit <profile>\n"
                    "The profile name can include remote/project scope.\n",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo profile import my_profile profiles/my_profile.yaml\n"
               "  figo profile import remote:project.my_profile profiles/my_profile.yaml\n"
               "  figo profile import my_profile profiles/my_profile.yaml --overwrite\n"
    )
    import_parser.add_argument(
        "profile_name",
        help="Target profile name. Can include remote and project scope (e.g., remote:project.profile)."
    )
    import_parser.add_argument(
        "yaml_file",
        help="Path to the profile YAML file to import."
    )
    import_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Skip 'incus profile create' and directly edit the profile from YAML."
    )


    # List command
    list_parser = profile_subparsers.add_parser(
        "list",
        aliases=["l"],
        help="List profiles and their associated instances.",
        description="List profiles and their associated instances.\n"
                    "You can specify a scope to filter by remote, project, or profile.\n"
                    "Use --recurse_instances to recursively list instances associated with inherited profiles.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo profile list\n"
               "  figo profile list remote:project.profile_name\n"
               "  figo profile list -i --extend --recurse_instances"
    )
    list_parser.add_argument(
        "scope",
        nargs="?",
        help="Scope in the format 'remote:project.profile_name', 'remote:project', 'project.profile_name', 'profile_name', or defaults to 'local:default'."
    )
    list_parser.add_argument("-i", "--inherited", action="store_true", help="Include inherited profiles in the listing.")
    list_parser.add_argument("-e", "--extend", action="store_true", help="Extend column width to fit the content.")
    list_parser.add_argument("-r", "--recurse_instances", action="store_true", help="Recursively list instances associated with inherited profile.")

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

    # Init command
    init_parser = profile_subparsers.add_parser(
        "init",
        help="Initialize profiles on a remote from local:default.",
        description="Initialize a remote by transferring a set of required profiles from 'local:default' to 'remote:default'.\n"
                    "Optionally, specify a custom list of profiles to be transferred using the -f/--profile option.\n"
                    "The custom list of profiles overrides the default list of profiles, which is hard-coded in the figo code.\n"
                    "If the remote already has a profile with the same name, it will not be overwritten.\n"
                    "Use the -l/--list option to display the default profiles that would be transferred.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo profile init my_remote\n"
               "  figo profile init my_remote:\n"
               "  figo profile init my_remote -f profile1,profile2,profile3\n"
               "  figo profile init -l"
    )
    init_parser.add_argument(
        "remote",
        nargs="?",
        help="Name of the remote to initialize. Can be specified as 'my_remote' or 'my_remote:'."
    )
    init_parser.add_argument(
        "-f", "--profile",
        help="Comma-separated list of profiles to transfer. Overrides the default list of profiles."
    )
    init_parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List the default profiles that would be transferred during initialization. If this option is used, the remote cannot be specified."
    )

    return profile_parser

def parse_profile_scope(profile_scope, assign_defaults=True):
    """Parse a profile scope string and return remote, project, and profile names.

    The profile scope can be in the following formats:
    - remote:project.profile
    - remote:project.
    - remote:profile
    - project.profile
    - project.
    - profile

    Parameters:
    profile_scope (str): The profile scope string to parse.
    assign_defaults (bool): Assign default values for remote and project if not provided.

    The list and dump commands use assign_defaults=False to avoid assigning defaults for remote and project.
    
    Returns:
    Tuple[str, str, str]: The remote, project, and profile names parsed from the scope.

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

    if assign_defaults:
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
        remote, project, profile = parse_profile_scope(args.profile_name, assign_defaults=False)

        client = pylxd.Client()
        if args.all:
            dump_profiles(client)
        elif profile:
            dump_profile(client, profile)
        else:
            logger.error("You must provide a profile name or use the --all option.")
    elif args.profile_command == "show":
        # Parse scope to get remote, project, and profile for the show command
        remote, project, profile = parse_profile_scope(args.profile_name)

        if profile:
            result = show_profile(remote, project, profile)
            if not result:
                logger.error(f"Error in displaying profile '{profile}'.")
        else:
            logger.error("You must provide a valid profile name to display.")
    elif args.profile_command in ["list", "l"]:
        remote, project, profile = parse_profile_scope(args.scope, assign_defaults=False)
        list_profiles(remote, project, profile_name=profile, inherited=args.inherited,
                      extend=args.extend, recurse_instances=args.recurse_instances)
    elif args.profile_command == "import":
        remote, project, profile = parse_profile_scope(args.profile_name)
        if profile is None or profile == "":
            logger.error("Error: Profile name cannot be empty.")
            return
        import_profile(
            remote,
            project,
            profile,
            args.yaml_file,
            overwrite=args.overwrite
        )

    elif args.profile_command == "copy":
        source_remote, source_project, source_profile = parse_profile_scope(args.source_profile)
        target_remote, target_project, target_profile = parse_profile_scope(
            args.target_profile if args.target_profile else source_profile
        )

        if source_profile is None or source_profile == "":
            logger.error("Error: Source profile name cannot be empty.")
            return
        
        if target_profile is None or target_profile == "":
            target_profile = source_profile

        copy_profile(source_remote, source_project, source_profile, target_remote, target_project, target_profile)
    elif args.profile_command in ["delete", "del", "d"]:
        remote, project, profile = parse_profile_scope(args.profile_scope)

        if profile is None or profile == "":
            logger.error("Error: Profile name cannot be empty.")
            return

        delete_profile(remote, project, profile)

    elif args.profile_command == "init":
        # Handle the -l/--list option
        if args.list:
            if args.remote:
                logger.error("Error: The -l/--list option cannot be used with a target remote.")
                return
            display_default_init_profiles()
            return
                
        # Validate and parse the remote
        remote = args.remote
        if ":" in remote:
            remote = remote.rstrip(":")

        if not check_remote_name(remote):
            logger.error(f"Invalid remote name: '{remote}'.")
            return

        # Parse the list of profiles
        profiles_to_transfer = args.profile.split(",") if args.profile else None

        # Proceed with initialization
        try:
            result = initialize_remote_profiles(remote, profiles_to_transfer)
            if result:
                logger.info(f"Successfully initialized profiles on remote '{remote}'.")
            else:
                logger.error(f"Failed to initialize profiles on remote '{remote}'.")
        except Exception as e:
            logger.error(f"Error during initialization of profiles on remote '{remote}': {str(e)}")


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
    user_parser = subparsers.add_parser(
        "user", 
        help="Manage users",
        description="Manage and manipulate user accounts, including adding, editing, listing, granting access, and deleting users.",
        epilog="Use 'figo user <command> -h' for more detailed help on a specific command.",
        formatter_class=argparse.RawTextHelpFormatter
        )
    user_subparsers = user_parser.add_subparsers(dest="user_command")

    # List subcommand
    user_list_parser = user_subparsers.add_parser(
        "list", aliases=["l"],
        help="List user information (use -f or --full for more details)",
        description="List all users.\n"
                    "Use the -f/--full option to show full details of users.\n"
                    "Use the -i/--ip option to include the WireGuard VPN IP address assigned to the user.\n"
                    "Use the -e/--extend option to extend column width to fit the content.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
                "  figo user list\n"
                "  figo user list -f\n"
                "  figo user list -i\n"
                "  figo user list -e"
        )
    user_list_parser.add_argument("-f", "--full", action="store_true",
                                  help="Show full details of users")
    user_list_parser.add_argument("-i", "--ip", action="store_true",
                                  help="Include the WireGuard VPN IP address assigned to the user")
    user_list_parser.add_argument("-e", "--extend", action="store_true",
                                  help="Extend column width to fit the content")

    # Add subcommand
    user_add_parser = user_subparsers.add_parser("add", aliases=["a"], help="Add a new user to the system",
                                                description="Add a new user to the system with various options for access and configuration.",
                                                 formatter_class=argparse.RawTextHelpFormatter)
    user_add_parser.add_argument("username", action=NoUnderscoreCheck, help="Username of the new user")
    user_add_parser.add_argument("-c", "--cert",
                                 help="Path to the user's certificate file for access to GUI (in .crt format, "
                                "if not provided a new key pair will be generated)")  
    user_add_parser.add_argument("-a", "--admin", action="store_true", help="Add user with admin privileges (unrestricted)")
    user_add_parser.add_argument("-w", "--wireguard", action="store_true",
                                 help="Generate WireGuard config for the user in .conf file") 
    user_add_parser.add_argument("-i", "--ip_next", action="store_true",
                                 
                                 help="Use the next available IP address for the user in the WireGuard config,\n"
                                      "instead of using the first available hole in the subnet.\n"
                                      "This option is only valid with the --wireguard option") 
    user_add_parser.add_argument("-s", "--set_vpn", action="store_true", 
                                 help="Set the user's VPN profile into the WireGuard access node") 
    user_add_parser.add_argument("-p", "--project", help="Project name to associate the user with an existing project")
    user_add_parser.add_argument("-e", "--email", action=NoCommaCheck, help="User's email address")
    user_add_parser.add_argument("-n", "--name", action=NoCommaCheck, help="User's full name")
    user_add_parser.add_argument("-o", "--org", action=NoCommaCheck, help="User's organization")
    user_add_parser.add_argument("-k", "--keys", action="store_true", help="Generate a key pair for SSH access to instances")
    user_add_parser.add_argument("-f", "--sshfs_keys", action="store_true", help="Generate a key pair for SSHFS access to instances")

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
    user_delete_parser = user_subparsers.add_parser("delete", aliases=["del", "d"], 
                                                    help="Delete an existing user from the system")
    user_delete_parser.add_argument("username", help="Username of the user to delete")
    user_delete_parser.add_argument("-p", "--purge", action="store_true",
                                    help="Delete associated projects and user files (even if the user does not exist)")
    user_delete_parser.add_argument("-k", "--keepfiles", action="store_true",
                                    help="Keep the associated files of the user in the users folder")
    user_delete_parser.add_argument("-n", "--no_vpn", action="store_true",
                                    help="Do not clean wireguard user entry in the access router")


    # Link parsers back to the main command
    subparsers._name_parser_map["us"] = user_parser
    subparsers._name_parser_map["u"] = user_parser

    return user_parser

def handle_user_command(args, parser_dict, client_name=None):
    client = pylxd.Client()
    if not args.user_command:
        parser_dict['user_parser'].print_help()
    elif args.user_command in ["list", "l"]:
        list_users(client, full=args.full, extend=args.extend, ip=args.ip)
    elif args.user_command == "add":
        # Pass the 'keys' flag to the add_user function
        if args.ip_next and not args.wireguard:
            logger.error("Error: --ip_next option is only valid with the --wireguard option.")
            return
        add_user(args.username, args.cert, client, remote_name=client_name, admin=args.admin, wireguard=args.wireguard, 
                ip_next=args.ip_next, set_vpn=args.set_vpn, project=args.project, email=args.email, name=args.name,
                org=args.org, keys=args.keys, sshfs_keys=args.sshfs_keys)
    elif args.user_command == "grant":
        grant_user_access(args.username, args.projectname, client)
    elif args.user_command == "edit":
        edit_user(args.username, client, email=args.email, name=args.name, org=args.org)
    elif args.user_command in ["delete", "del", "d"]:
        # Reverse logic: delete files by default unless --keepfiles is used
        # Reverse logic: clean wireguard user entry by default unless --no_vpn is used
        removefiles = not args.keepfiles
        removevpn = not args.no_vpn
        delete_user(args.username, client, purge=args.purge, removefiles=removefiles, removevpn=removevpn)

#############################################
###### figo remote command CLI ##############
#############################################

def create_remote_parser(subparsers):
    remote_parser = subparsers.add_parser("remote", help="Manage remotes",
                                          description="Manage and manipulate remote Incus servers, including enrolling, listing, and deleting remotes.",
                                          epilog="Use 'figo remote <command> -h' for more detailed help on a specific command.",
                                          formatter_class=argparse.RawTextHelpFormatter)
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
    remote_enroll_parser.add_argument("port", nargs="?", 
                                      default="8443", help="Port of the remote server (default: 8443)")
    remote_enroll_parser.add_argument("user", nargs="?",
                                      default=DEFAULT_LOGIN_FOR_INSTANCES,
                                      help=f"Username for SSH into the remote (default: {DEFAULT_LOGIN_FOR_INSTANCES})")
    remote_enroll_parser.add_argument("cert_filename", nargs="?", default="~/.config/incus/client.crt", 
                                      help="Client certificate file to transfer "
                                      "(default: ~/.config/incus/client.crt)")
    remote_enroll_parser.add_argument("remote_cert_filename", nargs="?", default="/var/lib/incus/server.crt",
                                      help="Remote certificate file to transfer locally "
                                      "(default: /var/lib/incus/server.crt)")
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
    project_parser = subparsers.add_parser("project", help="Manage projects",
                                           description="Manage and manipulate projects, including listing, creating, and deleting projects.",
                                           epilog="Use 'figo project <command> -h' for more detailed help on a specific command.",
                                           formatter_class=argparse.RawTextHelpFormatter)
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
###### figo operation command CLI ###########
#############################################

def create_operation_parser(subparsers):
    operation_parser = subparsers.add_parser(
        "operation",
        aliases=["op", "o"],
        help="Manage ongoing operations",
        description="Monitor and manage ongoing operations across all remotes, specific remotes, or specific projects.",
        epilog="Use 'figo operation <subcommand> -h' for more detailed help on a specific subcommand.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    operation_subparsers = operation_parser.add_subparsers(dest="operation_command")

    # Status command
    status_parser = operation_subparsers.add_parser(
        "status",
        aliases=["s"],
        help="Display the status of ongoing operations.",
        description="Display the status of ongoing operations for all remotes, specific remotes, or specific projects.\n"
                    "Specify the scope in the format 'remote:', 'remote:project', 'remote:project.', or leave blank for all.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo operation status\n"
               "  figo operation status my_remote\n"
               "  figo operation status my_remote:\n"
               "  figo operation status my_remote:project_name\n"
               "  figo operation status my_remote:project_name.\n"
               "  figo operation status my_remote --project project_name\n"
               "  figo operation status --extend"
    )
    status_parser.add_argument(
        "scope",
        nargs="?",
        help="Scope in the format 'remote:project', 'remote:', 'remote:project.', or leave blank for all operations."
    )
    status_parser.add_argument(
        "-p", "--project",
        help="Specify the project name to filter operations. If both scope and project are provided, they must match; otherwise, an error is displayed."
    )
    status_parser.add_argument(
        "-e", "--extend",
        action="store_true",
        help="Extend column width to fit the content for better readability."
    )

    # Progress command
    progress_parser = operation_subparsers.add_parser(
        "progress",
        aliases=["p"],
        help="Display the status of ongoing create instance operations.",
        description="Display the status of ongoing create instance operations for all remotes, specific remotes, or specific projects.\n"
                    "Specify the scope in the format 'remote:', 'remote:project', 'remote:project.', or leave blank for all.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  figo operation progress\n"
               "  figo operation progress my_remote\n"
               "  figo operation progress my_remote:\n"
               "  figo operation progress my_remote:project_name\n"
               "  figo operation progress my_remote:project_name.\n"
               "  figo operation progress my_remote --project project_name\n"
               "  figo operation progress --extend"
    )
    progress_parser.add_argument(
        "scope",
        nargs="?",
        help="Scope in the format 'remote:project', 'remote:', 'remote:project.', or leave blank for all operations."
    )
    progress_parser.add_argument(
        "-p", "--project",
        help="Specify the project name to filter operations. If both scope and project are provided, they must match; otherwise, an error is displayed."
    )
    progress_parser.add_argument(
        "-e", "--extend",
        action="store_true",
        help="Extend column width to fit the content for better readability."
    )

    return operation_parser

def parse_operation_scope(scope, provided_project=None):
    """
    Parse the operation scope string and return remote and project names.

    Parameters:
    - scope (str): Scope string in the format 'remote:project', 'remote:', 'remote:project.', or None for all.
    - provided_project (str): Project name provided via the -p/--project option.

    Returns:
    - Tuple[str, str]: (remote, project) extracted from the scope. Defaults to None if unspecified.

    Raises:
    - ValueError: If the scope and provided_project are inconsistent.
    """
    remote = None
    project = None

    if scope:
        if ':' in scope:
            remote, project = scope.split(':', 1)
            if remote == '':
                raise ValueError("Error: Remote name cannot be empty.")
            if project.endswith('.'):
                project = project.rstrip('.')
            if project == '':
                project = None
        else:
            remote = scope  # Assume remote-only if no colon present

    if provided_project:
        if project and project != provided_project:
            raise ValueError(
                f"Error: Inconsistent project names. Scope specifies project '{project}', "
                f"but --project specifies '{provided_project}'."
            )
        project = provided_project

    return remote, project

def handle_operation_command(args, parser_dict):
    """
    Handle subcommands for managing operations
    """
    if not args.operation_command:
        parser_dict['operation_parser'].print_help()

    elif args.operation_command in ["status", "s"] or args.operation_command in ["progress", "p"]: 
        try:
            # Parse the provided scope and ensure consistency with -p/--project
            remote, project = parse_operation_scope(args.scope, provided_project=args.project)

            # Call a function to display operations based on the parsed scope
            if args.operation_command in ["status", "s"]:
                display_operation_status(remote, project, filter_progress=False, progress=True, extend=args.extend)
            elif args.operation_command in ["progress", "p"]:
                display_operation_status(remote, project, filter_progress=True, progress=True, extend=args.extend)

        except ValueError as e:
            logger.error(str(e))

        except Exception as e:
            logger.error(f"Error while retrieving operation status: {str(e)}")

#############################################
###### figo vpn command CLI #################
#############################################

def create_vpn_parser(subparsers):
    vpn_parser = subparsers.add_parser("vpn", help="Manage VPN configuration",
                                       description="Manage VPN configuration, including adding routes and configuring VPN devices.",
                                       epilog="Use 'figo vpn <subcommand> -h' for more detailed help on a specific subcommand.",
                                       formatter_class=argparse.RawTextHelpFormatter)
    vpn_subparsers = vpn_parser.add_subparsers(dest="vpn_command")

    # Add route subcommand
    vpn_add_parser = vpn_subparsers.add_parser("add", help="Add VPN configuration", 
                                               description="Supports adding routes, for help type: figo vpn add route -h",
                                               formatter_class=argparse.RawTextHelpFormatter)
    vpn_add_subparsers = vpn_add_parser.add_subparsers(dest="vpn_add_command")

    # Route subcommand
    route_parser = vpn_add_subparsers.add_parser(
        "route", help="Add a route to VPN",
        description="Add a route to the VPN configuration.\n"
                    "Specify the destination address, gateway, device interface, and VPN type.\n"
                    "The target or host must be provided for the route.\n"
                    "If the target is provided, the host, user, and port are resolved"
                    "from the target mapping contained in the global dictionary 'ACCESS_ROUTER_TARGETS'.\n"
                    "If the host is provided, the user and port can be specified othewise they are set to default values.\n"
                    "The device interface is required for Linux routers but not for MikroTik routers.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
               "  # Add a route using a target my-target-name to be found in ACCESS_ROUTER_TARGETS\n"
               "  figo vpn add route 10.10.128.0/24 via 10.10.10.2 type mikrotik target my-target-name\n"
               "\n"
               "  # Add a route using a host address with explicit user and port\n"
               "  figo vpn add route 10.10.128.0/24 via 10.10.10.2 type mikrotik host 160.80.10.2 --user myuser --port 22\n"
               "\n"
               "  # Add a route using a host address with default user and port\n"
               "  figo vpn add route 10.10.128.0/24 via 10.10.10.2 type mikrotik host 160.80.10.2 \n"
               "\n"
               "  # Add a route to a network into a server my-linux to be found in ACCESS_ROUTER_TARGETS\n"
               "  figo vpn add route 10.10.0.0/16 via 10.202.128.1 --dev wg128 type linux target my-linux\n"
               "\n"
    )    

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
###### figo storage command CLI #############
#############################################

def create_storage_parser(subparsers):
    storage_parser = subparsers.add_parser(
        "storage",
        help="Manage file storage servers and user quotas",
        description="""
Manage distributed file storage servers and enforce user quotas.

This command group allows administrators to enroll and remove file servers,
inspect the current list of registered storage backends, and assign or discard
user quotas on each of them.
        """,
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n"
        "  figo storage enroll myfs1 192.168.1.10 --ssh-user ubuntu --mount-path /mnt/storage --pool-name storage --backend-fs zfs\n"
        "  figo storage delete myfs1\n"
        "  figo storage list\n"
        "  figo storage quota 100G alice myfs1\n"
        "  figo storage discard alice myfs1\n"
        "\n"
        "Use 'figo storage <subcommand> -h' for more detailed help on a specific subcommand.\n"
    )
    storage_subparsers = storage_parser.add_subparsers(dest="storage_command")

    # figo storage enroll
    enroll_parser = storage_subparsers.add_parser("enroll", help="Enroll a new file storage server")
    enroll_parser.add_argument("fileserver_name", help="Name of the storage server")
    enroll_parser.add_argument("ip_address", help="IP address of the server")
    enroll_parser.add_argument("--ssh-user", default="ubuntu", help="SSH username (default: ubuntu)")
    enroll_parser.add_argument("--mount-path", default="/figo-users-datapool/", help="Path where the storage is mounted")
    enroll_parser.add_argument("--pool-name", default="figo-users-datapool", help="Name of the ZFS storage pool")
    enroll_parser.add_argument("--backend-fs", default="zfs", choices=["zfs", "xfs", "ext4"], help="Filesystem type")

    # figo storage delete
    delete_parser = storage_subparsers.add_parser("delete", help="Remove a file storage server")
    delete_parser.add_argument("fileserver_name", help="Name of the storage server")

    # figo storage list
    list_parser = storage_subparsers.add_parser("list", help="List current file storage servers")

    # figo storage quota
    quota_parser = storage_subparsers.add_parser("quota", help="Set a quota for a user on a file server")
    quota_parser.add_argument("quota_size", help="Quota size (e.g., 100G)")
    quota_parser.add_argument("user", help="Username")
    quota_parser.add_argument("fileserver_name", help="Target file server")

    # figo storage discard
    discard_parser = storage_subparsers.add_parser("discard", help="Remove a user's quota and delete the user")
    discard_parser.add_argument("user", help="Username")
    discard_parser.add_argument("fileserver_name", help="Target file server")

    return storage_parser

# Dispatch function for storage command
def handle_storage_command(args, parser_dict):
    if args.storage_command is None:
        parser_dict["storage_parser"].print_help()
        return

    if args.storage_command == "enroll":
        storage_enroll(args)
    elif args.storage_command == "delete":
        storage_delete(args)
    elif args.storage_command == "list":
        storage_list()
    elif args.storage_command == "quota":
        storage_set_quota(args)
    elif args.storage_command == "discard":
        storage_discard(args)

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
    parser_dict['net_parser'] = create_net_parser(subparsers)
    parser_dict['profile_parser'] = create_profile_parser(subparsers)
    parser_dict['user_parser'] = create_user_parser(subparsers)
    parser_dict['remote_parser'] = create_remote_parser(subparsers)
    parser_dict['project_parser'] = create_project_parser(subparsers)
    parser_dict['operation_parser'] = create_operation_parser(subparsers)
    parser_dict['vpn_parser'] = create_vpn_parser(subparsers)
    parser_dict['storage_parser'] = create_storage_parser(subparsers)

    return parser, parser_dict

def handle_command(args, parser, parser_dict):

    # if --version is provided, print the version and exit
    if hasattr(args, 'version'):
        logger.info(parser.prog, parser.version)  # prints the version of the parser
        return
    
    # Handle the command based on the subparser
    if args.command in ["instance", "in", "i"]:
        handle_instance_command(args, parser_dict)
    elif args.command in ["gpu", "gp", "g"]:
        handle_gpu_command(args, parser_dict)
    elif args.command in ["profile", "pr", "p"]:
        handle_profile_command(args, parser_dict)
    elif args.command in ["user", "us", "u"]:
        handle_user_command(args, parser_dict, client_name="local")
    elif args.command in ["remote", "re", "r"]:
        handle_remote_command(args, parser_dict)
    elif args.command in ["project"]:
        handle_project_command(args, parser_dict)
    elif args.command in ["operation", "op", "o"]:
        handle_operation_command(args, parser_dict)
    elif args.command in ["net"]:
        handle_net_command(args, parser_dict)
    elif args.command in ["vpn"]:
        handle_vpn_command(args, parser_dict)
    elif args.command in ["storage"]:
        handle_storage_command(args, parser_dict)


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