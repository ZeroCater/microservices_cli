import logging
import os
import subprocess
import sys
from multiprocessing import Process, Queue

import git
import yaml

from config import Config

log = logging.getLogger(__name__)

# Config
BASE_DIR = Config.get('BASE_DIR')
DOCKER_COMPOSE_FILE = Config.get(
    'DOCKER_COMPOSE_FILE', os.path.join(BASE_DIR, 'docker-compose-tmp.yml'))

SERVICE_MAPPING = Config.get('SERVICE_MAPPING', {})
SERVICE_CONSTELLATIONS = Config.get('SERVICE_CONSTELLATIONS', {})
SINGLETON_SERVICES = Config.get('SINGLETON_SERVICES', {})


def run_docker_compose_command(cmd):
    """
    Run a Docker Compose command

    e.g.:
    run_docker_compose_command('up worker')
    run_docker_compose_command('up')
    """
    # Try to avoid docker-compose up read timeout error when starting a lot of containers
    os.environ['COMPOSE_HTTP_TIMEOUT'] = '300'

    if type(cmd) == list:  # If passed as an array, use arguments grouped as passed
        subprocess.call(['docker-compose', '-f', DOCKER_COMPOSE_FILE] + cmd)
    else:
        subprocess.call(['docker-compose', '-f', DOCKER_COMPOSE_FILE] + cmd.split(' '))


def remove_docker_compose_file():
    """Removes the temporary docker-compose file"""
    os.remove(DOCKER_COMPOSE_FILE)


def check_for_docker_compose_file():
    """
    Check to see if a microservices CLI docker-compose file is present. The absence of one
    suggests that the CLI is not currently running.
    """
    return os.path.isfile(DOCKER_COMPOSE_FILE)


def docker_compose_attach(service):
    """Attempt to attach to a running docker service."""
    try:
        run_docker_compose_command('exec {} bash'.format(service))
    except subprocess.CalledProcessError:
        log.error('Could not attach to [{}] service, is it running?'.format(service))
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


def start_docker_compose_services():
    """
    Runs docker-compose up for services defined in the temporary docker-compose file,
    remove the file when halted with Ctrl+C.
    """
    try:
        run_docker_compose_command('up')
    except KeyboardInterrupt:
        remove_docker_compose_file()


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
            log.error('Could not checkout master for service [{}], try checking in or stashing changes'.format(service))
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
        with open(os.path.join(BASE_DIR, service, 'docker-compose.yml'), 'r') as infile:
            individual_services = yaml.load(infile)['services'].keys()

        # Check for env override file
        #   Waiting on an optional env file to obviate the need for this: https://github.com/docker/compose/pull/3955
        env_override = os.path.isfile(os.path.join(BASE_DIR, service, '.env.local'))
        if env_override:
            with open(os.path.join(BASE_DIR, service, '.env.local')) as f:
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
                    'file': os.path.join(BASE_DIR, service, 'docker-compose.yml'),
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
    project_services = filter(lambda x: x not in SINGLETON_SERVICES, project_services)

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
    Find all running Docker containers and kill them
    """
    running_container_ids = subprocess.check_output(['docker', 'ps', '-q'])
    running_container_ids = running_container_ids.strip().split()  # Remove trailing \n and convert to list

    if running_container_ids:
        subprocess.call(['docker', 'kill'] + running_container_ids)
