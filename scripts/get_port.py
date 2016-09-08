#!/usr/bin/env python

# Gets a random unused port

import socket
sock = socket.socket()
sock.bind(('', 0))
print sock.getsockname()[1]
sock.close()
