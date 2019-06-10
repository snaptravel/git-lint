"""Functions for invoking a fix command."""

import collections
import copy
import os

from gitlint import utils


DEFAULT_FIX_LINE_EXPANSION = 0


def missing_requirements_command(missing_programs, installation_string,
                                 filename, _):
    """Pseudo-command to be used when requirements are missing."""
    verb = 'is'
    if len(missing_programs) > 1:
        verb = 'are'
    print('skipped fixing %s: %s %s not installed. %s' %
          (os.path.relpath(filename), ', '.join(missing_programs), verb,
           installation_string))


def get_modified_lines_range_tuples(modified_lines, fix_line_exp):
    """Returns a list of (modified line range start, modified line range end) tuples."""
    if fix_line_exp is None:
        fix_line_exp = DEFAULT_FIX_LINE_EXPANSION
    else:
        try:
            fix_line_exp = int(fix_line_exp)
        except ValueError:
            raise ValueError('Fix line expansion must be a non-negative integer')
        if fix_line_exp < 0:
            raise ValueError('Fix line expansion must be a non-negative integer')
    sorted_lines = sorted(modified_lines)
    modified_lines_ranges = []
    range_start = -1
    range_end = -1
    sorted_lines_len = len(sorted_lines)
    for ix, line in enumerate(sorted_lines):
        if range_start == -1:
            range_start = max(1, line - fix_line_exp)            
        elif line - fix_line_exp > range_end + 1:
            modified_lines_ranges.append((range_start, range_end))
            range_start = max(1, line - fix_line_exp)
        range_end = line + fix_line_exp
        if ix == (sorted_lines_len - 1):
            modified_lines_ranges.append((range_start, range_end))   
    return modified_lines_ranges
  

def fix_command(name, program, arguments, dynamic_arguments, fix_line_exp, filename, lines=None):
    """Executes a fix program."""
    all_arguments = copy.deepcopy(arguments)
    for arg in dynamic_arguments:
        if '{MODIFIED_LINES_RANGE_REPEATED_ARG}' in arg and lines:
          pattern = arg.replace('{MODIFIED_LINES_RANGE_REPEATED_ARG}', '%s-%s')
          all_arguments.extend(
              [pattern % (start, end) for start, end in get_modified_lines_range_tuples(lines, fix_line_exp)])
    utils.run(name, program, all_arguments, False, filename)


def parse_yaml_config(yaml_config, repo_home, fix_line_exp):
    """Converts a dictionary (parsed Yaml) to the internal representation."""
    config = collections.defaultdict(list)

    for name, data in yaml_config.items():
        command = utils.replace_variables([data['command']], repo_home)[0]
        requirements = utils.replace_variables(
            data.get('requirements', []), repo_home)
    
        not_found_programs = utils.programs_not_in_path([command] +
                                                        requirements)
        if not_found_programs:
            fixer_command = utils.Partial(missing_requirements_command,
                                          not_found_programs,
                                          data['installation'])
        else:
            arguments = utils.replace_variables(data.get('arguments', []), repo_home, data.get('config'))
            dynamic_arguments = data.get('dynamic_arguments', [])
            fixer_command = utils.Partial(fix_command, name, command, arguments, dynamic_arguments, fix_line_exp)
        for extension in data['extensions']:
            config[extension].append(fixer_command)

    return config


def fix(filename, config, lines=None):
    """Fixes formatting issues in a file.

    Args:
        filename: string: filename to fix.
        config: dict[string: fixer]: mapping from extension to a fixer
          function.
        lines: list[int]|None: list of lines that we want to format. If None,
          then all lines will be formatted.
    """
    _, ext = os.path.splitext(filename)
    for fixer in config.get(ext, []):
        fixer(filename, lines)
