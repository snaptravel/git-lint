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
"""
git-lint: improving source code one step at a time

Lints modified lines in your git repository branch.

It supports many filetypes, including:
    PHP, Python, Javascript, Ruby, CSS, SCSS, PNG, JPEG, RST, YAML, INI, Java,
    among others. See https://github.com/sk-/git-lint for the complete list.

Usage:
    git-lint [-f | --force] [--json] [--mode=MODE] [--no-cache] [--fix | --fix-all] [--fix-linexp=LINES] [FILENAME ...]
    git-lint [-t | --tracked] [-f | --force] [--json] [--mode=MODE] [--no-cache] [--fix | --fix-all] [--fix-linexp=LINES]
    git-lint -h | --version

Options:
    -h                  Show the usage patterns.
    --version           Prints the version number.
    -f --force          Shows all the lines with problems.
    -t --tracked        Lints only tracked files in the index.
    --json              Prints the result as a json string. Useful to use it in
                        conjunction with other tools.
    --mode=MODE         [merge-base, local, last-commit] Default is merge-base.
 
                         merge-base: Checks modifications since the merge-base commit
                         of this branch with master. Not supported for Mercurial vcs.
                  
                         local: Checks local modifications (those that have not yet been
                         committed).
                  
                         last-comit: Checks modifications since just prior to the last commit.
    --no-cache           If set, do not make use of the lint results cache.
    --fix                If set, run code formatters ('fixers') before linting. Linting will be applied
                         to changes post-fixing. Formatters that support formatting specific line
                         ranges in a file will be passed modified line ranges corresponding to the mode.
    --fix-linexp=LINES   When --fix is passed, this flag controls the number of lines above and below a
                         modified line to format. For instance, if line 3 is modified and --fix-linexp=1
                         then lines 2-4 will be formatted. Defaults to 0. Must be a non-negative integer.
    --fix-all            Same as fix, but runs formatting on all lines for all formatters.
"""

from __future__ import unicode_literals

import codecs
import functools
import json
import multiprocessing
import os
import os.path
import re
import sys
from concurrent import futures

import docopt
import termcolor
import yaml

import gitlint.fixers as fixers
import gitlint.git as git
import gitlint.hg as hg
import gitlint.linters as linters
from gitlint.version import __VERSION__

ERROR = termcolor.colored('ERROR', 'red', attrs=('bold',))
SKIPPED = termcolor.colored('SKIPPED', 'yellow', attrs=('bold',))
OK = termcolor.colored('OK', 'green', attrs=('bold',))


def find_invalid_filenames(filenames, repository_root):
    """Find files that does not exist, are not in the repo or are directories.

    Args:
      filenames: list of filenames to check
      repository_root: the absolute path of the repository's root.

    Returns: A list of errors.
    """
    errors = []
    for filename in filenames:
        if not os.path.abspath(filename).startswith(repository_root):
            errors.append((filename, 'Error: File %s does not belong to '
                           'repository %s' % (filename, repository_root)))
        if not os.path.exists(filename):
            errors.append((filename,
                           'Error: File %s does not exist' % (filename,)))
        if os.path.isdir(filename):
            errors.append((filename, 'Error: %s is a directory. Directories are'
                           ' not yet supported' % (filename,)))

    return errors


def get_config(repo_root):
    """Gets the configuration file either from the repository or the default."""
    config = os.path.join(os.path.dirname(__file__), 'configs', 'config.yaml')

    if repo_root:
        repo_config = os.path.join(repo_root, '.gitlint.yaml')
        if os.path.exists(repo_config):
            config = repo_config

    with open(config) as f:
        # We have to read the content first as yaml hangs up when reading from
        # MockOpen
        content = f.read()
        # Yaml.load will return None when the input is empty.
        if not content:
            yaml_config = {}
        else:
            yaml_config = yaml.load(content, Loader=yaml.SafeLoader)

    return yaml_config


def format_comment(comment_data):
    """Formats the data returned by the linters.

    Given a dictionary with the fields: line, column, severity, message_id,
    message, will generate a message like:

    'line {line}, col {column}: {severity}: [{message_id}]: {message}'

    Any of the fields may nbe absent.

    Args:
      comment_data: dictionary with the linter data.

    Returns:
      a string with the formatted message.
    """
    format_pieces = []
    # Line and column information
    if 'line' in comment_data:
        format_pieces.append('line {line}')
    if 'column' in comment_data:
        if format_pieces:
            format_pieces.append(', ')
        format_pieces.append('col {column}')
    if format_pieces:
        format_pieces.append(': ')

    # Severity and Id information
    if 'severity' in comment_data:
        format_pieces.append('{severity}: ')

    if 'message_id' in comment_data:
        format_pieces.append('[{message_id}]: ')

    # The message
    if 'message' in comment_data:
        format_pieces.append('{message}')

    return ''.join(format_pieces).format(**comment_data)


def get_vcs_root():
    """Returns the vcs module and the root of the repo.

    Returns:
      A tuple containing the vcs module to use (git, hg) and the root of the
      repository. If no repository exisits then (None, None) is returned.
    """
    for vcs in (git, hg):
        repo_root = vcs.repository_root()
        if repo_root:
            return vcs, repo_root

    return (None, None)


def get_vcs_modified_lines(vcs, force, filename, extra_file_data, commit):
    if force:
        return None
    return vcs.modified_lines(filename, extra_file_data, commit=commit)



def process_file(vcs, commit, force, linter_config, fixer_config, fix, fix_all, file_data):
    """Lint and optionally fix the file.

    Returns:
      The results from the linter.
    """
    filename, extra_data = file_data

    if fix:
        fixers.fix(filename, fixer_config, get_vcs_modified_lines(vcs, force, filename, extra_data, commit))
    elif fix_all:
        fixers.fix(filename, fixer_config)
    
    result = linters.lint(filename, get_vcs_modified_lines(vcs, force, filename, extra_data, commit), linter_config)
    result = result[filename]

    return filename, result


def main(argv, stdout=sys.stdout, stderr=sys.stderr):
    """Main gitlint routine. To be called from scripts."""
    # Wrap sys stdout for python 2, so print can understand unicode.
    linesep = os.linesep
    if sys.version_info[0] < 3:
        if stdout == sys.stdout:
            stdout = codecs.getwriter("utf-8")(stdout)
        if stderr == sys.stderr:
            stderr = codecs.getwriter("utf-8")(stderr)
        linesep = unicode(os.linesep)  # pylint: disable=undefined-variable

    arguments = docopt.docopt(
        __doc__, argv=argv[1:], version='git-lint v%s' % __VERSION__)

    json_output = arguments['--json']

    vcs, repository_root = get_vcs_root()

    if vcs is None:
        stderr.write('fatal: Not a git repository' + linesep)
        return 128

    commit = None
    mode = arguments['--mode']
    if not mode or mode == 'merge-base':
        commit = vcs.merge_base_commit()
    elif mode == 'last-commit':
        commit = vcs.last_commit()
    elif mode != 'local':
        raise ValueError(
            'Invalid mode. Valid modes are: merge-base, local, or last-commit.')

    config = get_config(repository_root)

    if arguments['FILENAME']:
        invalid_filenames = find_invalid_filenames(arguments['FILENAME'],
                                                   repository_root)
        if invalid_filenames:
            invalid_filenames.append(('', ''))
            stderr.write(
                linesep.join(invalid[1] for invalid in invalid_filenames))
            return 2

        changed_files = vcs.modified_files(
            repository_root, tracked_only=arguments['--tracked'], commit=commit)
        modified_files = {}
        for filename in arguments['FILENAME']:
            normalized_filename = os.path.abspath(filename)
            modified_files[normalized_filename] = changed_files.get(
                normalized_filename)
    else:
        modified_files = vcs.modified_files(
            repository_root, tracked_only=arguments['--tracked'], commit=commit)
        if config.get('ignore-regex'):
            regex_list = [
                '(%s)' % r for r in config.get('ignore-regex').split()
            ]
            regex = re.compile('|'.join(regex_list))
            modified_files = {
                k: v for k, v in modified_files.items() if not regex.match(k)
            }

    linter_not_found = False
    files_with_problems = 0
    linter_config = linters.parse_yaml_config(
        config.get('linters', {}), repository_root, not arguments['--no-cache'])
    fixer_config = fixers.parse_yaml_config(config.get('fixers', {}), repository_root, arguments['--fix-linexp'])
    json_result = {}

    with futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count())\
            as executor:
        processfile = functools.partial(process_file, vcs, commit,
                                        arguments['--force'], linter_config,
                                        fixer_config, arguments['--fix'], arguments['--fix-all'])
        for filename, result in executor.map(
                processfile, [(filename, modified_files[filename])
                              for filename in sorted(modified_files.keys())]):

            rel_filename = os.path.relpath(filename)

            if not json_output:
                stdout.write('Processing file: %s%s' % (termcolor.colored(
                    rel_filename, attrs=('bold',)), linesep))

            output_lines = []
            if result.get('error'):
                output_lines.extend('%s: %s' % (ERROR, reason)
                                    for reason in result.get('error'))
                linter_not_found = True
            if result.get('skipped'):
                output_lines.extend('%s: %s' % (SKIPPED, reason)
                                    for reason in result.get('skipped'))
            if not result.get('comments', []):
                if not output_lines:
                    output_lines.append(OK)
            else:
                files_with_problems += 1
                for data in result['comments']:
                    formatted_message = format_comment(data)
                    output_lines.append(formatted_message)
                    data['formatted_message'] = formatted_message

            if json_output:
                json_result[filename] = result
            else:
                output = linesep.join(output_lines)
                stdout.write(output)
                stdout.write(linesep + linesep)

    if json_output:
        # Hack to convert to unicode, Python3 returns unicode, wheres Python2
        # returns str.
        stdout.write(
            json.dumps(json_result,
                       ensure_ascii=False).encode('utf-8').decode('utf-8'))

    if files_with_problems > 0:
        return 1
    if linter_not_found:
        return 4
    return 0
