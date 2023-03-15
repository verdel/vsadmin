#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import click

CONTEXT_SETTINGS = dict(auto_envvar_prefix='VSADMIN')


class Context(object):

    def log(self, msg, *args):
        """Logs a message to stdout."""
        if args:
            msg %= args
        click.echo(msg)

    def logerr(self, msg, *args):
        """Logs a message to stderr only if verbose is enabled."""
        if args:
            msg %= args
        click.echo(msg, err=True)


pass_context = click.make_pass_decorator(Context, ensure=True)
cmd_folder = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                          'commands'))


class ComplexCLI(click.MultiCommand):

    def list_commands(self, ctx):
        rv = []
        for filename in os.listdir(cmd_folder):
            if filename.endswith('.py') and \
               filename.startswith('cmd_'):
                rv.append(filename[4:-3])
        rv.sort()
        return rv

    def get_command(self, ctx, name):
        ns = {}
        fn = os.path.join(cmd_folder, 'cmd_' + name + '.py')
        with open(fn) as f:
            code = compile(f.read(), fn, 'exec')
            eval(code, ns, ns)
        return ns['cli']


@click.command(cls=ComplexCLI, context_settings=CONTEXT_SETTINGS)
@click.option('-u', '--username',
              default=lambda: os.environ.get('VSADMIN_USERNAME'),
              help='Username for vSphere.')
@click.option('-p', '--password', hide_input=True,
              default=lambda: os.environ.get('VSADMIN_PASSWORD'),
              help='Password for vSphere.')
@click.option('-s', '--server',
              default=lambda: os.environ.get('VSADMIN_SERVER'),
              help='vCenter address.')
@click.option('--disable-ssl-verification', is_flag=True, default=True,
              show_default=True, help='Disable SSL verification.')

@pass_context
def cli(ctx, username, password, server, disable_ssl_verification):
    """Console utility for Vmware vSphere management."""
    ctx.username = username
    ctx.password = password
    ctx.server = server
    ctx.disable_ssl_verification = disable_ssl_verification
