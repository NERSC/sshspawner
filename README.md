
# sshspawner

The *sshspawner* enables JupyterHub to spawn single-user notebook servers on remote hosts over SSH.

## Features

* Supports SSH key-based authentication
* Pool of remote hosts for spawning notebook servers
* Extensible custom load-balacing for remote host pool
* Remote-side scripting to return IP and port

## Requirements

* Python 3
* JupyterHub

## Installation

```
python3 setup.py install
```

Install [scripts/get_port.py](scripts/get_port.py) on remote host and set correct path for `c.SSHSpawner.remote_port_command` in [jupyterhub_config.py](jupyterhub_config.py)

## Configuration

See [jupyterhub_config.py](jupyterhub_config.py) for a sample configuration.
Adjust values for your installation.

## Getting Help

We encourage you to post issues on the GitHub issue tracker if you have questions.

## License

All code is licensed under the terms of the revised BSD license.

## Resources

### JupyterHub and sshspawner

- [Reporting Issues](https://github.com/NERSC/sshspawner/issues)
- [Documentation for JupyterHub](https://jupyterhub.readthedocs.io)

### Jupyter

- [Documentation for Project Jupyter](https://jupyter.readthedocs.io/en/latest/index.html) | [PDF](https://media.readthedocs.org/pdf/jupyter/latest/jupyter.pdf)
- [Project Jupyter website](https://jupyter.org)

