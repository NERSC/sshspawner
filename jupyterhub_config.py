
c.JupyterHub.spawner_class = 'sshspawner.sshspawner.SSHSpawner'

c.SSHSpawner.remote_host = 'cori19-224.nersc.gov'
c.SSHSpawner.remote_port = '2222'
c.SSHSpawner.ssh_command = 'gsissh'

c.SSHSpawner.use_gsi = True
c.SSHSpawner.path = '/global/common/cori/software/python/3.5-anaconda/bin:/global/common/cori/das/jupyterhub/:/usr/common/usg/bin:/usr/bin:/bin:/usr/bin/X11:/usr/games:/usr/lib/mit/bin:/usr/lib/mit/sbin'
c.SSHSpawner.remote_port_command = '/global/common/cori/das/jupyterhub/get_port.py'

