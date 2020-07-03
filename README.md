# VSADMIN - VMware vSphere CLI

What is this?
-------------
With this simple VMware vSphere console client you can search virtual machine object by it's Name, IP, MAC, Hostname or information in Notes field.
You can get information about this virtual machines (Hardware parameters, Cluster, Folder, Datastores, Storage Policies, Network, etc)

Installation
------------
on most UNIX-like systems, you'll probably need to run the following
`install` commands as root or by using `sudo`

**from source**
```console
pip install git+https://github.com/verdel/vsadmin
```
**or**
```console
git clone https://github.com/verdel/vsadmin.git
cd vsadmin
python setup.py install
```

as a result, the ``vsadmin`` executable will be installed into a system ``bin``
directory

Usage
-----
Execute `vsadmin` with `--server`, `--username`, `--password` options or set environment variables `VSADMIN_SERVER`, `VSADMIN_USERNAME`, `VSADMIN_PASSWORD`

With the environment variables set, running the command will look like this:

`vsadmin search --ip 192.168.1.1`

To view all the options that you can use to search for a VM, use the `--help` option:

```bash
> vsadmin search --help

Usage: vsadmin search [OPTIONS]

  Search vm entry information in vCenter.

Options:
  --name <Virtual Machine Name>  name of vm entry to search
  --contains                     search not only complete but also partial
                                 virtual machine name matches

  --mac <MAC Address>            mac of vm entry to search
  --ip <IP Address>              ip of vm entry to search
  --custom-fields                search IP in custom_fields too
  --hostname <Domain Name>       hostname of vm entry to search
  --task <Service Desk Task ID>  service desk task id of vm entry to search
  -i, --interval <Int>           interval in minutes to average the vSphere
                                 stats over  [default: 20]

  -v, --verbose                  show advanced information about virtual
                                 machine

  --help                         Show this message and exit.
```

Contributing
------------

1. Check the open issues or open a new issue to start a discussion around
   your feature idea or the bug you found
2. Fork the repository and make your changes
3. Open a new pull request

If your PR has been waiting a while, feel free to [ping me on Twitter][twitter].

Use this software often? <a href="https://saythanks.io/to/valeksandrov@me.com" target="_blank"><img src="https://img.shields.io/badge/Say%20Thanks-!-1EAEDB.svg" align="center" alt="Say Thanks!"></a>
:smiley:


[twitter]: http://twitter.com/verdel