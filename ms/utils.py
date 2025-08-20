import logging
import os
import subprocess
import sys
import time
from multiprocessing import Process

import git
import yaml

from ms.config import Config

log = logging.getLogger(__name__)

# Config
BASE_DIR = os.path.abspath(os.path.expanduser(Config.get('BASE_DIR')))
DOCKER_COMPOSE_FILE = Config.get(
    'DOCKER_COMPOSE_FILE', os.path.join(BASE_DIR, 'docker-compose-tmp.yml'))

SERVICE_MAPPING = Config.get('SERVICE_MAPPING', {})
SERVICE_CONSTELLATIONS = Config.get('SERVICE_CONSTELLATIONS', {})
SINGLETON_SERVICES = Config.get('SINGLETON_SERVICES', {})
KEEP_DOCKER_COMPOSE_FILE_ON_SHUTDOWN = Config.get('KEEP_DOCKER_COMPOSE_FILE_ON_SHUTDOWN', False)


def run_docker_compose_command(cmd, verbose=False, log_level=None):
    """
    Run a Docker Compose command

    e.g.:
    run_docker_compose_command('up worker')
    run_docker_compose_command('up')
    """
    # Try to avoid docker-compose up read timeout error when starting a lot of containers
    os.environ['COMPOSE_HTTP_TIMEOUT'] = '300'

    args = ['docker-compose']

    if verbose:
        args += ['--verbose']

    if log_level:
        args += ['--log-level', log_level]

    args += ['-f', DOCKER_COMPOSE_FILE]

    if type(cmd) == list:  # If passed as an array, use arguments grouped as passed
        args += cmd
    else:
        args += cmd.split(' ')

    subprocess.call(args)


def run_docker_command(cmd):
    if type(cmd) == list:  # If passed as an array, use arguments grouped as passed
        subprocess.call(['docker'] + cmd)
    else:
        subprocess.call(['docker'] + cmd.split(' '))


def remove_docker_compose_file():
    """Removes the temporary docker-compose file"""
    os.remove(DOCKER_COMPOSE_FILE)


def check_for_docker_compose_file():
    """
    Check to see if a microservices CLI docker-compose file is present. The absence of one
    suggests that the CLI is not currently running.
    """
    return os.path.isfile(DOCKER_COMPOSE_FILE)


def should_remove_docker_compose_file():
    keep_compose_file = not KEEP_DOCKER_COMPOSE_FILE_ON_SHUTDOWN and check_for_docker_compose_file()
    log.debug(f'should keep docker-compose-tmp.yml: {keep_compose_file}')
    return keep_compose_file


def docker_compose_attach(service):
    """Attempt to attach to a running docker service."""
    try:
        run_docker_compose_command('exec {} bash'.format(service))
    except subprocess.CalledProcessError:
        log.error('Could not attach to [{}] service, is it running?'.format(service))
        sys.exit(1)


def docker_compose_restart(service):
    """Attempt to restart a running docker service."""
    try:
        run_docker_compose_command('restart {}'.format(service))
    except subprocess.CalledProcessError:
        log.error('Could not restart [{}] service, is it running?'.format(service))
        sys.exit(1)


def get_list_of_services(services):
    """
    Takes a list of services/constellation from the command line and maps them to the preferred names.
    Also validates that these are directories and they have a docker-compose file in them.
    """
    if not services:  # If no services passed, get all folders with a docker-compose file
        services = find_docker_compose_services()

    # See if service passed in is a constellation, if so expand
    if len(services) == 1 and services[0] in SERVICE_CONSTELLATIONS:
        services = SERVICE_CONSTELLATIONS[services[0]]

    # Check that each service is in the directory and has a docker-compose file
    check_services(services)

    return services


def start_docker_compose_services(args, mapped_services):
    """
    Runs docker-compose up for services defined in the temporary docker-compose file,
    remove the file when halted with Ctrl+C.
    """
    try:
        start_time = time.time()
        mapped_services = list(mapped_services)
        if args.ignore:
            for service_to_ignore in args.ignore:
                mapped_services.remove(service_to_ignore)

        log.debug(f'mapped serviced: {mapped_services}')
        log.debug(f'ignored: {args.ignore}')
        run_docker_compose_command(['up'] + mapped_services, log_level=args.l, verbose=args.v)

        log.debug(f'Started in {time.time() - start_time}')
    except KeyboardInterrupt:
        if should_remove_docker_compose_file():
            remove_docker_compose_file()


def stop_down_docker_compose_services(args, mapped_services):
    """
    Runs docker-compose up for services defined in the temporary docker-compose file,
    remove the file when halted with Ctrl+C.
    """
    if args.ignore:
        for service_to_ignore in args.ignore:
            mapped_services.remove(service_to_ignore)
    log.debug(f'mapped serviced: {mapped_services}')

    run_docker_compose_command(['down'] + mapped_services + ['--remove-orphans'], log_level=args.l, verbose=args.v)

    if should_remove_docker_compose_file():
        remove_docker_compose_file()


def top_docker_compose_services(services):
    """
    Runs docker-compose top for services defined in the temporary docker-compose file,
    or specified services.
    """
    run_docker_compose_command(['top'] + services)


def dockerhub_pull(services):
    """
    Pull DockerHub images for the passed services in parallel.
    """
    docker_services = get_list_of_services(services)
    service_list = construct_docker_compose_file(docker_services)

    procs = []
    for service in service_list:
        process = Process(target=run_docker_compose_command, args=(['pull', service],))
        process.start()
        procs.append(process)

    for p in procs:
        p.join()

    remove_docker_compose_file()


def git_clone_repo(remote_url, target_dir):
    """
    Clones a remote repository into a local directory.
    """
    log.info('Cloning [{}] into [{}]'.format(remote_url, target_dir))
    git.Repo.clone_from(remote_url, target_dir)


def git_pull_master(service, keep_branch=False):
    """
    Takes a service, switches to master, and pulls code. If the keep_branch argument
    is passed, it will switch back to the original branch if it was on anything other
    than master.
    """
    log.info('[{}] pulling master'.format(service))
    repo = git.Repo(os.path.join(BASE_DIR, service))

    if repo.active_branch.name != 'master':
        current_branch = repo.active_branch

        try:
            repo.git.checkout('master')
            repo.remotes.origin.pull()

            if keep_branch:
                current_branch.checkout()
        except git.exc.GitCommandError:
            log.error(
                'Could not checkout master for service [{}], try checking in or stashing changes'.format(service))
            sys.exit(1)
    else:
        repo.remotes.origin.pull()


def get_full_service_name(service, s):
    """
    Returns a properly formed service name based on the service and process names passed in.
    Will look up services in the service mapping dictionary to see if there's a preferred name.
    """
    service_alias = SERVICE_MAPPING[service] if service in SERVICE_MAPPING else service

    # Don't suffix service type if it's a web worker or the same as the service (e.g. gateway, haproxy)
    if s == 'web' or service_alias == s:
        return service_alias
    return '{}-{}'.format(service_alias, s)


def construct_docker_compose_file(services):
    """
    Construct a temporary docker-compose file from the passed services.
    """
    data = {
        'version': '2',
        'services': {},
    }

    for service in services:
        docker_compose_path = os.path.join(BASE_DIR, service, 'docker-compose.yml')
        if not os.path.isfile(docker_compose_path):
            log.error('Could not find docker-compose file for service {} in the path {}'.format(service, docker_compose_path))
            sys.exit(1)

        with open(docker_compose_path, 'r') as infile:
            individual_services = yaml.load(infile, Loader=yaml.SafeLoader)['services'].keys()

        # Check for env override file
        #   Waiting on an optional env file to obviate the need for this: https://github.com/docker/compose/pull/3955
        local_env_path = os.path.join(BASE_DIR, service, '.env.local')
        env_override = os.path.isfile(local_env_path)
        if env_override:
            with open(local_env_path) as f:
                env_override_block = [line.strip() for line in f if line != '\n' and not line.startswith('#')]

        for s in individual_services:
            if s in SINGLETON_SERVICES:
                if s not in data['services']:  # Make sure we only add it once
                    service_name = s
                else:
                    continue
            else:
                service_name = get_full_service_name(service, s)

            # Construct the service entry in the docker-compose outfile
            data['services'][service_name] = {
                'extends': {
                    'file': docker_compose_path,
                    'service': s
                }
            }

            # If there's an environment override, set environment block here
            if env_override and s not in SINGLETON_SERVICES:
                data['services'][service_name]['environment'] = env_override_block

    # Write docker-compose file
    with open(DOCKER_COMPOSE_FILE, 'w') as outfile:
        outfile.write(yaml.safe_dump(data))

    # Return list of services
    return data['services'].keys()


def print_docker_compose_path():
    log.info(f'DOCKER_COMPOSE_FILE: {DOCKER_COMPOSE_FILE}')


def check_services(services):
    """
    Takes an array of services and checks to see if the directories exist in the base
    directory and that there are docker-compose files in each of them.
    """
    dir_list = os.listdir(BASE_DIR)

    for service in services:
        # Check to see if they are in the root directory
        if service not in dir_list or not os.path.isdir(os.path.join(BASE_DIR, service)):
            log.error('Could not find service [{}] folder in the root directory'.format(service))
            sys.exit(1)

        # Check to see if there's a docker-compose file in the directory
        directory = os.path.join(BASE_DIR, service)
        if 'docker-compose.yml' not in os.listdir(directory):
            log.error('Could not find docker-compose.yml file in [{}] service directory'.format(service))
            sys.exit(1)


def find_docker_compose_services():
    """Traverses a base directory and determines which of the directories contain a `docker-compose.yml` file."""
    dir_list = os.listdir(BASE_DIR)
    directories = [d for d in dir_list if os.path.isdir(os.path.join(BASE_DIR, d))]

    return [d for d in directories if 'docker-compose.yml' in os.listdir(os.path.join(BASE_DIR, d))]


def run_one_off_command(directory, command, service=None):
    """
    Run a one-off command through docker-compose

    TODO: Add support for running a command even when docker-compose already running
    """
    if check_for_docker_compose_file():
        log.info('docker-compose already running, consider attaching to a running container')
        sys.exit(0)

    project_services = construct_docker_compose_file([directory])
    project_services = list(filter(lambda x: x not in SINGLETON_SERVICES, project_services))

    if service:  # Always use passed in service if present
        service_name = get_full_service_name(directory, service)
    else:
        if len(project_services) == 1:  # If only one service in directory (like worker), use that
            service_name = project_services[0]
        else:
            service = 'web' if not service else service  # If no --service, default to web
            service_name = get_full_service_name(directory, service)

    run_docker_compose_command(['run', '--rm', service_name] + command)
    remove_docker_compose_file()


def kill_all_docker_containers():
    """
    Find all running Docker containers and kill them.
    """
    running_container_ids = get_running_container_ids()

    if running_container_ids:
        start_time = time.time()
        subprocess.call(['docker', '-D', '-l', 'debug', 'kill'] + running_container_ids)

        log.debug(f'Killed in {time.time() - start_time}')


def stop_all_docker_containers():
    """
    Find all running Docker containers and kill them.
    """
    running_container_ids = get_running_container_ids()

    if running_container_ids:
        subprocess.call(['docker', 'stop'] + running_container_ids)


def get_running_container_ids():
    running_container_ids = subprocess.check_output(['docker', 'ps', '-q'])
    running_container_ids = running_container_ids.strip().split()  # Remove trailing \n and convert to list

    return running_container_ids


def show_logs_for_running_containers(services, tail, tail_count):
    """Run the docker-compose logs command for one or more running containers"""
    if not check_for_docker_compose_file():
        log.info('No running containers found')
        sys.exit(1)

    try:
        args = ['logs']

        if tail:
            args.append('-f')

        if tail_count:
            args.append(f'--tail={tail_count}')

        final_result = args + services

        run_docker_compose_command(final_result)
    except KeyboardInterrupt:
        sys.exit(0)


def list_all_docker_containers(ps_filter):
    """
    List all docker containers by their name, status, command and state.

    Specified filter is passed along to 'docker ps'
    """
    try:
        args = ['ps', '--format', 'table {{.Names}}\t{{.Status}}\t{{.Command}}\t{{.State}}\t{{.ID}}']

        if ps_filter:
            args.extend(['--filter', f'name={ps_filter}'])

        run_docker_command(args)
    except KeyboardInterrupt:
        sys.exit(0)


def print_config():
    subprocess.call(['cat', f'{DOCKER_COMPOSE_FILE}'])
