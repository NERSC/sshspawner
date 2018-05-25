import subprocess, os

def execute_dummy(command):
    
    ssh_env = os.environ.copy()
    
    ssh_env['X509_USER_CERT'] = 'cert'
    ssh_env['X509_USER_KEY'] = 'key'
    
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     shell=True, env=ssh_env)
    
    try:
        stdout, stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutError:
        proc.kill()
        stdout, stderr = proc.communicate()
    
    returncode = proc.returncode
    
    return (stdout, stderr, returncode) 

# Some smoke tests. I did more than are included here, some of which:
    # (a) involve changing the return value of the function to include proc,
    # (b) involve changing the timeout to be so miniscule that the timeout exception is invoked.

print(os.environ)

stdout, stderr, returncode = execute_dummy('/bin/sh echo "test"')

print(stdout)
print(stderr)
print(returncode)

# Should be the same as before
print(os.environ)
