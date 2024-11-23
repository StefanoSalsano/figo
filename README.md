# FIGO - Federated Infrastructure for GPU Orchestration

FIGO is a tool for managing federated testbeds with CPUs and GPUs. It provides commands to handle instances (VMs and containers) and GPU profiles.

End user manual (installation and usage) is available [here](https://figo-testbed.readthedocs.io/).

The source code of the documentation site is [here](https://github.com/netgroup/figo-testbed).

## Usage (for administrators)

FIGO provides various commands to manage VM and container instances and GPU profiles. Below is a detailed guide on how to use these commands.

### General Usage

When the script is called with no command parameters, the general usage information is displayed:

```bash
figo
```

### Commands

**Description:**  
This module provides a command-line interface (CLI) to manage a federated testbed with CPUs and GPUs. The `figo` program offers various commands and subcommands for managing instances, GPUs, profiles, users, remotes, projects, and VPNs in a federated environment.

**Usage:**

```bash
figo [command] [subcommand] [options]
```

**Commands:**

- [`figo instance`](#figo-instance)
- [`figo gpu`](#figo-gpu)
- [`figo profile`](#figo-profile)
- [`figo user`](#figo-user)
- [`figo remote`](#figo-remote)
- [`figo project`](#figo-project)
- [`figo vpn`](#figo-vpn)

Each command has its own set of subcommands and options.

### Command and Subcommand Details

### figo instance

- **Aliases:** `in`, `i`
- **Description:** Manage instances, including creating, listing, starting, stopping, setting IP addresses, setting keys, and executing bash commands.

#### Subcommands:
- [`figo instance list`](#figo-instance-list)
- [`figo instance start`](#figo-instance-start)
- [`figo instance stop`](#figo-instance-stop)
- [`figo instance set_key`](#figo-instance-set_key)
- [`figo instance show_keys`](#figo-instance-show_keys)
- [`figo instance set_ip`](#figo-instance-set_ip)
- [`figo instance create`](#figo-instance-create)
- [`figo instance delete`](#figo-instance-delete)
- [`figo instance bash`](#figo-instance-bash)

#### Subcommands details

- #### `figo instance list`

  - **Description:** List instances, with options to specify a scope, remote, and project. Use the `--full` option to display detailed information.
  - **Syntax:**

    ```bash
    figo instance list [scope] [-f | --full] [-e | --extend]
    ```

  - **Options:**
    - `scope`: Limits the listing to the specified scope in the format `remote:project.`, `project.`, or `remote:`.
    - `-f, --full`: Show full details of instance profiles.
    - `-e, --extend`: Extend column width to fit content.

  - **Examples:**
    ```bash
    figo instance list
    figo instance list remote:project.
    figo instance list project. -r remote_name
    figo instance list -f --extend
    ```

- #### `figo instance start`

  - **Description:** Start a specific instance, with options to specify remote and project scope.
  - **Syntax:**

    ```bash
    figo instance start instance_name [-r remote] [-p project]
    ```

  - **Options:**
    - `instance_name`: The name of the instance to start, which can include remote and project scope.

  - **Examples:**
    ```bash
    figo instance start instance_name
    figo instance start remote:project.instance_name
    figo instance start instance_name -r remote_name -p project_name
    ```

- #### `figo instance stop`

  - **Description:** Stop a specific instance or all instances in a specified scope.
  - **Syntax:**

    ```bash
    figo instance stop [instance_name] [-a | --all] [-r remote] [-p project]
    ```

  - **Options:**
    - `instance_name`: The name of the instance to stop, which can include remote and project scope. If `--all` is provided, a specific instance name should not be given.
    - `-a, --all`: Stop all instances in the specified scope.

  - **Examples:**
    ```bash
    figo instance stop instance_name
    figo instance stop remote:project.instance_name
    figo instance stop -a -r remote_name
    figo instance stop project. -a
    ```

- #### `figo instance set_key`

  - **Description:** Set a public key for a user in a specific instance.
  - **Syntax:**

    ```bash
    figo instance set_key instance_name key_filename [-l login] [-d dir] [-f | --force] [-r remote] [-p project]
    ```

  - **Options:**
    - `instance_name`: The name of the instance, which can include remote and project scope.
    - `key_filename`: Filename of the public key on the host (default location: `./users`).
    - `-l, --login`: Specify the user login name (default: `ubuntu`).
    - `-d, --dir`: Specify the directory path where the key file is located (default: `./users`).
    - `-f, --force`: Start the instance if not running, then stop after setting the key.

  - **Examples:**
    ```bash
    figo instance set_key instance_name key_filename
    figo instance set_key remote:project.instance_name key_filename
    figo instance set_key instance_name key_filename -r remote_name -p project_name
    ```

- #### [`figo instance show_keys`]

  - **Description:** Display the keys associated with a specific instance, including the key type and the key ID. Optionally, display the full key content using the `-k/--keys` option. Specify the remote, project, and login parameters as needed. If the instance is not running, you can force-start it using the `-f/--force` option. Use `-e/--extend` to adjust column widths for better readability.

  - **Syntax:**
    ```bash
    figo instance show_keys instance_name [-r remote] [-p project] [-l login] [-f | --force] [-k | --keys] [-e | --extend]
    ```

  - **Options:**
    - `instance_name`: The name of the instance. Can include remote and project scope in the format `remote:project.instance_name`.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-l, --login`: Specify the user login name to check keys for (default: `ubuntu`).
    - `-f, --force`: Start the instance if not running, then stop it after fetching the keys.
    - `-k, --keys`: Display the full key content in the output.
    - `-e, --extend`: Adjust column widths to fit content for better readability.

  - **Examples:**
    ```bash
    figo instance show_keys instance_name
    figo instance show_keys remote:project.instance_name
    figo instance show_keys instance_name -r remote_name -p project_name
    figo instance show_keys instance_name -l custom_user -f
    figo instance show_keys instance_name -k --extend
    ```

- #### `figo instance set_ip`

  - **Description:** Set a static IP address and gateway for a stopped instance. If an IP address is not provided, an available IP address is assigned. By default, assigns the next IP address after the highest assigned IP; with `--hole`, assigns the first available gap in the IP range.
  - **Syntax:**

    ```bash
    figo instance set_ip instance_name [-i ip_address] [-g gw_address] [-n nic] [-r remote] [-p project] [-o | --hole]
    ```

  - **Options:**
    - `instance_name`: The name of the instance, which can include remote and project scope.
    - `-i, --ip`: Specify a static IP address with prefix length (e.g., `192.168.1.10/24`). If omitted, an available IP address is assigned based on the highest IP in use, or the first available gap if `--hole` is used.
    - `-g, --gw`: Specify the gateway address. If omitted, the default gateway for the remote is used.
    - `-n, --nic`: Specify the NIC name (default: `eth0` for containers, `enp5s0` for VMs).
    - `-o, --hole`: Assigns the first available IP address hole in the range rather than the next sequential IP.

  - **Examples:**
    ```bash
    figo instance set_ip instance_name -i 192.168.1.10/24 -g 192.168.1.1
    figo instance set_ip remote:project.instance_name -i 10.0.0.5/24 -g 10.0.0.1
    figo instance set_ip my_remote:my_project.instance_name --hole
    figo instance set_ip remote:project.instance_name
    ```

- #### `figo instance create`

  - **Description:** Create a new instance with optional specifications for image, type, profiles, and IP settings. If the IP address is not provided, an available IP address is automatically assigned. By default, assigns the next IP after the highest assigned IP; with `--hole`, assigns the first available gap in the IP range.
  - **Syntax:**

    ```bash
    figo instance create instance_name image [-t type] [-p project] [-r remote] [-i ip_address] [-g gw_address] [-n nic] [-f profiles] [-o | --hole] [-m | --make_project]
    ```

  - **Options:**
    - `instance_name`: The name of the new instance, which can include remote and project scope.
    - `image`: The image source for creating the instance (e.g., `images:ubuntu/20.04`).
    - `-t, --type`: Specify the instance type (`vm`, `container`, or `cnt`). Default is `container`.
    - `-p, --project`: Specify the project under which the instance will be created.
    - `-r, --remote`: Specify the remote Incus server.
    - `-i, --ip`: Specify a static IP address for the instance.
    - `-g, --gw`: Specify the gateway address.
    - `-n, --nic`: Specify the NIC name (default: `eth0` for containers, `enp5s0` for VMs).
    - `-f, --profile`: Comma-separated list of profiles to apply to the instance.
    - `-m, --make_project`: Create the project if it does not exist on the specified remote.
    - `-o, --hole`: Assigns the first available IP address hole in the range rather than the next sequential IP.

  - **Examples:**
    ```bash
    figo instance create my_instance images:ubuntu/20.04
    figo instance create remote:project.instance_name images

:debian/11 -t vm
    figo instance create instance_name images:centos/8 -r remote_name -p project_name
    figo instance create instance_name images:ubuntu/22.04 -f profile1,profile2
    figo instance create instance_name images:alpine/3.15 -m --hole
    ```

- #### `figo instance delete`

  - **Description:** Delete a specific instance, with an option to force delete if the instance is running.
  - **Syntax:**

    ```bash
    figo instance delete instance_name [-f | --force] [-r remote] [-p project]
    ```

  - **Options:**
    - `instance_name`: The name of the instance to delete, which can include remote and project scope.
    - `-f, --force`: Force delete the instance even if it is running.

  - **Examples:**
    ```bash
    figo instance delete instance_name
    figo instance delete remote:project.instance_name -f
    figo instance delete instance_name -r remote_name -p project_name
    ```

- #### `figo instance bash`

  - **Description:** Execute bash in a specific instance, with an option to start the instance if it is not running.
  - **Syntax:**

    ```bash
    figo instance bash instance_name [-f | --force] [-t timeout] [-a attempts] [-r remote] [-p project]
    ```

  - **Options:**
    - `instance_name`: The name of the instance to execute bash, which can include remote and project scope.
    - `-f, --force`: Start the instance if not running and execute bash. Stop the instance on exit if it was initially stopped.
    - `-t, --timeout`: Total timeout in seconds for retries (default: `BASH_CONNECT_TIMEOUT`).
    - `-a, --attempts`: Number of retry attempts to connect (default: `BASH_CONNECT_ATTEMPTS`).

  - **Examples:**
    ```bash
    figo instance bash instance_name
    figo instance bash remote:project.instance_name
    figo instance bash instance_name -f -r remote_name -p project_name
    ```

### figo gpu

- **Aliases:** `gp`, `g`
- **Description:** Manage GPUs in instances within the federated testbed.

#### Subcommands:
- [`figo gpu status`](#figo-gpu-status)
- [`figo gpu list`](#figo-gpu-list)
- [`figo gpu add`](#figo-gpu-add)
- [`figo gpu remove`](#figo-gpu-remove)
- [`figo gpu pci_addr`](#figo-gpu-pci_addr)

#### Subcommands details

- #### `figo gpu status`

  - **Description**: Display the status of GPUs on the specified remote or local system.
  - **Syntax**:
      ```bash
      figo gpu status [remote] [-e | --extend]
      ```
  - **Options**:
      - `remote`: Specify the remote name to show the GPU status. Defaults to `local` if omitted.
      - `-e, --extend`: Extend column width for better readability.
  - **Examples**:
      ```bash
      figo gpu status
      figo gpu status my_remote:
      figo gpu status --extend
      ```

- #### `figo gpu list`

  - **Description**: List all GPU profiles configured on a specified remote or locally.
  - **Syntax**:
      ```bash
      figo gpu list [remote] [-e | --extend]
      ```
  - **Options**:
      - `remote`: Specify the remote name to list the GPU profiles. Defaults to `local` if omitted.
      - `-e, --extend`: Extend column width for better readability.
  - **Examples**:
      ```bash
      figo gpu list
      figo gpu list my_remote:
      figo gpu list --extend
      ```

- #### `figo gpu add`

  - **Description:** Add a GPU profile to a specific instance. The instance name can include remote and project scope in the format `remote:project.instance_name`. If not provided, use the `-r/--remote` and `-p/--project` options.
  - **Syntax:**
    ```bash
    figo gpu add instance_name [-p | --project project_name] [-r | --remote remote_name] [-u | --user user_name]
    ```
  - **Options:**
    - `instance_name`: The name of the instance to which the GPU profile will be added. Can include remote and project scope.
    - `-p, --project`: Specify the project name for the instance.
    - `-r, --remote`: Specify the remote Incus server name.
    - `-u, --user`: Specify the user to infer the project from.
  - **Examples:**
    ```bash
    figo gpu add my_instance
    figo gpu add my_project.instance_name -r my_remote
    figo gpu add my_remote:my_project.instance_name
    figo gpu add instance_name -p my_project -r my_remote
    figo gpu add my_instance -u user_name
    ```

- #### `figo gpu remove`

  - **Description:** Remove GPU profiles from a specific instance. Optionally, remove all profiles. The instance name can include remote and project scope in the format `remote:project.instance_name`. If not provided, use the `-r/--remote` and `-p/--project` options.
  - **Syntax:**
    ```bash
    figo gpu remove instance_name [-p | --project project_name] [-r | --remote remote_name] [-u | --user user_name] [--all]
    ```
  - **Options:**
    - `instance_name`: The name of the instance from which the GPU profile will be removed. Can include remote and project scope.
    - `-p, --project`: Specify the project name for the instance.
    - `-r, --remote`: Specify the remote Incus server name.
    - `-u, --user`: Specify the user to infer the project from.
    - `--all`: Remove all GPU profiles from the specified instance.
  - **Examples:**
    ```bash
    figo gpu remove my_instance
    figo gpu remove my_project.instance_name --all
    figo gpu remove my_remote:my_project.instance_name
    figo gpu remove instance_name -p my_project -r my_remote --all
    figo gpu remove my_instance -u user_name
    ```

- #### `figo gpu pci_addr`

  - **Description**: Display PCI addresses of GPUs available on a specific remote.
  - **Syntax**:
    ```bash
    figo gpu pci_addr [remote]
    ```
  - **Options**:
    - `remote`: Specify the remote name for displaying GPU PCI addresses. Defaults to `local` if omitted.
  - **Examples**:
    ```bash
    figo gpu pci_addr
    figo gpu pci_addr my_remote
    ```

### figo profile

- **Aliases:** `pr`, `p`
- **Description:** Manage profiles.

#### Subcommands:
- [`figo profile show`](#figo-profile-show)
- [`figo profile dump`](#figo-profile-dump)
- [`figo profile list`](#figo-profile-list)
- [`figo profile copy`](#figo-profile-copy)
- [`figo profile delete`](#figo-profile-delete)
- [`figo profile init`](#figo-profile-init)

#### Subcommands details

- #### `figo profile show`

  - **Description:** Display detailed information about a specific profile.
  - **Syntax:**
    ```bash
    figo profile show profile_name
    ```
  - **Options:**
    - `profile_name`: The name of the profile to display.

  - **Examples:**
    ```bash
    # Display details of a specific profile
    figo profile show my_profile
    ```

- #### `figo profile dump`

  - **Description:** Dump profile(s) to `.yaml` files for backup or inspection.
  - **Syntax:**
    ```bash
    figo profile dump [profile_name] [-a | --all]
    ```
  - **Options:**
    - `profile_name`: Name of the profile to dump. If omitted, use the `--all` option to dump all profiles.
    - `-a, --all`: Dump all profiles to `.yaml` files in the `./profiles` directory.

  - **Details:**
    - The profile data includes only the name, description, config, and devices.
    - Each dumped profile is saved in the `./profiles` directory with the filename matching the profile name, e.g., `./profiles/my_profile.yaml`.
    - The directory `./profiles` is created if it does not exist.
    - Note: This currently only works for local profiles and not for remote profiles.

  - **Examples:**
    ```bash
    # Dump a specific profile to a .yaml file
    figo profile dump my_profile

    # Dump all available local profiles to individual .yaml files in the './profiles' directory
    figo profile dump --all
    ```

- #### `figo profile list`

  - **Description:** List profiles and their associated instances, with options to include inherited profiles, extend column width, and recursively list instances associated with inherited profiles.
  - **Syntax:**
    ```bash
    figo profile list [scope] [-i | --inherited] [-e | --extend] [-r | --recurse_instances]
    ```
  - **Options:**
    - `scope`: Scope in the format `remote:project.profile_name`, `remote:project`, `project.profile_name`, or defaults to `local:default`.
    - `-i, --inherited`: Include inherited profiles in the listing.
    - `-e, --extend`: Extend column width to fit the content.
    - `-r, --recurse_instances`: Recursively list instances associated with inherited profiles.

  - **Examples:**
    ```bash
    # List profiles with default options
    figo profile list
    
    # List a specific profile with a given scope
    figo profile list remote:project.profile_name
    
    # List profiles, including inherited profiles, with extended column width
    figo profile list -i --extend

    # List profiles and recursively show instances associated with inherited profiles
    figo profile list --recurse_instances
    ```

- #### `figo profile copy`

  - **Description:** Copy a profile to a new profile name or remote/project.
  - **Syntax:**
    ```bash
    figo profile copy source_profile [target_profile]
    ```
  - **Options:**
    - `source_profile`: Source profile in the format `remote:project.profile_name` or `project.profile_name` or `profile_name`.
    - `target_profile`: Target profile in the format `remote:project.profile_name` or `project.profile_name` or `profile_name`.

  - **Examples:**
    ```bash
    figo profile copy remote:project.profile1 remote:project.profile2
    figo profile copy remote:project.profile1 remote:project
    figo profile copy profile1 profile2
    ```

- #### `figo profile delete`

  - **Description:** Delete a specific profile from the system.
  - **Syntax:**
    ```bash
    figo profile delete profile_scope
    ```
  - **Options:**
    - `profile_scope`: Profile scope in the format `remote:project.profile_name`, `remote:project`, `project.profile_name`, or `profile_name`.

  - **Examples:**
    ```bash
    figo profile delete remote:project.profile_name
    figo profile delete project.profile_name
    figo profile delete profile_name
    ```

- #### `figo profile init`

  - **Description:** Initialize profiles on a remote by transferring a set of required profiles from `local:default` to `remote:default`. Optionally, specify a custom list of profiles to transfer.
  - **Syntax:**
      ```bash
      figo profile init remote [-f | --profile profiles]
      ```
  - **Options:**
      - `remote`: Name of the remote to initialize. Can be specified as `my_remote` or `my_remote:`.
      - `-f, --profile`: Comma-separated list of profiles to transfer. Overrides the default list of profiles, which is hard-coded in the figo code.
  - **Details:**
      - If the remote already has a profile with the same name, it will not be overwritten.
      - If no custom list of profiles is provided, the default list of profiles is used.

  - **Examples:**
      ```bash
      # Initialize remote with the default set of profiles
      figo profile init my_remote

      # Initialize remote with a custom list of profiles
      figo profile init my_remote -f profile1,profile2,profile3

      # Initialize a remote with the default set, specifying the remote with a colon
      figo profile init my_remote:
      ```

### figo user

- **Aliases:** `us`, `u`
- **Description:** Manage users.

#### Subcommands:
- [`figo user list`](#figo-user-list)
- [`figo user add`](#figo-user-add)
- [`figo user grant`](#figo-user-grant)
- [`figo user edit`](#figo-user-edit)
- [`figo user delete`](#figo-user-delete)

#### Subcommands details

- #### `figo user list`

  - **Description:** List installed certificates, with options to show detailed information and extend column width for better readability.
  - **Syntax:**
    ```bash
    figo user list [-f | --full] [-e | --extend]
    ```
  - **Options:**
    - `-f, --full`: Show full details of installed certificates.
    - `-e, --extend`: Extend column width to fit the content.
  - **Examples:**
    ```bash
    figo user list
    figo user list --full
    figo user list --extend
    ```

- #### `figo user add`

  - **Description:** Add a new user to the system.
  - **Syntax:**
    ```bash
    figo user add username [-c | --cert cert_filename] [-a | --admin] [-w | --wireguard] [-s | --set_vpn] [-p | --project project_name] [-e | --email email] [-n | --name full_name] [-o | --org organization] [-k | --keys]
    ```
  - **Options:**
    - `username`: Username of the new user.
    - `-c, --cert`: Path to the user's certificate file. If not provided, a new key pair will be generated.
    - `-a, --admin`: Add user with admin privileges.
    - `-w, --wireguard`: Generate WireGuard configuration for the user in a `.conf` file.
    - `-s, --set_vpn`: Set the user's VPN profile into the WireGuard access node.
    - `-p, --project`: Associate the user with an existing project.
    - `-e, --email`: User's email address.
    - `-n, --name`: User's full name.
    - `-o, --org`: User's organization.
    - `-k, --keys`: Generate a key pair for SSH access to instances.
  - **Examples:**
    ```bash
    figo user add john_doe -e john@example.com -n "John Doe" -o "Example Corp"
    figo user add alice -p project1 -a
    figo user add jane --wireguard
    ```

- #### `figo user grant`

  - **Description:** Grant a user access to a specific project.
  - **Syntax:**
    ```bash
    figo user grant username projectname
    ```
  - **Options:**
    - `username`: Username to grant access.
    - `projectname`: Project name to grant access to.
  - **Examples:**
    ```bash
    figo user grant john_doe project1
    figo user grant alice project2
    ```

- #### `figo user edit`

  - **Description:** Edit an existing user's details.
  - **Syntax:**
    ```bash
    figo user edit username [-e | --email new_email] [-n | --name new_full_name] [-o | --org new_organization]
    ```
  - **Options:**
    - `username`: Username to edit.
    - `-e, --email`: New email for the user.
    - `-n, --name`: New full name for the user.
    - `-o, --org`: New organization for the user.
  - **Examples:**
    ```bash
    figo user edit john_doe -e john.doe@example.com -n "Johnathan Doe" -o "Example Corp"
    figo user edit alice --org "New Organization"
    ```

- #### `figo user delete`

  - **Description:** Delete an existing user from the system.
  - **Syntax:**
    ```bash
    figo user delete username [-p | --purge] [-k | --keepfiles]
    ```
  - **Options:**
    - `username`: Username of the user to delete.
    - `-p, --purge`: Delete associated projects and user files, even if the user does not exist.
    - `-k, --keepfiles`: Keep the associated files of the user in the users folder.
  - **Examples:**
    ```bash
    figo user delete john_doe
    figo user delete alice --purge
    figo user delete jane -k
    ```

### figo remote

- **Aliases:** `re`, `r`
- **Description:** Manage remotes for the FIGO system, including listing, enrolling, and deleting remote servers.

#### Subcommands:
- [`figo remote list`](#figo-remote-list)
- [`figo remote enroll`](#figo-remote-enroll)
- [`figo remote delete`](#figo-remote-delete)

#### Subcommands details

- #### `figo remote list`

  - **Description:** List available remotes, with options to show detailed information and adjust column width for better readability.
  - **Syntax:**
    ```bash
    figo remote list [-f | --full] [-e | --extend]
    ```
  - **Options:**
    - `-f, --full`: Show full details of available remotes.
    - `-e, --extend`: Extend column width to fit the content.
  - **Examples:**
    ```bash
    figo remote list
    figo remote list --full
    figo remote list --extend
    ```

- #### `figo remote enroll`

  - **Description:** Enroll a remote Incus server to set up a connection for managing instances and resources.
  - **Syntax:**
    ```bash
    figo remote enroll remote_server ip_address [port] [user] [cert_filename] [remote_cert_filename] [--loc_name loc_name]
    ```
  - **Options:**
    - `remote_server`: Name to assign to the remote server.
    - `ip_address`: IP address or domain name of the remote server.
    - `port`: Port of the remote server (default: 8443).
    - `user`: Username for SSH into the remote server (default: `ubuntu`).
    - `cert_filename`: Path to the client certificate file on the main node (default: `~/.config/incus/client.crt`).
    - `remote_cert_filename`: Path to the server certificate file on the remote server (default: `/var/lib/incus/server.crt`).
    - `--loc_name`: Name for saving the client certificate on the remote server (default: `main`).
  - **Examples:**
    ```bash
    figo remote enroll my_remote 192.168.1.100
    figo remote enroll my_remote 192.168.1.100 8443 ubuntu ~/.config/incus/client.crt /var/lib/incus/server.crt --loc_name main
    ```

- #### `figo remote delete`

  - **Description:** Delete a specified remote from the system, removing its configuration.
  - **Syntax:**
    ```bash
    figo remote delete remote_name
    ```
  - **Options:**
    - `remote_name`: The name of the remote to delete.
  - **Examples:**
    ```bash
    figo remote delete my_remote
    figo remote delete test_remote
    ```

### figo project

- **Description:** Manage projects within the federated testbed.

#### Subcommands:
- [`figo project list`](#figo-project-list)
- [`figo project create`](#figo-project-create)
- [`figo project delete`](#figo-project-delete)

#### Subcommands details

- #### `figo project list`

  - **Description:** List available projects, optionally specifying a remote or user.
  - **Syntax:**
    ```bash
    figo project list [scope] [--remote remote_name] [--user user_name] [-e | --extend]
    ```
  - **Options:**
    - `scope`: Scope in the format `remote:project`, `remote:`, or `project.` to limit the listing.
    - `--remote`: Specify the remote server name.
    - `--user`: Specify a user to filter the projects by ownership.
    - `-e, --extend`: Extend column width to fit the content.
  - **Examples:**
    ```bash
    figo project list
    figo project list remote:project
    figo project list --remote my_remote
    figo project list --user my_user --extend
    ```

- #### `figo project create`

  - **Description:** Create a new project, specifying scope, project name, and user ownership.
  - **Syntax:**
    ```bash
    figo project create scope [--project project_name] [--user user_name]
    ```
  - **Options:**
    - `scope`: Scope in the format `remote:project` or `remote:`.
    - `--project`: Project name, if not provided directly in the scope.
    - `--user`: Specify the user who will own the project.
  - **Examples:**
    ```bash
    figo project create my_remote:my_project --user my_user
    figo project create my_remote: --project new_project
    ```

- #### `figo project delete`

  - **Description:** Delete an existing project.
  - **Syntax:**
    ```bash
    figo project delete project_name
    ```
  - **Options:**
    - `project_name`: Name of the project to delete, in the format `remote:project` or `project`.
  - **Examples:**
    ```bash
    figo project delete my_remote:my_project
    figo project delete project_name
    ```

---

### figo vpn

- **Description:** Manage VPN configuration for secure communication and routing.

#### Subcommands:
- [`figo vpn add route`](#figo-vpn-add-route)

#### Subcommands details

- #### `figo vpn add route`

  - **Description:** Add a new route to an existing VPN configuration.
  - **Syntax:**
    ```bash
    figo vpn add route dst_address via gateway type vpn_type [target|host] target_or_host [-d dev] [-u user] [-p port]
    ```
  - **Options:**
    - `dst_address`: Destination address in CIDR format (e.g., `10.202.128.0/24`).
    - `via`: The keyword `via` followed by the gateway IP.
    - `gateway`: Gateway address (e.g., `10.202.9.2`) without a prefix.
    - `type`: The keyword `type` followed by the VPN device type, such as `mikrotik` or `linux`.
    - `target`: The keyword `target` followed by the target identifier (if applicable).
    - `host`: The keyword `host` followed by the host address.
    - `target_or_host`: The actual target or host for the VPN configuration.
    - `-d, --dev`: Device interface (e.g., `vlan403`). Required for Linux routers.
    - `-u, --user`: SSH username for logging into the node (default: configured SSH user).
    - `-p, --port`: SSH port for connecting to the VPN host (default: configured SSH port).
  - **Examples:**
    ```bash
    figo vpn add route 10.202.128.0/24 via 10.202.9.2 type linux target target-name -d vlan403
    figo vpn add route 192.168.0.0/16 via 192.168.1.1 type mikrotik host my-vpn-host
    ```
## Autocompletion

The CLI supports autocompletion using the `argcomplete` library,

using `argcomplete` library, which must be installed and configured to enable this feature.

## Examples

- List all instances in a specific project:

    ```bash
    figo instance list myproject
    ```

- Start an instance named `test-instance`:

    ```bash
    figo instance start test-instance
    ```

- Add a GPU profile to an instance:

    ```bash
    figo gpu add test-instance
    ```

- Enroll a remote Incus server:

    ```bash
    figo remote enroll my-remote-server 192.168.1.10 8443 myuser ~/.config/incus/client.cr --loc_name backup
    ```

- Add a user, generating a browser client certificate:

    ```bash
    figo user add user-name --email user@email.com --name "Name of User" --org "User organization"
    ```

- Remove a user (also deletes associated projects in all remotes if they are empty):

    ```bash
    figo user delete user-name
    ```

- Remove a user and associated files in the users folder (.pub, .ctr, .pfx, ...):

    ```bash
    figo user delete user-name -r
    ```

- Remove the projects associated with the user even if the user does not exist:

    ```bash
    figo user delete user-name -p
    ```

- Remove the projects and files associated with the user even if the user does not exist:

    ```bash
    figo user delete user-name -rp
    ```
