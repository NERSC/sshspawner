import asyncio, asyncssh
import os
from textwrap import dedent
import warnings

from traitlets import Bool, Unicode, Integer, List, observe

from jupyterhub.spawner import Spawner


class SSHSpawner(Spawner):

    # http://traitlets.readthedocs.io/en/stable/migration.html#separation-of-metadata-and-keyword-arguments-in-traittype-contructors
    # config is an unrecognized keyword

    remote_host = Unicode("remote_host",
            help="SSH remote host to spawn sessions on",
            config=True)

    remote_port = Integer(22,
            help="SSH remote port number",
            config=True)

    path = Unicode("/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin",
            help="Default PATH (should include jupyter and python)",
            config=True)

    # FIXME Fix help, what happens when not set?
    hub_api_url = Unicode("",
            help=dedent("""If set, Spawner will configure the containers to use
            the specified URL to connect the hub api. This is useful when the
            hub_api is bound to listen on all ports or is running inside of a
            container."""),
            config=True)

    ssh_keyfile = Unicode("~/.ssh/id_rsa",
            help=dedent("""Key file used to authenticate hub with remote host.

            `~` will be expanded to the user's home directory and `{username}`
            will be expanded to the user's username"""),
            config=True)

    pid = Integer(0,
            help=dedent("""Process ID of single-user server process spawned for
            current user."""))

    # TODO When we add host pool, we need to keep host/ip too, not just PID.
    def load_state(self, state):
        """Restore state about ssh-spawned server after a hub restart.

        The ssh-spawned processes only need the process id."""
        super().load_state(state)
        if "pid" in state:
            self.pid = state["pid"]

    # TODO When we add host pool, we need to keep host/ip too, not just PID.
    def get_state(self):
        """Save state needed to restore this spawner instance after hub restore.

        The ssh-spawned processes only need the process id."""
        state = super().get_state()
        if self.pid:
            state["pid"] = self.pid
        return state

    # TODO When we add host pool, we need to clear host/ip too, not just PID.
    def clear_state(self):
        """Clear stored state about this spawner (pid)"""
        super().clear_state()
        self.pid = 0

    # FIXME this looks like it's done differently now, there is get_env which
    # actually calls this.
    def user_env(self):
        """Augment env of spawned process with user-specific env variables."""

        # FIXME I think the JPY_ variables have been deprecated in JupyterHub
        # since 0.7.2, we should replace them.  Can we figure this out?

        env = super(SSHSpawner, self).get_env()
        env.update(dict(
            JPY_USER=self.user.name,
            JPY_BASE_URL=self.user.server.base_url,
            JPY_HUB_PREFIX=self.hub.server.base_url,
            JUPYTERHUB_PREFIX=self.hub.server.base_url,
            PATH=self.path
        ))

        if self.notebook_dir:
            env['NOTEBOOK_DIR'] = self.notebook_dir

        hub_api_url = self.hub.api_url
        if self.hub_api_url != '':
            hub_api_url = self.hub_api_url

        env['JPY_HUB_API_URL'] = hub_api_url
        env['JUPYTERHUB_API_URL'] = hub_api_url

        return env

    async def start(self):
        """Start single-user server on remote host."""
        
        port = int(self.remote_port)
        cmd = []

        cmd.extend(self.cmd)
        cmd.extend(self.get_args())

        if self.hub_api_url != "":
            old = "--hub-api-url={}".format(self.hub.api_url)
            new = "--hub-api-url={}".format(self.hub_api_url)
            for index, value in enumerate(cmd):
                if value == old:
                    cmd[index] = new
        for index, value in enumerate(cmd):
            if value[0:6] == '--port':
                cmd[index] = '--port=%d' % (port)

        remote_cmd = ' '.join(cmd)

        self.pid = await self.exec_notebook(remote_cmd)

        self.log.debug("Starting User: {}, PID: {}".format(self.user.name, self.pid))

        if self.pid < 0:
            return None
        # DEPRECATION: Spawner.start should return a url or (ip, port) tuple in JupyterHub >= 0.9
        return (self.remote_host, port)

    async def poll(self):
        """Poll ssh-spawned process to see if it is still running.

        If it is still running return None. If it is not running return exit
        code of the process if we have access to it, or 0 otherwise."""

        if not self.pid:
                # no pid, not running
            self.clear_state()
            return 0

        # send signal 0 to check if PID exists
        alive = await self.remote_signal(0)
        self.log.debug("Polling returned {}".format(alive))

        if not alive:
            self.clear_state()
            return 0
        else:
            return None

    async def stop(self, now=False):
        """Stop single-user server process for the current user."""
        alive = await self.remote_signal(15)
        self.clear_state()

    def get_remote_user(self, username):
        """Map JupyterHub username to remote username."""
        return username

    @observe('remote_host')
    def _log_remote_host(self, change):
        self.log.debug("Remote host was set to %s." % self.remote_host)

    # FIXME add docstring
    async def exec_notebook(self, command):
        """TBD"""

        env = self.user_env()
        username = self.get_remote_user(self.user.name)
        k = asyncssh.read_private_key(self.ssh_keyfile.format(username=self.user.name))
        bash_script_str = "#!/bin/bash\n"

        for item in env.items():
            # item is a (key, value) tuple
            # command = ('export %s=%s;' % item) + command
            bash_script_str += 'export %s=%s\n' % item
        bash_script_str += 'unset XDG_RUNTIME_DIR\n'

        bash_script_str += '%s < /dev/null >> jupyter.log 2>&1 & pid=$!\n' % command
        bash_script_str += 'echo $pid\n'

        run_script = "/tmp/{}_run.sh".format(self.user.name)
        with open(run_script, "w") as f:
            f.write(bash_script_str)
        if not os.path.isfile(run_script):
            raise Exception("The file " + run_script + "was not created.")
        else:
            with open(run_script, "r") as f:
                self.log.debug(run_script + " was written as:\n" + f.read())

        async with asyncssh.connect(self.remote_host,username=username,client_keys=[k],known_hosts=None) as conn:
            result = await conn.run("bash -s", stdin=run_script)
            stdout = result.stdout
            stderr = result.stderr
            retcode = result.exit_status

        self.log.debug("exec_notebook status={}".format(retcode))
        if stdout != b'':
            pid = int(stdout)
        else:
            return -1

        return pid

    async def remote_signal(self, sig):
        """Signal on the remote host."""

        username = self.get_remote_user(self.user.name)
        k = asyncssh.read_private_key(self.ssh_keyfile.format(username=self.user.name))

        command = "kill -s %s %d < /dev/null"  % (sig, self.pid)

        async with asyncssh.connect(self.remote_host,username=username,client_keys=[k],known_hosts=None) as conn:
            result = await conn.run(command)
            stdout = result.stdout
            stderr = result.stderr
            retcode = result.exit_status
        self.log.debug("command: {} returned {} --- {} --- {}".format(command, stdout, stderr, retcode))
        return (retcode == 0)
