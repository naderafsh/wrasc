from locale import format_string
from os import path, rename
import yaml as ym
import time
import regex as re

jira_key_regex = r"[A-Z]+\-\d+(?=\s)"
param_regex = r"[a-zA-Z]+_\w*"
req_code_regex = r"[A-Z]+_\w*"

# def _group_replacer(data, match):
#     data_key = match.group(1)
#     return data[data_key]


class ShortHand:
    """
    This class auto completes shorthanded text messages/naes/references based on the recent activity.
    Based on the preset format, it tries to guess 
    and complete shorthanded leading ( and maybe trailing ) text. 
    """

    # expression = r"\([^\(]*<([^<]*)>[^\(]*\)"
    # expression = re.compile(expression)

    # reversed = re.sub(expression, partial(_group_replacer, data), string)
    in_text = ...  # type: str

    def __init__(
        self, group_formats: list, ditto_char="/", pre_dittos=False, post_dittos=False
    ) -> None:

        self.format_list = group_formats
        self.ditto_char = ditto_char
        self.pre_dittos = pre_dittos
        self.post_dittos = post_dittos

        self.full_expression = ""
        for group in self.format_list:
            self.full_expression += "(" + group[0] + ")*" + group[1]

        self.template = re.compile(self.full_expression)
        self.text_groups = [None] * len(group_formats)

    def long(self, in_text):
        self.in_text = in_text
        self._decompose()
        return self._compose()

    def _decompose(self):

        # parse the new text input:
        match = re.search(self.full_expression, self.in_text)
        match_group = match.group()
        match_groups = re.findall(self.full_expression, self.in_text)
        for mg in match_groups:
            if any(mg):
                match_group = list(mg)
                # the first non-empty group is accepted
                break

        pre_text = True
        post_text = False
        for i, old_text in enumerate(self.text_groups):

            if match_group[i]:
                # a text in a field is found
                if match_group[i] == self.ditto_char:
                    # a ditto is found
                    if self.pre_dittos:
                        continue

                pre_text = False
                self.text_groups[i] = match_group[i]
            elif old_text:
                post_text = not pre_text
                if pre_text and self.pre_dittos:
                    if not self.in_text[i] == self.ditto_char:
                        # this is an error, because we haven't found no text and no dittos
                        raise RuntimeError(
                            f"pre_dittos missing at position {i} of {self.in_text}"
                        )

                match_group[i] = old_text
            else:
                # both are blank, we are confused!!
                raise RuntimeError(
                    f"No pretext to complete {self.in_text}, pretext is {self.text_groups} "
                )

    def _compose(self):
        out_text = ""
        # compose the full length output from self.text_fields
        for i, group in enumerate(self.format_list):
            out_text += self.text_groups[i] + group[1]

        return out_text


def avoid_overwrite(filepath):

    n_copies = 0
    while path.exists(filepath):
        name, ext = path.splitext(filepath)
        modif_time_str = time.strftime(
            "%y%m%d_%H%M", time.localtime(path.getmtime(filepath)),
        )
        n_copies_str = f"({n_copies})" if n_copies > 0 else ""
        try:
            rename(
                filepath, f"{name}_{modif_time_str}{n_copies_str}{ext}",
            )
        except FileExistsError:
            # next copy... never overwrite
            n_copies += 1

    return filepath


def parse_params(text):
    """parse text and return parameters in ccc_ccc format split via ","

    Args:
        text ([str]): [text which includes params]

    Returns:
        [list]: [of strings]
    """

    params_list = text if isinstance(text, list) else re.findall(param_regex, text)

    return params_list if len(params_list) > 0 else []


def query_field(any_table, parameters_field):
    """
    finds parameters listed in field "parameters_field" in table "any_table"
    returns the collection of all paameters in parameter_set
    also replaces the original parameter text with parsed list
    """
    parameter_set = set()

    for _record, _fields in any_table.items():
        _fields: dict
        new_parameters = parse_params(_fields[parameters_field])

        parameter_set = parameter_set.union(set(new_parameters))

        # DONE remove the side effect
        # _fields[parameters_field] = new_parameters

    return parameter_set


def dump_obj(myobj, yaml_dump_file):

    with open(yaml_dump_file, "w+") as f:
        try:
            ym.safe_dump(myobj, f, default_flow_style=False)
            success = True
        except Exception:
            success = False
        finally:
            f.close()
            return success


def undump_obj(obj_str, yaml_dump_path):

    with open(path.join(yaml_dump_path, obj_str + ".yaml"), "r") as f:
        myobjects = ym.safe_load(f)
        f.close()

    return myobjects


def dump_class_objs(yourself, obj_str_list, yaml_dump_path):
    """dumps all dicts in the class to corresponding yaml files in requested folder
    yaml file names follow member names

    Args:
        yourself (class): []
        obj_str_list (str): list of members to be dumped
        yaml_dump_path (str): path of dump folder

    Returns:
        [type]: [description]
    """

    list_of_errors = []
    for obj_str in obj_str_list:

        # yaml doesn't know how to represent objects. so to dump dicts of objects, only dump

        if not dump_obj(
            eval("yourself." + obj_str), path.join(yaml_dump_path, obj_str + ".yaml"),
        ):
            list_of_errors.append(obj_str)
    return list_of_errors


def time_stamp(filename):

    create_time_str = time.strftime("%y%m%d_%H%M", time.localtime())
    name, ext = path.splitext(filename)

    return f"{name}_{create_time_str}{ext}"
