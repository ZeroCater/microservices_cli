import logging
import sys
from ms import utils

log = logging.getLogger(__name__)


def init(args):
    """
    Create the configuration file.
    """
    services = utils.get_list_of_services(args.services)
    log.debug(f'services: {services}')
    mapped_services = utils.construct_docker_compose_file(services)
    log.debug(f'mapped services: {mapped_services}')

    utils.print_docker_compose_path()


def start(args):
    """
    Start the service(s) passed in the command line. If no services are passed,
    everything in the directory is started. Creates a temporary docker-compose
    file and removes it on Ctrl+c.
    """
    services = utils.get_list_of_services(args.services)
    log.debug(f'services: {services}')
    mapped_services = utils.construct_docker_compose_file(services)
    utils.start_docker_compose_services(args, mapped_services)


def down(args):
    services = utils.get_list_of_services(args.services)
    log.debug(f'services: {services}')
    mapped_services = utils.construct_docker_compose_file(services)
    utils.stop_down_docker_compose_services(args, mapped_services)

    if utils.should_remove_docker_compose_file():
        utils.remove_docker_compose_file()


def top(args):
    utils.top_docker_compose_services(args.services)


def pull(args):
    """Pulls specified (or all) images built on DockerHub"""
    utils.dockerhub_pull(args.services)


def gitpull(args):
    """Pulls git repositories of specified, or all, projects"""
    services = utils.get_list_of_services(args.services)
    for service in services:
        utils.git_pull_master(service, args.keep)


def attach(args):
    """Drops into a bash shell on a running docker service"""
    if not utils.check_for_docker_compose_file():
        log.error('No microservices docker-compose file found!')
        sys.exit(1)
    utils.docker_compose_attach(args.service)


def restart(args):
    """Restarts a running docker service"""
    if not utils.check_for_docker_compose_file():
        pass
    utils.docker_compose_restart(args.service)


def run(args):
    """Run a command inside a one-off Docker container"""
    utils.run_one_off_command(args.directory, args.command, args.service)


def logs(args):
    """Display logs for one or more running containers"""
    utils.show_logs_for_running_containers(args.services, args.f, args.t)


def list_containers(args):
    """Lists the name of all containers and status"""
    utils.list_all_docker_containers(args.filter)


def kill(args):
    """
    Stop any running Docker containers and remove the temporary docker-compose
    file if it exists
    """
    if args.service:
        utils.run_docker_compose_command(['kill', args.service])
    else:
        utils.kill_all_docker_containers()

    if args.keep:
        log.info('Keeping docker-compose-tmp.yml')
    elif utils.should_remove_docker_compose_file():
        utils.remove_docker_compose_file()


def stop(args):
    """
    Stop any running Docker containers and remove the temporary docker-compose
    file if it exists
    """
    utils.stop_all_docker_containers()

    if utils.should_remove_docker_compose_file():
        utils.remove_docker_compose_file()


def config(args):
    utils.print_config()


def add_commands(subparsers):
    attach_parser = subparsers.add_parser('attach')
    attach_parser.add_argument('service')
    attach_parser.set_defaults(func=attach)

    init_parser = subparsers.add_parser('init', help='Create the configuration file')
    init_parser.add_argument('services', nargs='*')
    init_parser.set_defaults(func=init)

    start_parser = subparsers.add_parser('start')
    start_parser.add_argument('services', nargs='*')
    start_parser.add_argument('--ignore', nargs='*', help='Space separated list of service to ignore.')
    start_parser.add_argument('-v', action='store_true',
                              help='Verbose output')
    start_parser.add_argument('-l', help='Log level: (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
    start_parser.set_defaults(func=start)

    down_parser = subparsers.add_parser('down')
    down_parser.add_argument('services', nargs='*')
    down_parser.add_argument('--ignore', nargs='*')
    down_parser.add_argument('-v', action='store_true',
                             help='Verbose output')
    down_parser.add_argument('-l', help='Log level: (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
    down_parser.set_defaults(func=down)

    top_parser = subparsers.add_parser('top', help='Display the running processes for each service.')
    top_parser.add_argument('services', nargs='*')
    top_parser.set_defaults(func=top)

    gitpull_parser = subparsers.add_parser('gitpull')
    gitpull_parser.add_argument('--keep', action='store_true', default=False,
                                help='Return to original branch if not on master after pull')
    gitpull_parser.add_argument('services', nargs='*')
    gitpull_parser.set_defaults(func=gitpull)

    pull_parser = subparsers.add_parser('pull')
    pull_parser.add_argument('services', nargs='*')
    pull_parser.set_defaults(func=pull)

    run_parser = subparsers.add_parser('run')
    run_parser.add_argument('--service', help='The name of the service to run the command (e.g. web, worker)')
    run_parser.add_argument('directory')
    run_parser.add_argument('command', nargs='*')
    run_parser.set_defaults(func=run)

    logs_parser = subparsers.add_parser('logs')
    logs_parser.add_argument('-f', action='store_true', help='Continuously tail the running container log')
    logs_parser.add_argument('-t', help='Number of lines to show from the end of the logs for each container. (e.g. '
                                        '-t 400)')
    logs_parser.add_argument('services', nargs='*')
    logs_parser.set_defaults(func=logs)

    list_parser = subparsers.add_parser('list', help='Show container info like "docker ps" but formatted.')
    list_parser.add_argument('--filter', help='Filters listed containers by name.')
    list_parser.set_defaults(func=list_containers)

    kill_parser = subparsers.add_parser('kill')
    kill_parser.add_argument('--keep', action='store_true',
                             help='Keep temp docker-compose file around.')
    kill_parser.add_argument('--service', help='Optionally specify a docker-compose service')
    kill_parser.set_defaults(func=kill)

    stop_parser = subparsers.add_parser('stop')
    stop_parser.set_defaults(func=stop)

    restart_parser = subparsers.add_parser('restart')
    restart_parser.add_argument('service')
    restart_parser.set_defaults(func=restart)

    config_parser = subparsers.add_parser('config', help='Print generated docker-compose-tmp.yml')
    config_parser.set_defaults(func=config)
