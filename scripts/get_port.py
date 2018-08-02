
import argparse
import socket

def main():
    args = parse_arguments()
    if args.ip:
        print("{} {}".format(port(), ip()))
    else:
        print(port())

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", "-i",
            help="Include IP address in output",
            action="store_true")
    return parser.parse_args()

def port():
    s = socket.socket()
    s.bind(('', 0))
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
    main()
