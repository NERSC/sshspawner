# SSH Spawner for Jupyterhub

Allows jupyter notebooks to be launched on a remote node over SSH.
Support for
- SSH key based auth
- GSISSH (See [GSI Authenticator](https://github.com/NERSC/GSIAuthenticator))

## Installation

Requires Python 3

```
python setup.py install 
```

Install [scripts/get_port.py](scripts/get_port.py) on remote host and set correct path for `c.SSHSpawner.remote_port_command` in [jupyterhub_config.py](jupyterhub_config.py) 

## Configuration

See [jupyterhub_config.py](jupyterhub_config.py) for a sample configuration. Adjust values for your installation.
