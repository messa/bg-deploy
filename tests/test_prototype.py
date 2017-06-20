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
    run_deploy(plan_file)
    assert read_file(tmp_dir / 'log.txt') == dedent('''\
        blue-prepare
        blue-check
        blue-activate
        blue-verify
        blue-done
    ''')


# The prototype
# -------------


import logging
import subprocess
import yaml


logger = logging.getLogger(__name__)


def run_deploy(plan_file):
    with plan_file.open() as f:
        plan = yaml.safe_load(f)
    branch = 'blue'
    run_steps(plan[branch]['prepare'])
    run_steps(plan[branch]['check'])
    run_steps(plan[branch]['activate'])
    run_steps(plan[branch]['verify'])
    run_steps(plan[branch]['done'])


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
    p = subprocess.Popen(cmd, shell=True)
    p.wait()
    if p.returncode != 0:
        raise Exception(
            'Command {!r} failed (return code {}, pid {})'.format(
                cmd, p.returncode, p.pid))
