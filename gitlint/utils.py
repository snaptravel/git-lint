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
"""Common function used across modules."""

import functools
import io
import os
import re
import subprocess

# This can be just pathlib when 2.7 and 3.4 support is dropped.
import pathlib2 as pathlib


class Partial(functools.partial):
    """Wrapper around functools partial to support equality comparisons."""

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                self.args == other.args and self.keywords == other.keywords)

    def __repr__(self):
        # This method should never be executed, only in failing tests.
        return (
            'Partial: func: %s, args: %s, kwargs: %s' %
            (self.func.__name__, self.args, self.keywords))  # pragma: no cover


def filter_lines(lines, filter_regex, groups=None):
    """Filters out the lines not matching the pattern.

    Args:
      lines: list[string]: lines to filter.
      pattern: string: regular expression to filter out lines.

    Returns: list[string]: the list of filtered lines.
    """
    pattern = re.compile(filter_regex)
    for line in lines:
        match = pattern.search(line)
        if match:
            if groups is None:
                yield line
            elif len(groups) == 1:
                yield match.group(groups[0])
            else:
                matched_groups = match.groupdict()
                yield tuple(matched_groups.get(group) for group in groups)


# TODO(skreft): add test
def which(program):
    """Returns a list of paths where the program is found."""
    if (os.path.isabs(program) and os.path.isfile(program) and
            os.access(program, os.X_OK)):
        return [program]

    candidates = []
    locations = os.environ.get("PATH").split(os.pathsep)
    for location in locations:
        candidate = os.path.join(location, program)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            candidates.append(candidate)
    return candidates


def programs_not_in_path(programs):
    """Returns all the programs that are not found in the PATH."""
    return [program for program in programs if not which(program)]


def _open_for_write(filename):
    """Opens filename for writing, creating the directories if needed."""
    dirname = os.path.dirname(filename)
    pathlib.Path(dirname).mkdir(parents=True, exist_ok=True)

    return io.open(filename, 'w')


def _get_cache_filename(name, filename):
    """Returns the cache location for filename and program name."""
    filename = os.path.abspath(filename)[1:]
    home_folder = os.path.expanduser('~')
    base_cache_dir = os.path.join(home_folder, '.git-lint', 'cache')

    return os.path.join(base_cache_dir, name, filename)


def get_output_from_cache(name, filename):
    """Returns the output from the cache if still valid.

    It checks that the cache file is defined and that its modification time is
    after the modification time of the original file.

    Args:
      name: string: name of the program.
      filename: string: path of the filename for which we are retrieving the
        output.

    Returns: a string with the output, if it is still valid, or None otherwise.
    """
    cache_filename = _get_cache_filename(name, filename)
    if (os.path.exists(cache_filename) and
            os.path.getmtime(filename) < os.path.getmtime(cache_filename)):
        with io.open(cache_filename) as f:
            return f.read()

    return None


def save_output_in_cache(name, filename, output):
    """Saves output in the cache location.

    Args:
      name: string: name of the program.
      filename: string: path of the filename for which we are saving the output.
      output: string: full output (not yet filetered) of the program.
    """
    cache_filename = _get_cache_filename(name, filename)
    with _open_for_write(cache_filename) as f:
        f.write(output)


def run(name, program, arguments, cache_enabled, filename):
    """Runs a program on a file using the given arguments.

    Args:
      name: string: the name of the program.
      program: string: program.
      arguments: list[string]: extra arguments for the program.
      cache_enabled: bool: whether using cached results is enabled.
      filename: string: filename to execute the program on.

    Returns:
      The output from the program.
    """
    output = None
    if cache_enabled:
        output = get_output_from_cache(name, filename)

    if output is None:
        call_arguments = [program] + arguments + [filename]
        try:
            output = subprocess.check_output(
                call_arguments, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as error:
            output = error.output
        except OSError:
            return {
                filename: {
                    'error': [('Could not execute "%s".%sMake sure all ' +
                               'required programs are installed') %
                              (' '.join(call_arguments), os.linesep)]
                }
            }
        output = output.decode('utf-8')
        if cache_enabled:
            save_output_in_cache(name, filename, output)
    return output
