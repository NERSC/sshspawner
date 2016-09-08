# SSH Spawner for Jupyterhub

Allows jupyter notebooks to be launched on a remote node over SSH.
Support for
- SSH key based auth
- GSISSH (See [GSI Authenticator](https://github.com/NERSC/GSIAuthenticator)

## Installation

Requires Python 3

```
python setup.py install 
```

## Configuration

See [jupyterhub_config.py](jupyterhub_config.py) for a sample configuration
