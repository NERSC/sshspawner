import asyncio
import os
import shlex
from textwrap import dedent
import warnings

from traitlets import Bool, Unicode, Integer

from jupyterhub.spawner import Spawner


class SSHSpawner(Spawner):
    
    remote_host = Unicode("remote_host",
            help="SSH remote host to spawn sessions on",
            config=True)

    remote_port = Unicode("22",
            help="SSH remote port number",
            config=True)

    ssh_command = Unicode("/usr/bin/ssh",
            help="Actual SSH command",
            config=True)

    path = Unicode("/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin",
            help="Default PATH (should include jupyter and python)",
            config=True)

    # The get_port.py script is in scripts/get_port.py
    # FIXME See if we avoid having to deploy a script on remote side?
    # For instance, we could just install sshspawner on the remote side
    # as a package and have it put get_port.py in the right place.
    # If we were fancy it could be configurable so it could be restricted
    # to specific ports.
    remote_port_command = Unicode("/usr/local/bin/get_port.py",
            help="Command to return unused port on remote host",
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
            Assumes use_gsi=False. (use_gsi=False is deprecated)

            `~` will be expanded to the user's home directory and `{username}`
            will be expanded to the user's username"""),
            config=True)

    # DEPRECATED
    use_gsi = Bool(False,
            help="""Use GSI authentication instead of SSH keys. Assumes you
            have a cert/key pair at the right path. Use in conjunction with
            GSIAuthenticator. (Deprecated)""",
            config=True)

    gsi_cert_path = Unicode("/tmp/x509_{username}",
            help=dedent("""GSI certificate used to authenticate hub with remote
            host.  Assumes use_gsi=True. (Deprecated)

            `~` will be expanded to the user's home directory and `{username}`
            will be expanded to the user's username"""),
            config=True)

    gsi_key_path = Unicode("/tmp/x509_{username}",
             help=dedent("""GSI key used to authenticate hub with remote host.
             Assumes use_gsi=True. (Deprecated)

             `~` will be expanded to the user's home directory and `{username}`
             will be expanded to the user's username"""),
             config=True)

    # FIXME this should be a traitlet probably?
    pid = None

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
            JPY_COOKIE_NAME=self.user.server.cookie_name,
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

        port = await self.remote_random_port()
        if port is None or port == 0:
            return False
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

        # time.sleep(2)
        # import pdb; pdb.set_trace()

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

    # FIXME handle the now business like the documentation actually says
    async def stop(self, now=False):
        """Stop single-user server process for the current user.

        If `now` is False (default), shutdown the server as gracefully as possible,
        e.g. starting with SIGINT, then SIGTERM, then SIGKILL.
        If `now` is True, terminate the server immediately.
        The coroutine should return when the process is no longer running."""
        alive = await self.remote_signal(15)
        self.clear_state()

    def get_remote_user(self, username):
        """Map JupyterHub username to remote username."""
        return username

    def get_gsi_cert(self):
        """Get location of x509 user cert. (Deprecated)"""
        return self.gsi_cert_path.format(username=self.user.name)

    def get_gsi_key(self):
        """Get location of x509 user key. (Deprecated)"""
        return self.gsi_key_path.format(username=self.user.name)

    async def remote_random_port(self):
        """Select unoccupied port on the remote host and return it. 
        
        If this fails for some reason return `None`."""

        # FIXME this keeps getting repeated
        # pass this into bash -c 'command'
        # command needs to be in "" quotes, with all the redirection outside
        # eg. bash -c '"ls -la" < /dev/null >> out.txt'

        command = '"{}" < /dev/null'.format(self.remote_port_command)

        stdout, stderr, retcode = await self.execute(command)

        if stdout != b"":
            port = int(stdout)
            self.log.debug("port={}".format(port))
        else:
            port = None
            self.log.error("Failed to get a remote port")
        return port

    # FIXME add docstring
    async def exec_notebook(self, command):
        """TBD"""

        env = self.user_env()
        bash_script_str = "#!/bin/bash\n"

        for item in env.items():
            # item is a (key, value) tuple
            # command = ('export %s=%s;' % item) + command
            bash_script_str += 'export %s=%s\n' % item

        # FIXME this keeps getting repeated
        # pass this into bash -c 'command'
        # command needs to be in "" quotes, with all the redirection outside
        # eg. bash -c '"ls -la" < /dev/null >> out.txt'

        # We pass in /dev/null to stdin to avoid the hang
        # Finally Grab the PID
        # command = '"%s" < /dev/null >> jupyter.log 2>&1 & pid=$!; echo $pid' % command

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

        stdout, stderr, retcode = await self.execute(command, stdin=run_script)
        self.log.debug("exec_notebook status={}".format(retcode))
        if stdout != b'':
            pid = int(stdout)
        else:
            return -1

        return pid

    async def remote_signal(self, sig):
        """Signal on the remote host."""

        command = 'kill -s %s %d' % (sig, self.pid)

        # FIXME this keeps getting repeated
        # pass this into bash -c 'command'
        # command needs to be in "" quotes, with all the redirection outside
        # eg. bash -c '"ls -la" < /dev/null >> out.txt'

        command = '"%s" < /dev/null' % command

        stdout, stderr, retcode = await self.execute(command)
        self.log.debug("command: {} returned {} --- {} --- {}".format(command, stdout, stderr, retcode))
        return (retcode == 0)

    # FIXME clean up
    async def execute(self, command=None, stdin=None):
        """Execute remote command via ssh.

        command: command to execute  (via bash -c command)
        stdin: script to pass in via stdin (via 'bash -s' < stdin)
        executes command on remote system "command" and "stdin" are mutually exclusive."""

        ssh_env = os.environ.copy()

        username = self.get_remote_user(self.user.name)

        ssh_args = "-o StrictHostKeyChecking=no -l {username} -p {port}".format(
            username=username, port=self.remote_port)

        if self.use_gsi:
            warnings.warn("SSHSpawner.use_gsi is deprecated",
                    DeprecationWarning)
            ssh_env['X509_USER_CERT'] = self.get_gsi_cert()
            ssh_env['X509_USER_KEY']  = self.get_gsi_key()
        elif self.ssh_keyfile:
            ssh_args += " -i {keyfile}".format(
                    keyfile=self.ssh_keyfile.format(username=self.user.name))
            ssh_args += " -o preferredauthentications=publickey"

        # DRY (don't repeat yourself)
        def split_into_arguments(self, command):
            self.log.debug("command: {}".format(command))
            commands = shlex.split(command)
            self.log.debug("shlex parsed command as: " +"{{"+ "}}  {{".join(commands) +"}}")
            return commands
    
        if stdin is not None:
            command = "{ssh_command} {flags} {hostname} 'bash -s'".format(
                ssh_command=self.ssh_command,
                flags=ssh_args,
                hostname=self.remote_host,
                stdin=stdin)

            commands = split_into_arguments(self, command)
            # the variable stdin above is the path to a shell script, but what the process requires as stdin is the content of the file itself as a buffer/bytes
            stdin = open(stdin, "rb")
            # it ^ might be better if this were an asyncio.streamwriter or asyncio.subprocess.PIPE, but this still works -- consider it a proof of concept.

            proc = await asyncio.create_subprocess_exec(*commands,
                                            stdin=stdin, 
                                            stdout=asyncio.subprocess.PIPE, 
                                            stderr=asyncio.subprocess.PIPE,
                                            env=ssh_env)
                        
        else:
            command = "{ssh_command} {flags} {hostname} bash -c '{command}'".format(
                ssh_command=self.ssh_command,
                flags=ssh_args,
                hostname=self.remote_host,
                command=command)

            commands = split_into_arguments(self, command)

            proc = await asyncio.create_subprocess_exec(*commands,
                                            stdout=asyncio.subprocess.PIPE, 
                                            stderr=asyncio.subprocess.PIPE,
                                            env=ssh_env)
        
        # DRY
        def log_process(self, returncode, stdout, stderr):
            def bytes_to_string(bytes):
                return bytes.decode().strip()
            stdout, stderr = (bytes_to_string(stdout), bytes_to_string(stderr))
            self.log.debug("subprocess returned exitcode: %s" % returncode)
            self.log.debug("subprocess returned standard output: %s" % stdout)
            self.log.debug("subprocess returned standard error: %s" % stderr)

        try:
            stdout, stderr = await proc.communicate()
        
        # catch wildcard exception
        except Exception as e:
            self.log.debug("execute raised exception %s when trying to run command: %s" % (e, command))
            proc.kill()
            self.log.debug("execute failed done kill")
            stdout, stderr = await proc.communicate()
            self.log.debug("execute failed done communicate")
            log_process(self, proc.returncode, stdout, stderr)
            raise e
        else:
            returncode = proc.returncode
            # account for instances where no Python exceptions, but shell process returns with non-zero exit status
            if returncode != 0:
                self.log.debug("execute failed for command: %s" % command)
                log_process(self, returncode, stdout, stderr)
                
        return (stdout, stderr, returncode)
