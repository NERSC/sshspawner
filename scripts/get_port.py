import socket


def port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def ip(address=("8.8.8.8", 80)):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(address)
    ip = s.getsockname()[0]
    s.close()
    return ip


if __name__ == "__main__":
    print(f"{ip()} {port()}")
