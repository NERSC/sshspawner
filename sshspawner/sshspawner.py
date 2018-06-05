import os, asyncio
from subprocess import Popen, PIPE, TimeoutExpired


from traitlets import Bool, Unicode, Integer
from tornado import gen


from jupyterhub.spawner import Spawner


class SSHSpawner(Spawner):
    # override default since batch systems typically need longer
    start_timeout = Integer(10).tag(config=True)
    
    remote_host = Unicode('remote_host',
                          help="""The SSH remote host to spawn sessions on."""
                          ).tag(config=True)
    remote_port = Unicode('22',
                          help="""The SSH remote port number."""
                          ).tag(config=True)
    ssh_command = Unicode('ssh',
                          help="""The SSH command."""
                          ).tag(config=True)

    path = Unicode('/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin',
                   help="""The default PATH (which should
                   include the jupyter and python bin directories)
                   """
                   ).tag(config=True)

    remote_port_command = Unicode("/usr/local/bin/get_port.py",
                                  help="""The command to return an unused port
                                  on the remote node.
                                  Copy from scripts/get_port.py to
                                  /usr/local/bin/ on the remote node
                                  """
                                  ).tag(config=True)

    hub_api_url = Unicode('',
                          help="""If set, Spawner will configure the containers
                to use the specified URL to connect the hub api.
                This is useful when the hub_api is bound to listen
                on all ports or is running inside of a container."""
                          ).tag(config=True)

    ssh_keyfile = Unicode('~/.ssh/id_rsa',
                          help="""The keyfile used to authenticate the hub with the remote host.
                          Assumes use_gsi=False.

                          `~` will be expanded to the user's home directory
                          `%U` will be expanded to the user's username"""
                          ).tag(config=True)

    use_gsi = Bool(False,
                   help="""Use GSI authentication instead of SSH keys. Assumes you have a
                   cert/key pair in /tmp/x509_{username}. Use in conjunction
                   with GSIAuthenticator
                   """
                   ).tag(config=True)

    gsi_cert_path = Unicode('/tmp/x509_%U',
                            help="""The GSI certificate used to authenticate the hub with the
                            remote host. (Assumes use_gsi=True)

                            `~` will be expanded to the user's home directory
                            `%U` will be expanded to the user's username
                            """
                            ).tag(config=True)

    gsi_key_path = Unicode('/tmp/x509_%U',
                           help="""The GSI key used to authenticate the hub with the
                           remote host. (Assumes use_gsi=True)

                           `~` will be expanded to the user's home directory
                           `%U` will be expanded to the user's username
                           """
                           ).tag(config=True)

    pid = None

    def get_remote_user(self, username):
        """
        Maps a jupyterhub username to a remote user. Override this if
        you need to return a different name
        """
        return username

    def get_gsi_cert(self):
        """
        Returns location of x509 user cert. Override this if you need to
        return a different path
        """
        return self.gsi_cert_path.replace("%U", self.user.name)

    def get_gsi_key(self):
        """
        Returns location of x509 user key. Override this if you need to
        return a different path
        """
        return self.gsi_key_path.replace("%U", self.user.name)

    async def execute(self, command=None, stdin=None):
        """
        command: command to execute  (via bash -c command)
        stdin: script to pass in via stdin (via 'bash -s' < stdin)
        executes command on remote system "command" and "stdin" are mutually exclusive
        """

        ssh_env = os.environ.copy()

        username = self.get_remote_user(self.user.name)

        if self.ssh_command is None:
            self.ssh_command = 'ssh'

        ssh_args = "-o StrictHostKeyChecking=no -l {username} -p {port}".format(
            username=username, port=self.remote_port)

        if self.use_gsi:
            ssh_env['X509_USER_CERT'] = self.get_gsi_cert()
            ssh_env['X509_USER_KEY']  = self.get_gsi_key()
        elif self.ssh_keyfile:
            ssh_args += " -i {keyfile}".format(
                    keyfile=self.ssh_keyfile.replace("%U", self.user.name))
            ssh_args += " -o preferredauthentications=publickey"

        # This is not very good at handling nested quotes - avoid using quotes in
        # the command and use wrapper scripts as much as possible
        if stdin:
            command = "{ssh_command} {flags} {hostname} 'bash -s' < {stdin}".format(
                ssh_command=self.ssh_command,
                flags=ssh_args,
                hostname=self.remote_host,
                stdin=stdin)
        else:
            command = "{ssh_command} {flags} {hostname} bash -c '{command}'".format(
                ssh_command=self.ssh_command,
                flags=ssh_args,
                hostname=self.remote_host,
                command=command)

        self.log.debug("command: {}".format(command))

        proc = await asyncio.create_subprocess_shell(command, 
                                                    stdout=asyncio.subprocess.PIPE, 
                                                    stderr=asyncio.subprocess.PIPE,
                                                    env=ssh_env)
#        try:
            # changed the timeout to 300 temporarily for testing purposes (and because that's BatchSpawner's default)
#            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        stdout, stderr = await proc.communicate()
#        except asyncio.TimeoutError:
#            self.log.debug("execute timed out")
#            proc.kill()
#            self.log.debug("execute timed out done kill")
#            stdout, stderr = await proc.communicate()
#            self.log.debug("execute timed out done communicate")

        returncode = proc.returncode

        return (stdout, stderr, returncode)
    
    def user_env(self):

        env = super(SSHSpawner, self).get_env()
        env.update(dict(
            JPY_USER=self.user.name,
            JPY_COOKIE_NAME=self.user.server.cookie_name,
            JPY_BASE_URL=self.user.server.base_url,
            JPY_HUB_PREFIX=self.hub.server.base_url,
            JUPYTERHUB_PREFIX=self.hub.server.base_url,
            # PATH=self.path
            # NERSC local mod
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

    async def exec_notebook(self, command):
        env = self.user_env()
        bash_script_str = "#!/bin/bash\n"

        for item in env.items():
            # item is a (key, value) tuple
            # command = ('export %s=%s;' % item) + command
            bash_script_str += 'export %s=%s\n' % item

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

        stdout, stderr, retcode = await self.execute(command, stdin=run_script)
        self.log.debug("exec_notebook status={}".format(retcode))
        if stdout != b'':
            pid = int(stdout)
        else:
            return -1

        return pid

    async def remote_random_port(self):
        # command = self.remote_port_command
        # NERSC local mod
        command = self.remote_port_command

        # pass this into bash -c 'command'
        # command needs to be in "" quotes, with all the redirection outside
        # eg. bash -c '"ls -la" < /dev/null >> out.txt'
        command = '"%s" < /dev/null' % command

        stdout, stderr, retcode = await self.execute(command)

        if stdout != b'':
            port = int(stdout)
        else:
            self.log.error("could not get a remote port")
            return None
        self.log.debug("port={}".format(port))
        return port

    async def remote_signal(self, sig):
        """
        simple implementation of signal, which we can use
        when we are using setuid (we are root)
        """
        command = 'kill -s %s %d' % (sig, self.pid)

        # pass this into bash -c 'command'
        # command needs to be in "" quotes, with all the redirection outside
        # eg. bash -c '"ls -la" < /dev/null >> out.txt'
        command = '"%s" < /dev/null' % command

        stdout, stderr, retcode = await self.execute(command)
        self.log.debug("command: {} returned {} --- {} --- {}".format(command, stdout, stderr, retcode))
        return (retcode == 0)

    async def start(self):
        """Start the process"""
        self.log.debug("Entering start")

        port = await self.remote_random_port()
        if port is None or port == 0:
            return False
        cmd = []

        cmd.extend(self.cmd)
        cmd.extend(self.get_args())

        if self.hub_api_url != '':
            old = '--hub-api-url=%s' % self.hub.api_url
            new = '--hub-api-url=%s' % self.hub_api_url
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
        return (self.remote_host, port)

    async def poll(self):
        self.log.debug("Entering poll")

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
        self.log.debug("Entering stop")

        alive = await self.remote_signal(15)

        self.clear_state()

    def get_state(self):
        """get the current state"""
        self.log.debug("Entering get_state")

        state = super().get_state()
        if self.pid:
            state['pid'] = self.pid
        return state

    def load_state(self, state):
        """load state from the database"""
        self.log.debug("Entering load_state")

        super().load_state(state)
        if 'pid' in state:
            self.pid = state['pid']

    def clear_state(self):
        """clear any state (called after shutdown)"""
        self.log.debug("Entering clear_state")
        self.log.debug("Clearing User: {}, PID: {}".format(self.user.name, self.pid))
        super().clear_state()
        self.pid = 0
