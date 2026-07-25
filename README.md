# FIGO - Federated Infrastructure for GPU Orchestration

FIGO is a tool for managing federated testbeds with CPUs and GPUs. It provides commands to handle instances (VMs and containers) and GPU profiles.

Additional presentations, papers, and documentation can be found [here](docs/figo-doc.md).

End user manual (installation and usage) is available [here](https://figo-testbed.readthedocs.io/).

The source code of the end user manual is [here](https://github.com/netgroup/figo-testbed).

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
- [`figo operation`](#figo-operation)
- [`figo vpn`](#figo-vpn)

Each command has its own set of subcommands and options.

### Command and Subcommand Details

### figo instance

- **Aliases:** `in`, `i`
- **Description:** Manage instances with comprehensive control over creation, listing, starting, stopping, configuring IP addresses, setting user keys, and executing bash commands directly within instances.

#### Features:
- **Instance Creation:** Create instances with specified profiles, IP configurations, and user keys.
- **Remote and Project Support:** Manage instances across remotes and projects with scoped commands.
- **Key Management:** Add or view authorized keys for users in specific instances.
- **Dynamic Network Configuration:** Assign static IP addresses or use automatic assignment for seamless networking.
- **Additional IP Addresses:** Register further addresses held by an instance (for nested virtual machines, inner containers, or extra addresses on its own NIC) so that the IPAM never hands them out to anybody else.
- **Instance Execution:** Execute bash commands directly within instances, with automatic start if required.
- **Flexibility:** Supports containers, virtual machines (VMs), and multiple instance profiles.

#### Example Use Cases:
- Set up and manage instances in a federated environment with customizable configurations.
- Integrate user-specific SSH keys into newly created instances for secure access.
- Monitor and control instances across multiple remotes and projects with ease.
- Dynamically assign IP addresses or manage networking configurations for isolated or shared environments.

#### Subcommands:
- [`figo instance list`](#figo-instance-list)
- [`figo instance start`](#figo-instance-start)
- [`figo instance stop`](#figo-instance-stop)
- [`figo instance set_key`](#figo-instance-set_key)
- [`figo instance show_keys`](#figo-instance-show_keys)
- [`figo instance set_ip`](#figo-instance-set_ip)
- [`figo instance additional_ip`](#figo-instance-additional_ip)
- [`figo instance create`](#figo-instance-create)
- [`figo instance delete`](#figo-instance-delete)
- [`figo instance bash`](#figo-instance-bash)

#### Subcommands details

- #### `figo instance list`

  - **Description:** List instances, with options to specify a scope, remote, and project. Use the `--full` option to display detailed information. The `--extend` option adjusts column widths for better readability. The `--join` option combines the context and instance name into a single field. The address column reports the address of each instance, followed by `+N` when the instance also holds N **additional addresses** (see [`figo instance additional_ip`](#figo-instance-additional_ip)).
  - **Syntax:**

    ```bash
    figo instance list [scope] [-f | --full] [-e | --extend] [-j | --join] [-a | --additional] [-r remote] [-p project] [-u user]
    ```

  - **Options:**
    - `scope`: Limits the listing to the specified scope in the format `remote:project.`, `project.`, or `remote:`.
    - `-f, --full`: Show full details of instance profiles.
    - `-e, --extend`: Extend column width to fit content.
    - `-j, --join`: Combine the context and instance name into a single field for display.
    - `-a, --additional`: Expand each instance that holds additional IP addresses into one extra row per address, and add the `NAME` and `MAC` columns.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.

  - **Details:**
    - When an instance holds additional addresses, the address column appends `+N`, where N is how many — for example `10.202.9.213 (enp5s0) +3`. The addresses themselves are deliberately not spelled out here: the column is 25 characters wide and a single `address (device)` entry already fills most of it, so listing them inline would truncate immediately and convey less than the counter does. Use [`figo instance additional_ip list`](#figo-instance-additional_ip-list) to see them, with MAC and label.
    - The counter is shown for the same reason the addresses are tracked at all: they are part of the occupancy of the subnet, and a listing with no trace of them would suggest that those addresses are free.

    - With `-a/--additional` the counter is expanded: every additional address held by an instance gets **its own row**, placed under the instance that holds it. On those rows `TYPE` reads `additional_ip`, while `STATE` and `CONTEXT` are left empty — they describe an instance, and an address is not one. Two columns are added, `NAME` and `MAC`, carrying the label and the MAC recorded for the address, and empty on ordinary instance rows.

      ```
      INSTANCE         TYPE          STATE CONTEXT                   IP ADDRESS(ES)            NAME         MAC
      ioam-factory     vm            run   blade3:figo-ioam-factory  10.202.9.213 (enp5s0) +3
      ioam-factory     additional_ip                                 10.202.9.214              gob0         52:54:00:ca:09:d6
      ioam-factory     additional_ip                                 10.202.9.215              ramon        52:54:00:ca:09:d7
      ioam-factory     additional_ip                                 10.202.9.216              justin       52:54:00:ca:09:d8
      file-server      vm            run   blade3:default            10.202.9.201 (enp5s0)
      ```

      The profiles column is **dropped** in this view. It is empty by definition on the address rows, and the room taken by the wider `TYPE` plus `NAME` and `MAC` would otherwise push the line past the width of a normal terminal, wrapping the profiles in mid-word. Whoever asks for `-a` is looking at addresses, not at profiles.

      The `INSTANCE` column repeats the name of the instance holding the address, so that every row stands on its own and remains meaningful when the output is grepped, sorted or pasted in isolation. The `+N` counter is kept on the instance row, where it now also tells how many rows follow.

  - **Examples:**

    ```bash
    figo instance list
    figo instance list remote:project.
    figo instance list project. -r remote_name
    figo instance list -f --extend
    figo instance list project. -u custom_user
    figo instance list project. -j
    figo instance list project. -j -e
    figo instance list -a
    figo instance list -a -r blade3 --extend
    ```

- #### `figo instance start`

  - **Description:** Start a specific instance, with options to specify remote and project scope.
  - **Syntax:**

    ```bash
    figo instance start instance_name [-r remote] [-p project] [-u user]
    ```
  
  - **Options:**
    - `instance_name`: The name of the instance to start, which can include remote and project scope.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.


  - **Examples:**

    ```bash
    figo instance start instance_name
    figo instance start remote:project.instance_name
    figo instance start instance_name -r remote_name -p project_name
    figo instance start instance_name -u custom_user
    ```

- #### `figo instance stop`

  - **Description:** Stop a specific instance or all instances in a specified scope.
  - **Syntax:**

    ```bash
    figo instance stop [instance_name] [-a | --all] [-r remote] [-p project] [-u user]
    ```

  - **Options:**
    - `instance_name`: The name of the instance to stop, which can include remote and project scope. If `--all` is provided, a specific instance name should not be given.
    - `-a, --all`: Stop all instances in the specified scope.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.

  - **Examples:**

    ```bash
    figo instance stop instance_name
    figo instance stop remote:project.instance_name
    figo instance stop -a -r remote_name
    figo instance stop project. -a
    figo instance stop instance_name -u custom_user
    ```

- #### `figo instance set_key`

  - **Description:** Set a public key for a user in a specific instance. If the `key_filename` is not provided, the system uses a default key derived from the `-u/--user` parameter.
  - **Syntax:**

    ```bash
    figo instance set_key instance_name [key_filename] [-l login] [-d dir] [-f | --force] [-r remote] [-p project] [-u user]
    ```

  - **Options:**
    - `instance_name`: The name of the instance, which can include remote and project scope.
    - `key_filename`: Optional filename of the public key on the host. If not provided, the system derives it based on the `-u/--user` parameter.
    - `-l, --login`: Specify the user login name for which we are setting the key (default: `ubuntu`).
    - `-d, --dir`: Specify the directory path where the key file is located (default: `./users`).
    - `-f, --force`: Start the instance if not running, then stop it after setting the key.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to derive the default key filename if `key_filename` is not provided.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.

  - **Examples:**

    ```bash
    figo instance set_key instance_name key_filename
    figo instance set_key remote:project.instance_name key_filename -r remote_name -p project_name
    figo instance set_key instance_name -u user_name -f
    figo instance set_key remote:project.instance_name -u custom_user -r remote_name
    ```

- #### `figo instance show_keys`

  - **Description:** Display the keys associated with a specific instance, including the key type and the key ID. Optionally specify the remote and project. If the instance is not running, you can force-start it using the `-f/--force` option.
  - **Syntax:**

    ```bash
    figo instance show_keys instance_name [-r remote] [-p project] [-l login] [-f | --force] [-k | --keys] [-e | --extend] [-u user]
    ```

  - **Options:**
    - `instance_name`: The name of the instance. Can include remote and project scope in the format `remote:project.instance_name`.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-l, --login`: Specify the user login name for which we are showing the keys (default: `ubuntu`).
    - `-f, --force`: Start the instance if not running, then stop it after fetching the keys.
    - `-k, --keys`: Show full key details, including the full key content.
    - `-e, --extend`: Extend column widths to fit content for better readability.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.

  - **Examples:**

    ```bash
    figo instance show_keys instance_name
    figo instance show_keys remote:project.instance_name
    figo instance show_keys instance_name -r remote_name -p project_name
    figo instance show_keys instance_name -l custom_user -f -k --extend
    figo instance show_keys instance_name -u user_name -r remote_name
    ```

- #### `figo instance set_ip`

  - **Description:** Set a static IP address and gateway for a stopped instance. If an IP address is not provided, an available IP address is assigned. By default, assigns the next IP address after the highest assigned IP; with `--hole`, assigns the first available gap in the IP range.
  - **Syntax:**

    ```bash
    figo instance set_ip instance_name [-i ip_address] [-g gw_address] [-n nic] [-r remote] [-p project] [-u user] [-o | --hole]
    ```

  - **Options:**
    - `instance_name`: The name of the instance, which can include remote and project scope.
    - `-i, --ip`: Specify a static IP address with prefix length (e.g., `192.168.1.10/24`). If omitted, an available IP address is assigned based on the highest IP in use, or the first available gap if `--hole` is used.
    - `-g, --gw`: Specify the gateway address. If omitted, the default gateway for the remote is used.
    - `-n, --nic`: Specify the NIC name (default: `eth0` for containers, `enp5s0` for VMs).
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.
    - `-o, --hole`: Assigns the first available IP address hole in the range rather than the next sequential IP.

  - **Examples:**

    ```bash
    figo instance set_ip instance_name -i 192.168.1.10/24 -g 192.168.1.1
    figo instance set_ip remote:project.instance_name -i 10.0.0.5/24 -g 10.0.0.1
    figo instance set_ip my_remote:my_project.instance_name --hole
    figo instance set_ip remote:project.instance_name
    figo instance set_ip instance_name -u custom_user -n eth1 -r remote_name
    ```

- #### `figo instance additional_ip`

  - **Description:** Manage the **additional IP addresses held by an instance**. Besides the address configured on the instance itself (see [`figo instance set_ip`](#figo-instance-set_ip)), an instance may hold further addresses of the same subnet: addresses used by nested QEMU virtual machines it runs, by containers started inside it, or simply extra addresses configured on its own NIC. Registering them makes figo's IPAM aware that those addresses are taken, so they are never handed out to another instance.

    figo deliberately does **not** model what sits behind an additional address. It records the address, optionally a MAC and a label, and nothing else.

  - **Subcommands:**
    - [`figo instance additional_ip list`](#figo-instance-additional_ip-list)
    - [`figo instance additional_ip add`](#figo-instance-additional_ip-add)
    - [`figo instance additional_ip remove`](#figo-instance-additional_ip-remove)

  - **Details:**

    - **figo records, it does not configure.** These commands change figo's bookkeeping only. No interface is created, no address is applied inside the instance, no DHCP reservation is written. Whatever uses the address must be configured by whoever runs it. Consequently the instance does **not** need to be stopped (unlike `set_ip`) and is never restarted.

    - **Same allocation pool as instances.** Additional addresses are drawn from the same pool as instance addresses. An additional address can therefore never collide with an instance address, nor with an additional address of another instance.

    - **Where the state is kept.** In the instance configuration, under the `user.figo.additional_ips` key, as a YAML list. It is visible with `incus config show <instance>` and it is deleted together with the instance, so an instance can never leave stale address registrations behind. Example of a stored value:

      ```yaml
      - ip: 10.202.9.214
        mac: 52:54:00:ca:09:d6
        name: gob0
      - ip: 10.202.9.215
        name: dev-guest
      ```

    - **Relation to L1 hosts and `user.l2_ip_list`.** An L1 host records, in a separate `user.l2_ip_list` key, the addresses of the nested **Incus** instances that figo itself created through the L1 remote. The two keys are distinct and both are honoured by the allocator, because they hold different kinds of fact: `l2_ip_list` is an *index* of instances that exist as objects elsewhere, while `additional_ips` is a *primary record* of addresses about which figo knows nothing else. Neither replaces the other, and an address should appear in only one of them.

- #### `figo instance additional_ip list`

  - **Description:** List the additional IP addresses held by an instance, or by all the instances in a scope.
  - **Syntax:**

    ```bash
    figo instance additional_ip list [instance_name] [-r remote] [-p project] [-u user] [-e | --extend]
    ```

  - **Options:**
    - `instance_name`: The name of the instance, which can include remote and project scope. If omitted, the additional addresses of all the instances in the scope are listed.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.
    - `-e, --extend`: Extend column width to fit the content.

  - **Details:**
    - The table reports, for each entry, the holding instance, the address, the MAC (if recorded) and the label (if any).
    - [`figo instance list`](#figo-instance-list) does not spell out these addresses: it only appends `+N` to the address of the instance holding them, as a reminder that they exist. This command is where the addresses themselves are shown, which makes it the way to answer "who is using this address?".

  - **Examples:**

    ```bash
    figo instance additional_ip list
    figo instance additional_ip list ioam-factory
    figo instance additional_ip list blade3:figo-ioam-factory.ioam-factory
    figo instance additional_ip list -r blade3 --extend
    figo instance additional_ip list -u custom_user
    ```

- #### `figo instance additional_ip add`

  - **Description:** Register an additional IP address held by an instance. If the address is not provided, an available one is assigned and printed. By default the next address after the highest assigned one is used; with `--hole`, the first available gap in the range.
  - **Syntax:**

    ```bash
    figo instance additional_ip add instance_name [ip_address] [--mac mac_address | --mac auto] [-n name] [-r remote] [-p project] [-u user] [-o | --hole]
    ```

  - **Options:**
    - `instance_name`: The name of the instance holding the address, which can include remote and project scope.
    - `ip_address`: Optional. The address to register, without prefix length (e.g. `10.202.9.214`). If omitted, figo assigns an available address and prints it.
    - `--mac`: Record a MAC address for the entry. With the literal value `auto`, figo derives it deterministically from the IP address (prefix `52:54:00` followed by the last three octets), which guarantees uniqueness within the subnet without maintaining a second registry. If the option is omitted, no MAC is recorded.
    - `-n, --name`: A free-form label for the entry, to record what the address is used for.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.
    - `-o, --hole`: Assigns the first available IP address hole in the range rather than the next sequential IP. Only meaningful when `ip_address` is omitted.

  - **Details:**
    - **Both forms are validated.** Whether the address is chosen by figo or passed explicitly, the command **fails** if it is already assigned to an instance, already registered as an additional address of any instance, already listed by an L1 host, or outside the subnet of the remote. An explicit address is therefore just as safe against double assignment as an automatic one. Note that the check and the registration are not atomic, so — exactly as for `set_ip` and `create` — two concurrent figo invocations can still end up choosing the same address.
    - **On success the address, and only the address, is printed on standard output**, so that the command can be used as `IP=$(figo instance additional_ip add my_instance --mac auto)`. Log messages go to standard error.
    - **Letting figo choose is still the better habit**, for a different reason than safety: when a human picks the address, the choice tends to follow conventions that live in people's heads rather than in figo — "the top of the range is for nested guests", "leave a gap after the servers". figo cannot see those conventions, and will happily allocate into them later.
    - Omitting `--mac` is the right choice when the address is an extra address on the instance's own NIC, where a distinct MAC would be meaningless. It is normally recorded when the address belongs to a virtual machine or a container running inside the instance, which has its own interface on the bridge.

  - **Examples:**

    ```bash
    # Let figo assign the address, and print it
    figo instance additional_ip add ioam-factory

    # Address assigned by figo, MAC derived from it, labelled
    figo instance additional_ip add ioam-factory --mac auto -n gob0

    # Fully explicit
    figo instance additional_ip add blade3:figo-ioam-factory.ioam-factory 10.202.9.214 --mac 52:54:00:ca:09:d6 -n gob0

    # Reuse a gap left by a removed entry rather than growing the range
    figo instance additional_ip add ioam-factory --hole --mac auto -n justin

    figo instance additional_ip add my_instance -u custom_user -r remote_name
    ```

- #### `figo instance additional_ip remove`

  - **Description:** Remove one additional IP address registration from an instance, or all of them.
  - **Syntax:**

    ```bash
    figo instance additional_ip remove instance_name [ip_address] [-a | --all] [-r remote] [-p project] [-u user]
    ```

  - **Options:**
    - `instance_name`: The name of the instance, which can include remote and project scope.
    - `ip_address`: The address to remove. Must not be given together with `--all`.
    - `-a, --all`: Remove every additional address registered for the instance.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.

  - **Details:**
    - Exactly one of `ip_address` and `--all` must be provided; giving both, or neither, is an error.
    - Removing a registration only frees the address for future allocation. Whatever was using it is not stopped or reconfigured, so remove the entry **after** the entity behind it is gone, not before.

  - **Examples:**

    ```bash
    figo instance additional_ip remove ioam-factory 10.202.9.214
    figo instance additional_ip remove blade3:figo-ioam-factory.ioam-factory 10.202.9.214
    figo instance additional_ip remove ioam-factory --all
    figo instance additional_ip remove my_instance 10.0.0.5 -u custom_user -r remote_name
    ```

- #### `figo instance create`

  - **Description:** Create a new instance with optional specifications for image, type, profiles, IP settings, and adding a public key for access. If the IP address is not provided, an available IP address is automatically assigned. By default, assigns the next IP after the highest assigned IP; with `--hole`, assigns the first available gap in the IP range. If the `-k/--key` option is used, a public key is added to the `authorized_keys` file of the instance.
  - **Syntax:**

    ```bash
    figo instance create instance_name image [-t type] [-p project] [-r remote] [-i ip_address] [-g gw_address] [-n nic] [-f profiles] [-o | --hole] [-m | --make_project] [-u user] [-k | --key] [-l login]
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
    - `-u, --user`: Specify the username to infer the project and derive the public key for `-k/--key`.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.
    - `-k, --key`: Add the user's public key to the instance's `authorized_keys` file. Requires `-u/--user`.
    - `-l, --login`: Specify the user login name on the instance for which the key provides access (optional, default: `ubuntu`).

  - **Examples:**

    ```bash
    figo instance create my_instance images:ubuntu/20.04
    figo instance create remote:project.instance_name images:debian/11 -t vm
    figo instance create instance_name images:centos/8 -r remote_name -p project_name
    figo instance create instance_name images:ubuntu/22.04 -f profile1,profile2
    figo instance create instance_name images:alpine/3.15 -m --hole
    figo instance create instance_name images:fedora/35 -u custom_user -n eth1 -r remote_name
    figo instance create instance_name images:ubuntu/22.04 -u custom_user -k
    figo instance create instance_name images:debian/11 -u custom_user -k -l newlogin
    ```
- #### `figo instance delete`

  - **Description:** Delete a specific instance, with an option to force delete if the instance is running.
  - **Syntax:**

    ```bash
    figo instance delete instance_name [-f | --force] [-r remote] [-p project] [-u user]
    ```

  - **Options:**
    - `instance_name`: The name of the instance to delete, which can include remote and project scope.
    - `-f, --force`: Force delete the instance even if it is running.
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.

  - **Examples:**

    ```bash
    figo instance delete instance_name
    figo instance delete remote:project.instance_name -f
    figo instance delete instance_name -r remote_name -p project_name
    figo instance delete instance_name -u custom_user -r remote_name
    ```

---

- #### `figo instance bash`

  - **Description:** Execute bash in a specific instance, with an option to start the instance if it is not running.
  - **Syntax:**

    ```bash
    figo instance bash instance_name [-f | --force] [-t timeout] [-a attempts] [-r remote] [-p project] [-u user]
    ```

  - **Options:**
    - `instance_name`: The name of the instance to execute bash, which can include remote and project scope.
    - `-f, --force`: Start the instance if not running and execute bash. Stop the instance on exit if it was initially stopped.
    - `-t, --timeout`: Total timeout in seconds for retries (default: `30`).
    - `-a, --attempts`: Number of retry attempts to connect (default: `3`).
    - `-r, --remote`: Specify the remote server name.
    - `-p, --project`: Specify the project name.
    - `-u, --user`: Specify the username to infer the project.
    - `-x, --relax`: Use `-u/--user` only for key filename derivation, no consistency checks between `-p/--project` and `-u/--user`.

  - **Examples:**

    ```bash
    figo instance bash instance_name
    figo instance bash remote:project.instance_name
    figo instance bash instance_name -f -r remote_name -p project_name
    figo instance bash instance_name -u custom_user -r remote_name -a 5
    ```

### figo gpu

- **Aliases:** `gp`, `g`
- **Description:** Manage GPUs in instances within the federated testbed. This includes monitoring GPU status, managing GPU profiles, and retrieving hardware information for resource allocation.

#### Features:
- **Monitor GPU Status:** Check the availability and usage of GPUs on local or remote nodes.
- **Manage GPU Profiles:** Add or remove GPU profiles to/from instances.
- **Retrieve PCI Addresses:** Obtain detailed information about GPU PCI addresses for hardware-specific operations.
- **Support for Scopes:** Perform GPU management tasks at the remote, project, or instance level.
- **Flexible Options:** Extend column widths for better readability and specify users, projects, or remotes to customize operations.

#### Example Use Cases:
- **Resource Allocation:** Assign GPU resources to instances based on project requirements.
- **Monitoring Utilization:** Keep track of GPU usage across multiple nodes in the testbed.
- **Dynamic Scaling:** Add or remove GPU profiles dynamically to meet the changing workload demands of instances.
- **Hardware Diagnostics:** Retrieve PCI addresses to debug hardware-specific issues or optimize configurations.

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
      # Show GPU status for the local node
      figo gpu status

      # Show GPU status for a specific remote
      figo gpu status my_remote:

      # Show GPU status with extended column widths
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
      # List GPU profiles on the local node
      figo gpu list

      # List GPU profiles on a specific remote
      figo gpu list my_remote:

      # List GPU profiles with extended column widths
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
    # Add a GPU profile to an instance in the default project on the local server
    figo gpu add my_instance

    # Add a GPU profile to an instance on the local server in a specific project
    figo gpu add instance_name -p my_project

    # Add a GPU profile to an instance on a specific remote in the default project
    figo gpu add instance_name -r my_remote    

    # Add a GPU profile to an instance on a specific remote in a specific project
    figo gpu add my_project.instance_name -r my_remote
    
    # Add a GPU profile to an instance on a specific remote in a specific project
    figo gpu add my_remote:my_project.instance_name

    # Add a GPU profile to an instance on a specific remote in a specific project
    figo gpu add instance_name -p my_project -r my_remote

    # Add a GPU profile to an instance on the local server, inferring the project from the user name
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
    # Display PCI addresses of GPUs on the local node
    figo gpu pci_addr

    # Display PCI addresses of GPUs on a specific remote
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

  - **Description:** Initialize profiles on a remote by transferring a set of required profiles from `local:default` to `remote:default`. Optionally, specify a custom list of profiles to transfer or list the default profiles.
  - **Syntax:**
      ```bash
      figo profile init remote [-f | --profile profiles]
      figo profile init -l | --list
      ```
  - **Options:**
      - `remote`: Name of the remote to initialize. Can be specified as `my_remote` or `my_remote:`.
      - `-f, --profile`: Comma-separated list of profiles to transfer. Overrides the default list of profiles, which is hard-coded in the figo code.
      - `-l, --list`: Display the default set of profiles that would be transferred during initialization. Cannot be used with a target remote.

  - **Details:**
      - If the remote already has a profile with the same name, it will not be overwritten.
      - If no custom list of profiles is provided, the default list of profiles is used.
      - The `-l/--list` option outputs the default profiles and does not perform the initialization process.
      - Using `-l/--list` alongside a `remote` argument results in an error.

  - **Examples:**
      ```bash
      # Initialize remote with the default set of profiles
      figo profile init my_remote

      # Initialize remote with a custom list of profiles
      figo profile init my_remote -f profile1,profile2,profile3

      # Initialize a remote with the default set, specifying the remote with a colon
      figo profile init my_remote:

      # Display the default set of profiles for initialization
      figo profile init -l
      ```   ```

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

  - **Description:** List users, with options to show detailed information, include VPN IP addresses, and extend column width for better readability.
  - **Syntax:**
    ```bash
    figo user list [-f | --full] [-e | --extend] [-i | --ip]
    ```
  - **Options:**
    - `-f, --full`: Show full details of users.
    - `-i, --ip`: Include the WireGuard VPN IP address assigned to the user.
    - `-e, --extend`: Extend column width to fit the content.
  - **Examples:**
    ```bash
    figo user list
    figo user list --full
    figo user list --extend
    figo user list --ip
    figo user list --full --ip --extend
    ```

- #### `figo user add`

  - **Description:** Add a new user to the system.
  - **Syntax:**
    ```bash
    figo user add username [-c | --cert cert_filename] [-a | --admin] [-w | --wireguard] [-s | --set_vpn] [-p | --project project_name] [-e | --email email] [-n | --name full_name] [-o | --org organization] [-k | --keys]
    ```
  - **Options:**
    - `username`: Username of the new user.
    - `-c, --cert`: Path to the user's certificate file for GUI access in .crt format. If not provided, a new key pair will be generated.
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

  - **Description:** Delete an existing user from the system, with optional control over file retention, project purging, and VPN entry cleanup.
  - **Syntax:**
    ```bash
    figo user delete username [-p | --purge] [-k | --keepfiles] [-n | --no_vpn]
    ```
  - **Options:**
    - `username`: Username of the user to delete.
    - `-p, --purge`: Delete associated projects and user files, even if the user does not exist.
    - `-k, --keepfiles`: Keep the associated files of the user in the users folder.
    - `-n, --no_vpn`: Do not clean the WireGuard user entry in the access router.
  - **Examples:**
    ```bash
    figo user delete john_doe
    figo user delete alice --purge
    figo user delete jane -k
    figo user delete bob -n
    figo user delete charlie --purge --no_vpn
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

### figo operation

- **Description:** Manage and monitor operations across the federated testbed.

#### Subcommands:
- [`figo operation status`](#figo-operation-status)
- [`figo operation progress`](#figo-operation-progress)

#### Subcommands details

- #### `figo operation status`

  - **Description:** Display the status of ongoing operations on remotes and projects.
  - **Syntax:**
    ```bash
    figo operation status [scope] [-p | --project project_name] [-e | --extend]
    ```
  - **Options:**
    - `scope`: Scope in the format `remote:project`, `remote:`, or `project.` to filter the operations. Can also include `remote:project.` (with the final dot).
    - `-p, --project`: Specify the project name to filter operations. If both `scope` and `--project` are provided, they must match; otherwise, an error is returned.
    - `-e, --extend`: Extend column width to fit the content for better readability.

  - **Details:**
    - When the `scope` specifies a remote and project, only operations in that scope are displayed.
    - When no scope or `--project` is provided, all ongoing operations on all remotes and projects are displayed.
    - Consistency between the project specified in `scope` and `--project` is enforced.

  - **Examples:**
    ```bash
    # Display status for all ongoing operations
    figo operation status

    # Display status for a specific remote
    figo operation status my_remote

    # Display status for a specific remote and project
    figo operation status my_remote:project_name

    # Display status for a specific remote and project (with final dot)
    figo operation status my_remote:project_name.

    # Display status for a specific project using the --project option
    figo operation status -p my_project

    # Display status for a specific remote and project, ensuring consistency
    figo operation status my_remote:project_name -p project_name
    ```

- #### `figo operation progress`

  - **Description:** Display the status of ongoing "create instance" operations on remotes and projects.
  - **Syntax:**
    ```bash
    figo operation progress [scope] [-p | --project project_name] [-e | --extend]
    ```
  - **Options:**
    - `scope`: Scope in the format `remote:project`, `remote:`, or `project.` to filter the operations. Can also include `remote:project.` (with the final dot).
    - `-p, --project`: Specify the project name to filter operations. If both `scope` and `--project` are provided, they must match; otherwise, an error is returned.
    - `-e, --extend`: Extend column width to fit the content for better readability.

  - **Details:**
    - When the `scope` specifies a remote and project, only "create instance" operations in that scope are displayed.
    - When no scope or `--project` is provided, all ongoing "create instance" operations on all remotes and projects are displayed.
    - Consistency between the project specified in `scope` and `--project` is enforced.

  - **Examples:**
    ```bash
    # Display progress for all "create instance" operations
    figo operation progress

    # Display progress for a specific remote
    figo operation progress my_remote

    # Display progress for a specific remote and project
    figo operation progress my_remote:project_name

    # Display progress for a specific remote and project (with final dot)
    figo operation progress my_remote:project_name.

    # Display progress for a specific project using the --project option
    figo operation progress -p my_project

    # Display progress for a specific remote and project, ensuring consistency
    figo operation progress my_remote:project_name -p project_name
    ```

### figo vpn

- **Description:** Manage VPN configuration for secure communication and routing. The `figo vpn` command enables adding and configuring VPN routes for different device types, including Linux and MikroTik routers. This is essential for maintaining secure and efficient network operations across federated environments.

#### Features:
- Configure routes dynamically for different VPN device types (`mikrotik`, `linux`).
- Support for target-based configuration using predefined settings from the ACCESS_ROUTER_TARGETS dictionary.
- Host-based configuration with optional user and port settings.

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
    # Add a route using a target name found in ACCESS_ROUTER_TARGETS
    figo vpn add route 10.10.128.0/24 via 10.10.10.2 type mikrotik target my-target-name

    # Add a route using a host address with explicit user and port
    figo vpn add route 10.10.128.0/24 via 10.10.10.2 type mikrotik host 160.80.10.2 --user myuser --port 22

    # Add a route using a host address with default user and port
    figo vpn add route 10.10.128.0/24 via 10.10.10.2 type mikrotik host 160.80.10.2

    # Add a route to a network into a Linux router using device interface
    figo vpn add route 10.10.0.0/16 via 10.202.128.1 --dev wg128 type linux target my-linux

    # Add a route for extending a network to eln_cloud
    figo vpn add route 10.202.10.0/24 via 10.202.9.2 type mikrotik target mikrotik-rm2
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
