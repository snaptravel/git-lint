# Copyright 2013-2014 Sebastian Kreft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Functions for invoking a lint command."""

import collections
import os
import os.path
import re
import string

import gitlint.utils as utils


def missing_requirements_command(missing_programs, installation_string,
                                 filename, unused_lines):
    """Pseudo-command to be used when requirements are missing."""
    verb = 'is'
    if len(missing_programs) > 1:
        verb = 'are'
    return {
        filename: {
            'skipped': [
                '%s %s not installed. %s' % (', '.join(missing_programs), verb,
                                             installation_string)
            ]
        }
    }


# TODO(skreft): add test case for result already in cache.
def lint_command(name, program, arguments, filter_regex, cache_enabled,
                 filename, lines):
    """Executes a lint program and filter the output.

    Executes the lint tool 'program' with arguments 'arguments' over the file
    'filename' returning only those lines matching the regular expression
    'filter_regex'.

    Args:
      name: string: the name of the linter.
      program: string: lint program.
      arguments: list[string]: extra arguments for the program.
      filter_regex: string: regular expression to filter lines.
      cache_enabled: bool: whether using cached results is enabled.
      filename: string: filename to lint.
      lines: list[int]|None: list of lines that we want to capture. If None,
        then all lines will be captured.

    Returns: dict: a dict with the extracted info from the message.
    """
    output = utils.run(name, program, arguments, cache_enabled, filename)
    output_lines = output.split(os.linesep)

    if lines is None:
        lines_regex = r'\d+'
    else:
        lines_regex = '|'.join(map(str, lines))
    lines_regex = '(%s)' % lines_regex

    groups = ('line', 'column', 'message', 'severity', 'message_id')
    filtered_lines = utils.filter_lines(
        output_lines,
        filter_regex.format(lines=lines_regex, filename=re.escape(filename)),
        groups=groups)

    result = []
    for data in filtered_lines:
        comment = dict(p for p in zip(groups, data) if p[1] is not None)
        if 'line' in comment:
            comment['line'] = int(comment['line'])
        if 'column' in comment:
            comment['column'] = int(comment['column'])
        if 'severity' in comment:
            comment['severity'] = comment['severity'].title()
        result.append(comment)

    return {filename: {'comments': result}}


def _replace_variables(data, variables):
    """Replace the format variables in all items of data."""
    formatter = string.Formatter()
    return [formatter.vformat(item, [], variables) for item in data]


# TODO(skreft): validate data['filter'], ie check that only has valid fields.
def parse_yaml_config(yaml_config, repo_home, cache_enabled):
    """Converts a dictionary (parsed Yaml) to the internal representation."""
    config = collections.defaultdict(list)

    variables = {
        'DEFAULT_CONFIGS': os.path.join(os.path.dirname(__file__), 'configs'),
        'REPO_HOME': repo_home,
    }

    for name, data in yaml_config.items():
        command = _replace_variables([data['command']], variables)[0]
        requirements = _replace_variables(
            data.get('requirements', []), variables)
        arguments = _replace_variables(data.get('arguments', []), variables)

        not_found_programs = utils.programs_not_in_path([command] +
                                                        requirements)
        if not_found_programs:
            linter_command = utils.Partial(missing_requirements_command,
                                           not_found_programs,
                                           data['installation'])
        else:
            linter_command = utils.Partial(lint_command, name, command,
                                           arguments, data['filter'],
                                           cache_enabled)
        for extension in data['extensions']:
            config[extension].append(linter_command)

    return config


def lint(filename, lines, config):
    """Lints a file.

    Args:
        filename: string: filename to lint.
        lines: list[int]|None: list of lines that we want to capture. If None,
          then all lines will be captured.
        config: dict[string: linter]: mapping from extension to a linter
          function.

    Returns: dict: if there were errors running the command then the field
      'error' will have the reasons in a list. if the lint process was skipped,
      then a field 'skipped' will be set with the reasons. Otherwise, the field
      'comments' will have the messages.
    """
    _, ext = os.path.splitext(filename)
    if ext in config:
        output = collections.defaultdict(list)
        for linter in config[ext]:
            linter_output = linter(filename, lines)
            for category, values in linter_output[filename].items():
                output[category].extend(values)

        if 'comments' in output:
            output['comments'] = sorted(
                output['comments'],
                key=lambda x: (x.get('line', -1), x.get('column', -1)))

        return {filename: dict(output)}
    else:
        return {
            filename: {
                'skipped': [
                    'no linter is defined or enabled for files'
                    ' with extension "%s"' % ext
                ]
            }
        }
