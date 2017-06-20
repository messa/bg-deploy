from textwrap import dedent

from helpers import read_file, write_file


def test_simple_workflow(tmp_dir):
    plan_file = write_file(tmp_dir / 'plan.yaml', dedent('''
        blue:
            prepare:
                - run: echo blue-prepare >> TMP/log.txt
            check:
                - run: echo blue-check >> TMP/log.txt
            activate:
                - run: echo blue-activate >> TMP/log.txt
            verify:
                - run: echo blue-verify >> TMP/log.txt
            done:
                - run: echo blue-done >> TMP/log.txt
        green:
            prepare:
                - run: echo green-prepare >> TMP/log.txt
            check:
                - run: echo green-check >> TMP/log.txt
            activate:
                - run: echo green-activate >> TMP/log.txt
            verify:
                - run: echo green-verify >> TMP/log.txt
            done:
                - run: echo green-done >> TMP/log.txt
        state_file: TMP/state.yaml
    ''').replace('TMP', str(tmp_dir)))
    log_file = tmp_dir / 'log.txt'
    status_file = tmp_dir / 'state.yaml'

    # first run - should deploy blue

    run_deploy(plan_file)
    assert read_file(log_file) == dedent('''\
        blue-prepare
        blue-check
        blue-activate
        blue-verify
        blue-done
    ''')
    assert read_file(status_file) == dedent('''\
        blue_status: active
    ''')

    # second run - should deploy green

    log_file.unlink()
    run_deploy(plan_file)
    assert read_file(log_file) == dedent('''\
        green-prepare
        green-check
        green-activate
        green-verify
        green-done
    ''')
    assert read_file(status_file) == dedent('''\
        blue_status: backup
        green_status: active
    ''')

    # third run - should deploy blue

    log_file.unlink()
    run_deploy(plan_file)
    assert read_file(log_file) == dedent('''\
        blue-prepare
        blue-check
        blue-activate
        blue-verify
        blue-done
    ''')
    assert read_file(status_file) == dedent('''\
        blue_status: active
        green_status: backup
    ''')


def test_fallback_from_verify(tmp_dir):
    plan_file = write_file(tmp_dir / 'plan.yaml', dedent('''
        blue:
            prepare:
                - run: echo blue-prepare >> TMP/log.txt
            check:
                - run: echo blue-check >> TMP/log.txt
            activate:
                - run: echo blue-activate >> TMP/log.txt
            verify:
                - run: echo blue-verify >> TMP/log.txt
            done:
                - run: echo blue-done >> TMP/log.txt
        green:
            prepare:
                - run: echo green-prepare >> TMP/log.txt
            check:
                - run: echo green-check >> TMP/log.txt
            activate:
                - run: echo green-activate >> TMP/log.txt
            verify:
                - run: echo green-verify failed >> TMP/log.txt && false
            done:
                - run: echo green-done >> TMP/log.txt
        state_file: TMP/state.yaml
    ''').replace('TMP', str(tmp_dir)))

    # first run - should deploy blue

    run_deploy(plan_file)
    assert read_file(tmp_dir / 'state.yaml') == dedent('''\
        blue_status: active
    ''')

    # second run - should try to deploy green, ten fallback to blue

    run_deploy(plan_file)
    assert read_file(tmp_dir / 'state.yaml') == dedent('''\
        blue_status: active
        green_status: activate-failed
    ''')

    assert read_file(tmp_dir / 'log.txt') == dedent('''\
        blue-prepare
        blue-check
        blue-activate
        blue-verify
        blue-done
        green-prepare
        green-check
        green-activate
        green-verify failed
        blue-activate
        blue-verify
        blue-done
    ''')


# The prototype
# -------------


import logging
import subprocess
from time import monotonic as monotime
import yaml


logger = logging.getLogger(__name__)


GREEN = 'green'
BLUE = 'blue'


def run_deploy(plan_path):
    with plan_path.open() as f:
        plan = yaml.safe_load(f)
    state_path = plan_path.parent / plan['state_file']
    with StateFile(state_path) as state_file:
        branch = GREEN if state_file.get('blue_status') == 'active' else BLUE
        other_branch = GREEN if branch == BLUE else BLUE
        state_file[branch + '_status'] = 'preparing'
        state_file.flush()
        try:
            run_steps(plan[branch]['prepare'])
            run_steps(plan[branch]['check'])
        except BaseException as e:
            state_file[branch + '_status'] = 'prepare-failed'
            state_file.flush()
            return
        try:
            run_steps(plan[branch]['activate'])
            run_steps(plan[branch]['verify'])
        except BaseException as e:
            state_file[branch + '_status'] = 'activate-failed'
            state_file.flush()
            if state_file.get(other_branch + '_status') in ['active', 'backup']:
                logger.info('Rollback to %s', other_branch)
                run_steps(plan[other_branch]['activate'])
                run_steps(plan[other_branch]['verify'])
                run_steps(plan[other_branch]['done'])
            else:
                logger.info('Activate of %s failed, but %s not in state for rollback', branch, other_branch)
            return
        state_file[branch + '_status'] = 'active'
        if state_file.get(other_branch + '_status') == 'active':
            state_file[other_branch + '_status'] = 'backup'
        state_file.flush()
        run_steps(plan[branch]['done'])


class StateFile:

    def __init__(self, path):
        self._path = path
        self._content = self._read_file(self._path)
        self._data = yaml.safe_load(self._content or '') or {}

    def _read_file(self, path):
        try:
            with path.open() as f:
                return f.read()
        except FileNotFoundError:
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def get(self, key):
        return self._data.get(key)

    def __setitem__(self, key, value):
        logger.debug('State %s: %r -> %r', key, self._data.get(key), value)
        self._data[key] = value

    def flush(self):
        content = self._read_file(self._path)
        if content != self._content:
            raise Exception('File {} has been modified'.format(self._path))
        new_content = yaml.safe_dump(self._data, default_flow_style=False, indent=4)
        temp_path = self._path.with_name(self._path.name + '.temp')
        if temp_path.is_file():
            temp_path.unlink()
        with temp_path.open('x') as f:
            f.write(new_content)
        temp_path.rename(self._path)
        self._content = new_content
        logger.info('Saved state file %s', self._path)


def run_steps(steps):
    if not isinstance(steps, list):
        raise Exception('expected list, got {!r}'.format(steps))
    for step in steps:
        run_step(step)


def run_step(step):
    logger.debug('run_step: %r', step)
    if isinstance(step, dict):
        if step.get('run'):
            cmd = step['run']
            if isinstance(cmd, str):
                run_step_command_str(cmd)
                return
            if isinstance(cmd, list):
                run_step_command_list(cmd)
                return
    raise Exception('Unknown step: {!r}'.format(step))


def run_step_command_str(cmd):
    logger.debug('run_step_command_str: %r', cmd)
    t0 = monotime()
    p = subprocess.Popen(cmd, shell=True)
    p.wait()
    td = monotime() - t0
    logger.debug('Command finished in %.3f s with return code %r', td, p.returncode)
    if p.returncode != 0:
        raise Exception(
            'Command {!r} failed (return code {}, pid {})'.format(
                cmd, p.returncode, p.pid))
