"""Functions for invoking a fix command."""

import collections
import os

from gitlint import utils


def missing_requirements_command(missing_programs, installation_string,
                                 filename):
    """Pseudo-command to be used when requirements are missing."""
    verb = 'is'
    if len(missing_programs) > 1:
        verb = 'are'
    print('skipped fixing %s: %s %s not installed. %s' %
          (os.path.relpath(filename), ', '.join(missing_programs), verb,
           installation_string))


def fix_command(name, program, arguments, filename):
    """Executes a fix program."""
    utils.run(name, program, arguments, False, filename)


def parse_yaml_config(yaml_config, repo_home):
    """Converts a dictionary (parsed Yaml) to the internal epresentation."""
    config = collections.defaultdict(list)

    for name, data in yaml_config.items():
        command = utils.replace_variables([data['command']], repo_home)[0]
        requirements = utils.replace_variables(
            data.get('requirements', []), repo_home)
        arguments = utils.replace_variables(data.get('arguments', []), repo_home)

        not_found_programs = utils.programs_not_in_path([command] +
                                                        requirements)
        if not_found_programs:
            fixer_command = utils.Partial(missing_requirements_command,
                                          not_found_programs,
                                          data['installation'])
        else:
            fixer_command = utils.Partial(fix_command, name, command, arguments)
        for extension in data['extensions']:
            config[extension].append(fixer_command)

    return config


def fix(filename, config):
    """Fixes formatting issues in a file.

    Args:
        filename: string: filename to fix.
        config: dict[string: fixer]: mapping from extension to a fixer
          function.
    """
    _, ext = os.path.splitext(filename)
    for fixer in config.get(ext, []):
        fixer(filename)
