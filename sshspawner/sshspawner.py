
import os
from subprocess import Popen, PIPE, TimeoutExpired


from traitlets import Bool, Unicode
from tornado import gen


from jupyterhub.spawner import Spawner


class SSHSpawner(Spawner):
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

    remote_port_command = Unicode("python -c \"import socket; sock = socket.socket(); sock.bind(('', 0)); print sock.getsockname()[1]; sock.close()\"",
                                  help="""The command to return an unused port
                                  on the remote node
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
                          Assumes use_gsi=False."""
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

    def execute(self, command):
        ssh_env = os.environ.copy()

        username = self.get_remote_user(self.user.name)

        if self.ssh_command is None:
            self.ssh_command = 'ssh'

        ssh_args = "-o StrictHostKeyChecking=no -l {username} -p {port}".format(
            username=username, port=self.remote_port)

        if self.use_gsi:
            ssh_env['X509_USER_CERT'] = self.get_gsi_cert()
            ssh_env['X509_USER_KEY'] = self.get_gsi_key()
        elif self.ssh_keyfile:
            ssh_args += " -i {keyfile}".format(keyfile=self.ssh_keyfile)

        command = "{ssh_command} {flags} {hostname} {command}".format(
            ssh_command=self.ssh_command,
            flags=ssh_args,
            hostname=self.remote_host,
            command=command)

        proc = Popen(command, stdout=PIPE, stderr=PIPE,
                     shell=True, env=ssh_env)

        try:
            stdout, stderr = proc.communicate(timeout=10)
        except TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()

        returncode = proc.returncode
        return (stdout, stderr, returncode)

    def user_env(self):

        env = super(SSHSpawner, self).get_env()
        env.update(dict(
            JPY_USER=self.user.name,
            JPY_COOKIE_NAME=self.user.server.cookie_name,
            JPY_BASE_URL=self.user.server.base_url,
            JPY_HUB_PREFIX=self.hub.server.base_url,
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

        return env

    def exec_notebook(self, command):
        env = self.user_env()
        for item in env.items():
            command = ('export %s="%s";' % item) + command

        # The command needs to be wrapped in quotes
        # We pass in stdin to avoid the hang
        # Grab the PID
        command = "'%s < /dev/null >> jupyter.log 2>&1 & pid=$!; echo $pid'" % command

        stdout, stderr, retcode = self.execute(command)
        print("exec_notebook status=%d" % retcode)
        if stdout != b'':
            pid = int(stdout)
        else:
            return -1

        return pid

    def remote_random_port(self):
        # command = self.remote_port_command
        # NERSC local mod
        command = self.remote_port_command

        command = command + "< /dev/null"
        stdout, stderr, retcode = self.execute(command)

        if stdout != b'':
            port = int(stdout)
        else:
            print("Bad port")
            return None
        print("port=%d" % (port))
        return port

    def remote_signal(self, sig):
        """
        simple implementation of signal, which we can use
        when we are using setuid (we are root)
        """
        command = 'kill -s %s %d' % (sig, self.pid)

        command = command + "< /dev/null"

        stdout, stderr, retcode = self.execute(command)
        return (retcode == 0)

    @gen.coroutine
    def start(self):
        """Start the process"""
        self.user.server.ip = self.remote_host
        port = self.remote_random_port()
        if port is not None and port > 0:
            self.user.server.port = port
        else:
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

        remote_cmd = ' '.join(cmd)

        # time.sleep(2)
        # import pdb; pdb.set_trace()

        self.pid = self.exec_notebook(remote_cmd)
        if self.pid < 0:
            return None

    @gen.coroutine
    def poll(self):
        if not self.pid:
                # no pid, not running
            self.clear_state()
            return 0

        # send signal 0 to check if PID exists
        alive = self.remote_signal(0)
        if not alive:
            self.clear_state()
            return 0
        else:
            return None

    @gen.coroutine
    def stop(self):

        alive = self.remote_signal(15)

        self.clear_state()

    def get_state(self):
        """get the current state"""
        state = super().get_state()
        if self.pid:
            state['pid'] = self.pid
        return state

    def load_state(self, state):
        """load state from the database"""
        super().load_state(state)
        if 'pid' in state:
            self.pid = state['pid']

    def clear_state(self):
        """clear any state (called after shutdown)"""
        super().clear_state()
        self.pid = 0
