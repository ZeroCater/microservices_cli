# Microservices CLI

This is a CLI utility written in Python that makes developing microservices with Docker easy. The CLI utilizes docker-compose to orchestrate multiple services, and offers additional functionality like pulling code, Docker images, and starting groups of services. It handles the core interactions between services and the code, git, and docker-compose.

Note: This is very much a work in progress and everything in this project is liable to change so don't depend on this project yet for anything mission critical.

## Installation

Coming soon. For now you can clone the repo and run `pip install -e .` from inside the `microservices_cli/` directory.

## Usage

Each service being orchestrated must have a `docker-compose.yml` file in the root of the project, and all of the projects must be siblings of each other in a single directory.

All configuration lives in a file located at `~/.ms` and is formatted with JSON. The only config variable that needs to be set is `BASE_DIR` which is the parent folder of all services. An example of the bare minimum `.ms` file would look like this:

```json
{
    "BASE_DIR": "/Users/tony/Documents/Development/microservices_project"
} 
```

Once that is set, there are several commands available to start working with the services:
 
### start
Usage: `ms start [-h] [services [services ...]]`

The start command will take one or more services and start them simultaneously. If no services are specified, the command will start all services inside the root project directory that has a `docker-compose.yml` file in it.
 
Additionally, a "service constellation" can be substituted in place of a service name, which can be used to start a group of services instead of needing to type out the names of each service individually. Constellations can be set by specifying them with the `SERVICE_CONSTELLATIONS` configuration option.

### attach
Usage: `ms attach [-h] service`

Attach will take a single service attempt to drop you into a bash shell in a running container. The container you are trying to attach to must be currently running.

### pull
Usage: `ms pull [-h] [services [services ...]]`

Pull will pull Docker images from DockerHub for the service(s) specified in the command. If no services are passed, the command will pull images for all services.

### gitpull
Usage: `ms gitpull [-h] [services [services ...]]`
 
Gitpull will take a list of services (defaulting to all if no services are passed) and pull the master branch for each of the repositories. If any repositories are  on a branch that is not master, they will checkout master, pull, and then checkout the original branch leaving the repository as it was before the pull.

## Config options

There are a number of configuration variables that can be set in the `~/.ms` file to change the way the CLI behaves.

### `BASE_DIR`

This is the only required configuration option for the operation of the CLI. The base directory is the root directory that contains all the services beneath it as children.

```
microservices_proj/
|-- service1/
|-- service2/
|-- service3/
```

In this case, `microservices_proj` would be the base directory of the project.

### `DOCKER_COMPOSE_FILE`

Default: `BASE_DIR/docker-compose-tmp.yml`

This is an optional configuration option that allows changing the location of the temporary docker-compose file that is created by the microservices CLI when it runs. When services are started, this temporary file is created at this location and when the stack is brought down it is automatically removed.

### `SERVICE_MAPPING`

The service mapping configuration option allows you to specify a name for you services that differs from the folder name that they are in. This is a JSON object that simply maps directory name to desired service name. An example is:

```
"SERVICE_MAPPING": {
    "my-service": "service"
}
```

### `SERVICE_CONSTELLATIONS`

Service constellations allow you to specify groups, or subsets, of all services in your base directory that you would like to bring up. If you're developing something that only needs a handful of your services, or if you regularly only need to start a certain subset of services this option can help simplify things. An example is:

```
"SERVICE_CONSTELLATIONS": {
    "mygroup": [
        "service1/",
        "service2/",
        "service3/"
    ]
}
```

With this constellation set, you can now run `ms start mygroup` instead of needing to run `ms start service1 service2 service3`.

### `SINGLETON_SERVICES`

Singleton services allow you to specify services that should only be started a single time, despite how many times they show up in the `docker-compose.yml` files of the individual services. This is useful in situations where each service may individually specify `rabbitmq` or `redis`, which is needed when running a service on its own, but all services need to share a single `rabbitmq` instance when running multiple at a time.

Example:

```
"SINGLETON_SERVICES": ["rabbitmq", "redis"]
```

### `PLUGINS`

Plugins are dynamically loaded based on the value of this configuration variable. Plugins can be installed via pip, and then be added here and will be available from within the command.

For a plugin to work, it should be available on your Python path (you should be able to open a Python interpreter and type `import <plugin_name>` without seeing any errors).

Example:

```
"PLUGINS": ["myplugin"]
```

## Plugin system

The plugin system is designed to make the microservices CLI endlessly extensible by anyone who has a particular use case that they'd like to build off of the base CLI.

Anyone wishing to create a plugin need only implement a module compatible with argparse. The microservices CLI will call the `add_commands()` method on modules specified in the `PLUGINS` config variable.

Plugins can interact with the base CLI utilizing the `utils` module of the package. Anything that interacts with the code, services, git, or docker should be done through the built-in utils. If there is any functionality that is missing belonging to any of these domains, please open an issue or a PR to add it. Plugins can implement their own utils that handle interactions with other areas. An example plugin may handle hooking up microservices with Heroku, so this plugin's utils would manage any interactions with Heroku, but call the microservices CLI utils to do anything related to the services on disk.

## Contribution

This is a work in progress and Issues and Pull Requests are welcome.

## License

The microservices CLI is free software, and may be redistributed under the terms specified in the [LICENSE](LICENSE) file.
