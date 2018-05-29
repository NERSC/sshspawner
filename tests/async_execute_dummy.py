import asyncio, os

async def async_execute_dummy(command):

    # Have to change the environment manually before running the process.
    # asyncio.subprocess.Process does not have an `env` attribute, the way subprocess.Popen does.
    backup_env = os.environ.copy()
    # Want a copy by value, not reference
    ssh_env = backup_env.copy()
    
    ssh_env['X509_USER_CERT'] = 'cert'
    ssh_env['X509_USER_KEY'] = 'key'
    
    os.environ.update(ssh_env)
    
    try:
        proc = await asyncio.create_subprocess_shell(command, 
                                                    stdout=asyncio.subprocess.PIPE, 
                                                    stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
        returncode = proc.returncode
    
    # Even if the above fails, we still want our environment variables reset and cleared of sensitive information.
    finally:
        os.environ.clear()
        os.environ.update(backup_env)
    
    return (stdout, stderr, returncode)

# Some smoke tests. I did more than are included here, some of which:
    # (a) involve changing the return value of the function to include proc,
    # (b) involve changing the timeout to be so miniscule that the timeout exception is invoked.

print(os.environ)

loop = asyncio.get_event_loop()

try:
    stdout, stderr, returncode = loop.run_until_complete(async_execute_dummy('/bin/sh echo "test"'))
    
finally:
    loop.close()

print(stdout)
print(stderr)
print(returncode)

# Should be the same as before
print(os.environ)
