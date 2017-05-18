# -*- coding: utf-8 -*-
import sys
import click
from vsadmin.cli import pass_context
from vsadmin.commands.tools import vCenter


@click.command('search', short_help='search vm')
@click.option('--name', metavar='<Virtual Machine Name>', help='name of vm entry to search')
@click.option('--contains', is_flag=True, help='search not only complete but also partial virtual machine name matches')
@click.option('--mac', metavar='<MAC Address>', help='mac of vm entry to search')
@click.option('--ip', metavar='<IP Address>', help='ip of vm entry to search')
@click.option('--hostname', metavar='<Domain Name>', help='hostname of vm entry to search')
@click.option('--task', metavar='<Service Desk Task ID>', help='service desk task id of vm entry to search')
@click.option('-i', '--interval', metavar='<Int>', default=20, show_default=True, help='interval in minutes to average the vSphere stats over')
@click.option('-v', '--verbose', is_flag=True, help='show advanced information about virtual machine')
@pass_context
def cli(ctx, name, contains, mac, ip, hostname, task, verbose, interval):
    """Search vm entry information in vCenter."""
    vc = vCenter(ctx.server, ctx.username, ctx.password)
    vm = None
    if name:
        if contains:
            vm = vc.search_vm_by_name(name, 'contains')
        else:
            vm = vc.search_vm_by_name(name)

    elif ip:
        vm = vc.search_vm_by_ip(ip)

    elif hostname:
        vm = vc.search_vm_by_hostname(hostname)

    elif task:
        vm = vc.search_vm_by_task(task)

    elif mac:
        vm = vc.search_vm_by_mac(mac)

    if vm:
        for item in vm:
            vc.print_vm_info(item, interval=interval, verbose=verbose)
    else:
        ctx.log('There is no VM found.')
        sys.exit(1)
