# Shamelessly copied, at some places modified, from `tests.py` from Mike Milligan's batchspawner.

from unittest import mock
from .. import SSHSpawner
from traitlets import Unicode
import time
import pytest
from jupyterhub import orm, version_info

try:
    from jupyterhub.objects import Hub
    from jupyterhub.user import User
except:
    pass

testhost = "userhost123"
testjob = "12345"

def new_spawner(db, **kwargs):
    """Creates a generic instance of SSHSpawner."""
    # Attributes SSHSpawner inherits from Spawner:
    kwargs.setdefault('cmd', ['singleuser_command'])
    user = db.query(orm.User).first()
    
    if version_info < (0.8):
        hub = db.query(orm.Hub).first()
    else:
        hub = Hub()
        user = User(user, {})
        
    kwargs.setdefault('hub', hub)
    kwargs.setdefault('user', user)
    # TIMEOUT attributes not part of SSHSpawner or base Spawner class, just BatchSpawner
    kwargs.setdefault('poll_interval', 1)

    if version_info < (0.8):
        return SSHSpawner(db=db, **kwargs)
    else:
        print("JupyterHub version >=0.8 detected, using new spawner creation")
        return user._new_spawner('', spawner_class=SSHSpawner, **kwargs)

def test_stress_submit(db, io_loop):
    """Checks to see whether the expected start, stop, poll behavior still continues to work even after 200 trials."""
    for i in range(200):
        time.sleep(0.01)
        test_spawner_start_stop_poll(db, io_loop)

# check_ip function not applicable, because SSHSpawner doesn't have a current_ip attribute (in contrast to batchspawner which does)

def test_spawner_start_stop_poll(db, io_loop):
    """Basic checks of necessary conditions for the `start`, `stop`, and `poll` methods of SSHSpawner to be behaving as expected."""
    
    spawner = new_spawner(db=db)

    # The following should not work because the event loop should not have been started yet. Therefore we expect status to equal 1.
    status = io_loop.run_sync(spawner.poll, timeout=5)
    assert status == 1
    
    # SSH Spawner has no job_id attribute
    
    # Before starting, the result of get_state should be an empty dictionary.
    assert spawner.get_state() == {}

    io_loop.run_sync(spawner.start, timeout=5)

    # http://www.tornadoweb.org/en/stable/ioloop.html#tornado.ioloop.IOLoop.run_sync
    # Seems to run spawner's poll method.
    # If the timeout expires, a `TimeoutError` is raised, status does not equal none, and the test fails.
    # Otherwise SSHSpawner's poll method returns `None`, and the test passes.
    status = io_loop.run_sync(spawner.poll, timeout=5)
    assert status is None
    
    # SSHSpawner has no batch_query_cmd attribute

    # Attempts to stop the event loop within the timeout period
    io_loop.run_sync(spawner.stop, timeout=5)
    # If the above was successful, the event loop was stopped (i.e. it didn't timeout)
    # Therefore what follows should raise an error, and thus `status` should equal 1.
    status = io_loop.run_sync(spawner.poll, timeout=5)
    assert status == 1
    # Because the `stop` method of SSHSpawner calls the `clear_state` method, the result of `get_state` after a successful call to `stop` should be an empty dictionary.
    # Therefore the following should pass if `stop` was successful.
    assert spawner.get_state() == {}


    
def test_spawner_state_reload(db, io_loop):
    """Basic checks of necessary conditions for the `get_state`, `clear_state`, and `load_state` methods to be behaving as expected. """
    spawner = new_spawner(db=db)
    # By default, before initialization, the value of `spawner.pid` will be `None`.
    # So when SSHSpawner's `get_state` method checks `if self.pid`, the result will be `False`.
    # Thus `spawner.get_state()` will return the result of the parent `Spawner` class's `get_false` method, which is an empty dictionary, and the below assert statement will pass.
    assert spawner.get_state() == {}

    io_loop.run_sync(spawner.start, timeout=30)

    # SSHSpawner doesn't have a jobid attribute, so these lines had to be removed.
    
    state = spawner.get_state()
    # After starting, the value of spawner.pid should no longer be none (see line 280 of SSHSpawner)
    # self.pid = self.exec_notebook(remote_cmd)
    # Thus the logical `if self.pid` will now be true, and the result of `spawner.get_state` should now be a non-empty dictionary, as the following assert statement checks:
    assert state == dict('pid':self.exec_notebook(remote_cmd))

    # I am not sure why this line is supposed to be useful.
    # Presumably what one wants to do is to check that the `clear_state` method works? Then seemingly that would only be useful if the state wasn't clear, which wouldn't be the case if we initialized another brand-new spawner. Nevertheless I trust Mike Milligan's knowledge judgment better than mine, so I will leave the line in.
    spawner = new_spawner(db=db)
    # Clears the state, now we want to see if it actually works:
    spawner.clear_state()
    # After clear state, `spawner.pid` should equal `0`, therefore `if self.pid` should be `False`, and thus `get_state` should return the same thing `Spawner`'s parent method returns, which is an empty dictionary.
    assert spawner.get_state() == {}

    # If none of the above asserts failed, then `state == {'pid':spawner.exec_notebook(remote_cmd)}`.
    # Thus `load_state` should make `self.pid` once again not null. This is what the assert statement checks.
    spawner.load_state(state)
    assert spawner.pid == spawner.exec_notebook(remote_cmd)

    
# test_submit_failure not relevant to SSHSpawner since it lacks batch_submit_cmd, job_id, and job_status attributes.

# test_pending_fails also not relevant to SSHSpawner since it lacks a batch_query_cmd attribute, as well as lacking job_id and job_status attributes (as noted already before).
