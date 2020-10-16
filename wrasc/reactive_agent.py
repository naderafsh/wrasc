#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/wrasc/wrasc/reactive_agent.py $
# $Revision: #1 $
# $DateTime: 2020/08/09 22:35:08 $
# Last checked in by: $Author: afsharn $
#
# Description
# <description text>
#
# Copyright (c) 2019 Australian Synchrotron
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# Licence as published by the Free Software Foundation; either
# version 2.1 of the Licence, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public Licence for more details.
#
# You should have received a copy of the GNU Lesser General Public
# Licence along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Contact details:
# nadera@ansto.gov.au
# 800 Blackburn Road, Clayton, Victoria 3168, Australia.
#


import functools
import sys
import time
import inspect
from csv import excel
from timeit import default_timer as timer
from typing import Set, Any, List, Union, Tuple

import numpy as np
from epics import PV
from wrasc.reactive_utils import myEsc, cls, retrieve_name, retrieve_name_in_globals
import re
from collections import OrderedDict
import logging
import os
from datetime import datetime

import flask_table as ft
import yaml as ym
from pathlib import Path


""" This is main DModel library! 
If you get compile error at pass 3, "max iteration" it is most likely due to a circular reference. 
    A common error which may lead to false circular reference error is:
        agents references by name in their own methods
        DONT use literal name of the agent inside methods which will be used by it. Always use self to self reference!

"""

# output_dir = os.path.expanduser("~") + "/wrasc_output"
output_dir = "ra_out"

dmodel_log_filename = os.path.join(output_dir, "dmodel_compiler" + ".log")
info_log_filename = os.path.join(output_dir, "reactive_agents_process" + ".log")

Path(output_dir).mkdir(parents=True, exist_ok=True)

# Create two logger files
formatter = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
# first file logger
logger_dmodel = logging.getLogger(__name__ + "_compiler")
hdlr_1 = logging.FileHandler(dmodel_log_filename, mode="w+")
hdlr_1.setFormatter(formatter)
logger_dmodel.setLevel(logging.DEBUG)
logger_dmodel.addHandler(hdlr_1)
logger_dmodel.info(
    "SCS reactive agents module is compiling..."  # at {}".format(datetime.now())
)

formatter = logging.Formatter(
    "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
)

# second Logger
logger_default = logging.getLogger("reactive_agents_default")
hdlr_2 = logging.FileHandler(info_log_filename)
hdlr_2.setFormatter(formatter)
logger_default.setLevel(logging.INFO)
logger_default.addHandler(hdlr_2)
logger_default.addHandler(logging.StreamHandler(sys.stdout))
logger_default.info("SCS reactive agents module is loading...")

# third logger
logger_debug = logging.getLogger("debug")
hdlr_3 = logging.FileHandler(info_log_filename)
hdlr_3.setFormatter(formatter)
logger_debug.setLevel(logging.DEBUG)
logger_debug.addHandler(hdlr_3)
# noneed for the debug messages to spit on by the logger ?????
logger_debug.addHandler(logging.StreamHandler(sys.stdout))

agent_var_debug_format = '  {0} {1}: {3} {4} "{2}"'
agent_debug_format = "  {0}"
var_debug_format = '[{0}] {2} {3} "{1}"'

# TODO remove hardcoded filename
excel_out_file_name = "excel_output.tpv"
excel_out_path = output_dir
html_out_filename = "SCS-Poll-Vars.html"
html_out_path = excel_out_path


# Declare your table
class VarsTable(ft.Table):
    name = ft.Col("Agent")
    description = ft.Col("Value")


def pythonise_ag_name(_name):
    _name = re.sub(r"g__", "", _name)
    _name = re.sub("__", r".", _name)
    return _name


def excelise_ag_name(_name):
    """

    :type _name: str
    """
    _name = re.sub(r"\.", "__", _name)
    if (not _name.startswith("ag_")) and _name.endswith("_ag"):
        _name = "ag_" + _name[:-3]

    return _name


class InStates:
    Invalid = None, "Invalid"
    Valid = True, "Valid"
    Inhibited = False, "Inhibited"


class OutStates:
    Idle = None, "Idle"
    Armed = False, "Armed"
    Done = True, "Done"


class StateLogics:
    Invalid = InStates.Invalid[0]
    Valid = InStates.Valid[0]
    Inhibited = InStates.Inhibited[0]
    Idle = OutStates.Idle[0]
    Armed = OutStates.Armed[0]
    Done = OutStates.Done[0]


class StateNames:
    Invalid = InStates.Invalid[1]
    Valid = InStates.Valid[1]
    Inhibited = InStates.Inhibited[1]
    Idle = OutStates.Idle[1]
    Armed = OutStates.Armed[1]
    Done = OutStates.Done[1]


default_act_on_valid = """print('=', end="")"""
default_motor_fields = [
    ".VAL",
    ":INIT.PROC",
    ":FORCE_UNINIT.PROC",
    ".RBV",
    ".DMOV",
    ".MOVN",
]


# def pv_callback(fullpvname, value, status, **kwargs):
#     pass


# DModel methods
class Loci(object):
    def __init__(self, n_dims=(1, 1)):

        self.n_dims = n_dims
        self.position = np.arange(n_dims[0])
        self.coords = np.arange(n_dims[1])
        self.inverse_trans = None
        self.forward_trans = None
        self.cs_name = None

    def set(self, coords=0, cs_name=None, inverse_trans=None, forward_trans=None):
        self.cs_name = cs_name
        self.coords = coords

        if inverse_trans:
            self.inverse_trans = inverse_trans
        if forward_trans:
            self.forward_trans = forward_trans

        self.refresh_check()

    def set_position(self, position_in_cs0):

        if self.forward_trans:
            _r = self.forward_trans(position_in_cs0)
        else:
            _r = position_in_cs0
        self.position = _r

    def get_position_in_cs0(self):

        if self.inverse_trans:
            _r = self.inverse_trans(self.position)
        else:
            _r = self.position

        return _r

    def refresh_check(self):
        _check_position = self.position
        _check_position_cs0 = self.get_position_in_cs0()
        self.set_position(_check_position_cs0)
        if self.position != _check_position:
            print(
                "transform is divergent: {} -cs0> {} -to_cs> {}".format(
                    _check_position, _check_position_cs0, self.position
                )
            )


class Device:
    default_dev_prefix = ...  # type: str
    default_dev_pvs = ...  # type: list
    stat_rec_decode = dict(name=0, severity=1, action_pv=2, inverted=3)
    severity_try_decrease_value = 0.001
    master_config = ...  # type: dict
    device_config = ...  # type: dict

    class Status:
        max_severity = ...
        max_severity_errors = ...  # type [[]]
        less_severity_errors = ...
        no_severity_status = ...

    # DONE move setting of prefixes into this init, instead of set PV's? or leave it for later?
    def __init__(
        self,
        device_name="unnamed_device",
        master_config={},
        device_config={},
        eprefix=None,
        dev_prefix=None,
        auto_install_pvs=None,
        **kwargs,
    ):
        self.dev_prefix = dev_prefix
        self.pvf_list = []
        self.pv_by_name = {}
        self.eprefix = eprefix
        self.device_name = device_name

        self.auto_install_pvs = auto_install_pvs

        self.statrec = self.Status()

        if dev_prefix is not None:
            self.dev_prefix = dev_prefix
        else:
            self.dev_prefix = self.default_dev_prefix

        self.default_dev_pvs = None

        self.master_config = master_config
        self.device_config = device_config

    def install_dev_pvs(self, eprefix=None, dev_prefix=None, pvf_list=None, **kwargs):

        if pvf_list is None:
            pvf_list = self.default_dev_pvs
        elif type(pvf_list) is str:
            # TODO proper test if this is a valid PV name
            pvf_list = [pvf_list]

        if eprefix is None:
            eprefix = self.eprefix

        if dev_prefix is None:
            dev_prefix = self.dev_prefix
        if dev_prefix is None:
            dev_prefix = ""

        if eprefix and dev_prefix and pvf_list:

            assert type(pvf_list) is list and type(pvf_list[0]) is str

            if self.pv_by_name is None:
                self.pv_by_name = {}
                self.pvf_list = []

            for _pvf in [item for item in pvf_list if item not in self.pvf_list]:
                self.pvf_list.append(_pvf)
                _pvfPV = PV(eprefix + dev_prefix + _pvf, verbose=False)
                self.pv_by_name.update({_pvf: _pvfPV})

    def get_pv_by_name(self, pv_name=None):

        # validate pv_name
        if type(pv_name) is str and (pv_name in self.pv_by_name):
            _r = self.pv_by_name[pv_name]

        else:
            if self.auto_install_pvs:
                self.install_dev_pvs(pvf_list=pv_name)
                _r = self.pv_by_name[pv_name]
            else:
                _r = None

        return _r


method_names = ["poll_pr", "poll_in", "act_on_invalid", "act_on_valid", "act_on_armed"]
push_method_names = ["poll.force", "poll.unhold", "poll.hold", "act.hold", "act.unhold"]


class MyObservable:
    def __init__(self, **kwargs):
        self.Var = None
        self.SavedVar = None
        self.ErrTol = None
        self.NoRestore = None
        self.Changed = True
        self.Diff = None
        self.ChangeCount = 0
        self.Time = timer()
        self.ChangeTime = self.Time
        self.Err = None
        self.ForcedVar = None

        self.DiffTime = 0
        self.Last = self.Var
        self.LastTime = self.Time

        self.DebounceCycles = 3
        self.VarDebounced = None
        self.NoChangeCount = 0
        self.IsStable = False

        self._hold_counter = 0
        self._force_counter = 0

        self._hold_timer = 0
        self._force_timer = 0

        self._hold_indefinitely = False
        self._force_indefinitely = False

        self.unit = ""
        self.verbose = 0

        self.last_message = ""

    def is_on_hold(self):
        return (
            self._hold_indefinitely
            or (self._hold_counter > 0)
            or (self._hold_timer >= timer())
        )

    def hold(self, for_cycles=1, for_seconds=-1, reset_var=True):
        """ sets Var to invalid and keeps it invalid for requested _hold_counter (cycles)
        unless Var is forced or unhold function is called"""
        # TODO shall we infer here out of cycle?
        #  could it be left to happen in due time?
        #  maybe NOT
        if reset_var:
            self.Var = None
            self.Changed = False

        # -1 means indefinitely
        if (for_cycles < 0) and (for_seconds < 0):
            # this is dangerously effective as it stops count down and locks
            self._hold_indefinitely = True
        # if someone is requesting for invalidation for MORE than already planned:
        if self._hold_counter < for_cycles:
            self._hold_counter = for_cycles

        time_0 = timer()
        if self._hold_timer < time_0 + for_seconds:
            self._hold_timer = time_0 + for_seconds

        return True

    def unhold(self):
        """ends hold cycle and evaluates inVar"""
        self._hold_counter = 0
        self._hold_indefinitely = False
        # Removing (200406) immediate procing as _proc is now external to the observables
        # self._proc()

        return True

    def force(self, forced_var, for_cycles=1, for_seconds=0, immediate=False):
        """ forces inVar, and unholds at next cycle
        """

        self.ForcedVar = forced_var
        if immediate:
            self.Var = forced_var
        # TODO also, unhold? or leave it to the user to unhold explicitly?
        self._hold_counter = 0
        self._hold_indefinitely = False

        if for_cycles == -1:
            # force indefinitely
            self._force_indefinitely = True

        # if someone is requesting for invalidation for MORE than already planned:
        if self._force_counter < for_cycles:
            self._force_counter = for_cycles

        time_0 = timer()
        if self._force_timer < time_0 + for_seconds:
            self._force_timer = time_0 + for_seconds

        return True

    def delta(self):

        if self.Changed:
            r = self.Diff
            t = self.DiffTime
        else:
            r = 0
            t = 0

        return r, t

    def check_var(self):
        if self._hold_indefinitely:
            self._hold_counter = 1

        if self._force_indefinitely:
            self._force_counter = 1

        if not ((self._hold_counter < 1) and (self._hold_timer < timer())):
            # TODO review: do we need persistent invalidation? probably NO
            # changed it to reflect
            # if it is holding, then it is not "just" changed.
            # all the otrher counts may still stay frozen, but at least Changed shall be false
            #

            self.Changed = False

            return_message = "on hold"
            # recalc remaining invalidation time
            self._hold_counter -= 1

            self.last_message = return_message

            return return_message

        # if poll.forced, use poll.forced value
        if self._force_counter > 0:
            _v = self.ForcedVar
            return_message = "forced"
            self._force_counter -= 1

            self.set_var(_v, return_message)

            return return_message

        # return blank to indicate not forced nor on hold
        return ""

    def set_var(self, _v, return_message):

        self.last_message = return_message

        # TODO improve change setting by defining inChange_threshold,
        if _v is None:
            self.Changed = False
        else:
            if self.Var is None:
                if self.Last is None:
                    # there has never been a valid value before but now its valid. This is a change
                    self.Changed = True
                else:
                    # val1->None .. None->val2 is a change.
                    self.Changed = not (_v == self.Last)
                    if self.Changed:
                        self.DiffTime = timer() - self.LastTime
            else:
                # inVar is valid
                self.Changed = not (_v == self.Var)
                if self.Changed:
                    self.DiffTime = timer() - self.Time
                    self.Last = self.Var
                    self.LastTime = self.Time

            if self.Changed:
                self.NoChangeCount = 0
                self.ChangeCount += 1
                self.ChangeTime = timer()
                try:
                    # this may throw an exception depending on dmAgentType... put this last!
                    if isinstance(self.Var, type(_v)):
                        self.Diff = _v - self.Var
                except TypeError:
                    pass
            else:
                # when not on hold, a false Change counts.
                self.NoChangeCount += 1
                # two consecutive valid variables are equal: valid and unchanged
                if self.NoChangeCount >= self.DebounceCycles:
                    self.VarDebounced = self.Var
                else:
                    # change debounced
                    self.VarDebounced = self.VarDebounced

            self.IsStable = self.NoChangeCount > self.DebounceCycles

        # Assign new variable: Time is the time of last update, weather it is changed or not or even None.

        self.Time = timer()
        self.Var = _v


# DModel agent class
class Agent(object):
    depend_ags = ...  # type: Set[Any]
    infer_ags = ...  # type: Set[Any]
    preced_ags = ...  # type: Set[Any]
    dmAgentType = "uninitialised"
    owner = Device()

    poll_pr = ...  # type: Method
    poll_in = ...  # type: Method
    act_on_invalid = ...  # type: Method
    act_on_valid = ...  # type: Method
    act_on_armed = ...  # type: Method

    act_on = ...  # type: Method

    poll = ...  # type: MyObservable
    act = ...  # type: MyObservable

    def __init__(self, owner: Device = None, **kwargs):

        self.owner = owner
        self.poll = MyObservable(**kwargs)
        self.act = MyObservable(**kwargs)

        self.inhibited = False
        self.known = False
        self.in_state = None
        self.out_state = None

        self.poll_pr = None
        self.poll_in = None

        self.act_on_invalid = None
        self.act_on_valid = None
        self.act_on_armed = None

        self.act_on = None

        self.unit = ""
        self.in_unit = ""
        self.out_unit = ""

        self.verbose = 0
        self.in_verbose = 0
        self.out_verbose = 0

        self.in_message = ""
        self.out_message = ""

        self.first_name = None
        self.owner_name = ""

        if self.owner:
            if hasattr(owner, "device_name"):
                self.owner_name = owner.device_name
            self.eprefix = self.owner.eprefix
            self.dev_prefix = self.owner.dev_prefix
        else:
            self.eprefix = None
            self.dev_prefix = None

        self.name = None
        self.dmAgentType = "untyped"
        self.description = ""
        self.depend_ags = set()
        self.preced_ags = set()
        self.infer_ags = set()
        self.layer = None

        self.time_out = None

        self.setup(**kwargs)

        self.pvs_by_name = None
        self.pvs_by_name_PVs = None
        self.inpvname = None
        self.in_PV = None
        self.outpvname = None
        self.out_PV = None

        self.install_pvs(**kwargs)

        self.agent_list = None

    def setup(
        self,
        initial_value=None,
        # eprefix=None,
        poll_in=None,
        act_on_invalid=None,
        act_on_valid=None,
        act_on_armed=None,
        poll_pr=None,
        verbose=0,
        name: str = None,
        first_name=None,
        dmAgentType=None,
        description=None,
        time_out=None,
        unit="",
        **kwargs,
    ):

        if initial_value:
            self.poll.force(initial_value, for_cycles=1)

        # TODO this shall be obsolete
        # if eprefix:
        #     self.eprefix = eprefix
        if dmAgentType:
            self.dmAgentType = dmAgentType
        if unit:
            self.unit = unit

        if poll_pr:
            self.poll_pr = poll_pr

        if poll_in:
            self.poll_in = poll_in
        if act_on_invalid:
            self.act_on_invalid = act_on_invalid
        if act_on_valid:
            self.act_on_valid = act_on_valid
        if act_on_armed:
            self.act_on_armed = act_on_armed

        if verbose:
            self.verbose = verbose

        if description:
            self.description = description

        if name:
            # poll.forced name, not recommended
            self.name = name
        else:
            if first_name:
                self.first_name = first_name
                if self.owner_name:
                    self.name = self.owner_name + "." + self.first_name

                else:
                    self.name = self.first_name

        if time_out:
            self.time_out = time_out

    def install_pvs(
        self,
        eprefix=None,
        dev_prefix=None,
        inpvname=None,
        outpvname=None,
        pvs_by_name=None,
        **kwargs,
    ):

        if eprefix is None:
            eprefix = self.eprefix

        if dev_prefix is None:
            dev_prefix = self.dev_prefix
        if dev_prefix is None:
            dev_prefix = ""

        if inpvname:
            self.inpvname = inpvname
            self.in_PV = PV(
                eprefix + dev_prefix + inpvname, verbose=False
            )  # , callback=handle_update)

        if outpvname:
            self.outpvname = outpvname
            self.out_PV = PV(
                eprefix + dev_prefix + outpvname, verbose=False
            )  # , callback=handle_update)

        if pvs_by_name:
            self.pvs_by_name = pvs_by_name
            self.pvs_by_name_PVs = {}

            for _pvf in self.pvs_by_name:
                _pvfPV = PV(
                    self.eprefix + self.dev_prefix + _pvf, verbose=False
                )  # , callback=handle_update)
                self.pvs_by_name_PVs.update({_pvf: _pvfPV})

    @property
    def is_done(self):
        # if action is Done
        if self.act.Var:
            return True
        else:
            return False

    def state(self):

        # DONE change the state notation from text to enum

        # TODO add separate "invalid" flag, detach it from inVar/outVar

        if self.inhibited:
            self.in_state = StateNames.Inhibited
            self.out_state = StateNames.Inhibited
            self.poll.ChangeCount = 0
            self.poll.NoChangeCount = 0
            self.act_on = None
            return self.in_state, self.out_state

        # set act_on to valid. If invalid
        self.act_on = self.act_on_valid

        if self.poll.Var is None:
            self.in_state = StateNames.Invalid

            self.poll.ChangeCount = 0
            self.poll.NoChangeCount = 0
            # act on invalid
            self.act_on = self.act_on_invalid
        else:
            self.in_state = StateNames.Valid

        if self.act.Var is StateLogics.Idle:
            self.out_state = StateNames.Idle
            self.act.ChangeCount = 0
            # self.act.NotChangeCount = 0
        elif self.act.Var is StateLogics.Armed:
            self.out_state = StateNames.Armed
            # # now if its not Invalid then act on armed
            # if inst != StateNames.Invalid:
            #     self.act_on = self.act_on_armed

            # TODO verify the change: 200524 : on_armed takes priority over on_invalid
            self.act_on = self.act_on_armed
        else:
            self.out_state = StateNames.Done

        self.known = (not self.inhibited) and (self.poll.Var is not None)

        return self.in_state, self.out_state

    def _in_proc(self):

        # DONE look at the list of valid refs and eval if your precedents are all valid. Otw post a message
        # if planned invalidation is passed

        _v = None

        return_message = self.poll.check_var()

        if return_message:
            return self.state(), return_message

        if self.poll_in:
            try:
                # pre poll function, which will NOT be interrogated for dependencies

                # now fuse the pre and poll:
                # if poll is unknown, the it wins.
                # if poll is known, the pre can represent the value
                # by multiplication!
                # i.e. if poll returns True, then pre determins the value
                #
                try:
                    if self.poll_pr is not None:
                        self.inhibited = not self.poll_pr(self)  # override to diabled
                except:
                    # TODO fix this
                    raise RuntimeError(
                        f"Exception in poll_pr func of agent {self.name} "
                    )

                if self.inhibited:
                    _v, return_message = None, "inhibited"
                else:
                    _v, return_message = self.poll_in(self)

            except AttributeError:
                _v = None
                return_message = str(sys.exc_info()[0])
                raise AttributeError(return_message)
            except TypeError:
                _v = None
                return_message = str(sys.exc_info()[0])
            except KeyError:
                _v = None
                return_message = str(sys.exc_info()[0])
        else:
            # not forced and no poll method, retain the existing var
            _v = self.poll.Var
            return_message = ""

        self.poll.set_var(_v, return_message)

        return self.state(), return_message

    def _out_proc(self):
        """

        :return:
        
        """

        # return_message = self.act.check_var()

        # if return_message:
        #     return self.state(), return_message

        _v = None
        return_message = ""
        if self.act._hold_indefinitely:
            self.act._hold_counter = 1

        if not ((self.act._hold_counter < 1) and (self.act._hold_timer < timer())):
            # TODO review: do we need persistant act.hold? probably NO
            # changed it from None to outVar
            _v = self.act.Var
            # in case of holding on timer, decrementing the cycle counter is useless and harmless.
            self.act._hold_counter -= 1
            return_message = "on act.hold..."
        else:
            # calculate the current state
            # DONE Major bug fixed:
            self.state()

            if self.act_on is not None:
                try:
                    # assert(self.act_on == self.act_on_invalid)
                    _v, return_message = self.act_on(self)
                except TypeError:
                    _v = None
                    return_message = str(sys.exc_info()[0])
                except KeyError:
                    _v = None
                    return_message = str(sys.exc_info()[0])

        # TODO improve change setting by defining inChange_threshold
        if self.act.Var is None:
            self.act.Changed = _v is not None
        elif _v is None:
            self.act.Changed = self.act.Var is not None
        else:
            self.act.Changed = _v != self.act.Var

        if self.act.Changed:
            self.act.ChangeCount += 1
            self.act.DiffTime = timer() - self.act.Time
            self.act.Last = self.act.Var
            self.act.LastTime = self.act.Time
            self.act.ChangeTime = timer()
            try:
                # this may through an exception depending on dmAgentType... put this last!
                if isinstance(self.act.Var, type(_v)):
                    self.act.Diff = _v - self.act.Var
            except TypeError:
                pass

        self.act.Var = _v
        self.act.last_message = return_message
        return self.state(), return_message

    def annotate(self):

        status = self.state()
        agname = self.name
        poll_message = self.poll.last_message
        print_str = desc_str = in_var_str = ""

        abbreviated_status = status[0][0] + status[1][0]
        in_var_str = "nil"

        if self.verbose < 1:
            return print_str, desc_str, in_var_str

        if isinstance(self.poll.Var, dict):
            in_var_str = "<"
            for key in self.poll.Var:
                if self.poll.Var[key] is None:
                    in_var_str += " {}:None ".format(key)
                elif isinstance(self.poll.Var[key], str):
                    in_var_str += " {}:{} ".format(key, self.poll.Var[key])
                else:
                    in_var_str += " {}:{:.3E} ".format(key, float(self.poll.Var[key]))
            in_var_str += ">"

        else:
            in_var_str = "{}".format(self.poll.Var)

        _str = "<" + agent_var_debug_format.format(
            agname,
            abbreviated_status,
            poll_message,
            in_var_str,
            "" if self.unit is None else self.unit,
        )

        desc_str = '{0}({2} {3}) "{1}" "{4}"'.format(
            abbreviated_status,
            poll_message,
            in_var_str,
            "" if self.unit is None else self.unit,
            self.act.last_message,
        )

        if (self.poll.Changed or self.act.Changed) and self.verbose > 1:
            desc_str = "**" + desc_str
            print_str = "{} {}".format(agname, desc_str)
        elif self.verbose > 2:
            desc_str = "* " + desc_str
            print_str = "{} {}".format(agname, desc_str)
        else:
            print_str = ""
            desc_str = "  " + desc_str

        return print_str, desc_str, in_var_str


class SeverityAg(Agent):
    action_str = ...  # type string
    status_record = ...  # type ra.Status

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_str = None
        self.status_record = self.owner.Status()
        self.status_record.less_severity_errors = [["not processed"]]
        self.status_record.max_severity = 10000
        self.status_record.max_severity_errors = [["not processed"]]
        self.status_record.no_severity_status = [["not processed"]]


def prep1(ddict, cfg_motor_props=None, eprefix=None):
    if cfg_motor_props:

        for _ma in cfg_motor_props:
            for _ag in ddict:
                # setup motor PV'a (!!!) hardcoding
                if "dev_prefix" in ddict[_ag]:
                    _pv = ddict[_ag]["dev_prefix"]
                    if _pv == _ma:  # there is additional config attributes for this pv
                        ddict[_ag].update(cfg_motor_props[_ma])

    for _ag in ddict:
        for _fd in ddict[_ag]:
            _val = ddict[_ag][_fd]
            if isinstance(_val, str):
                if _val[0:7] == "default":
                    ddict[_ag][_fd] = eval(_val)
                if (_fd == "dev_prefix") and _val[0] == ":":  # this is a PV
                    ddict[_ag][_fd] = eprefix + _val

    for _ag in ddict:
        if ("dev_prefix" in ddict[_ag]) and ("pvf_list" in ddict[_ag]):
            dev_prefix = ddict[_ag]["dev_prefix"]
            _pvs_by_name = ddict[_ag]["pvf_list"]

            for _pvf in _pvs_by_name:
                _pvfPV = PV(
                    dev_prefix + _pvf, verbose=False
                )  # , callback=handle_update)
                pvf = _pvf
                ddict[_ag].update({pvf: _pvfPV})

        # also, add layer to dictionary to sort based on layer
        ddict[_ag].update({"layer": ddict[_ag]["agent"].layer})


def inference(sorted_ag_list, ag_states, debug=False):
    # cycle only once, based on dependency order

    # logger = logger_debug if debug else logger_default
    polls_var_list = []

    ra_commands = set([])
    _this_cycle_has_print = False
    ag_states[StateNames.Valid] = 0
    ag_states[StateNames.Invalid] = 0
    for agname in sorted_ag_list:
        agent = sorted_ag_list[agname]["agent"]  # type: Agent
        # install a copy of agents list on each agent ONCE
        if not agent.agent_list:
            agent.agent_list = sorted_ag_list
        # only the first minor cycle counts as a major cycle.
        status, return_message = agent._in_proc()
        (print_str, desc_str, in_var_str) = agent.annotate()

        if str(return_message).startswith("RA_"):
            # this is a RA command:
            ra_commands.add(return_message)

        if agent.verbose > 0:
            polls_var_list.append(dict(name=agname, description=desc_str))

        ag_states[status[0]] += 1
        sorted_ag_list[agname].update({"Status": status})

        sorted_ag_list[agname].update({"var_str": in_var_str})

    return _this_cycle_has_print, ra_commands, polls_var_list


def action(sorted_ag_list, ag_states, debug=False):

    logger = logger_debug if debug else logger_default

    _this_cycle_has_print = False

    ra_commands = set([])

    for agname in sorted_ag_list:
        agent = sorted_ag_list[agname]["agent"]  # type: Agent
        status, return_message = agent._out_proc()
        (print_str, desc_str, in_var_str) = agent.annotate()

        if str(return_message).startswith("RA_"):
            # this is a RA command:
            ra_commands.add(return_message)

        ag_states[status[1]] += 1
        sorted_ag_list[agname].update({"Status": status})

        if len(print_str):
            if debug:
                logger.debug(print_str)
                _this_cycle_has_print = True

    return _this_cycle_has_print, ra_commands


def compile_dependencies(_agents_list, script_globals):

    print("\n\n\nCompiling dependencies pass {}".format(1), end="...\n \n")
    for _this_ag in _agents_list:
        _this_ag_obj = _this_ag[1]  # type: Agent
        _this_ag_fullname = _this_ag_obj.name  # type: str
        if not (pythonise_ag_name(_this_ag[0]) == _this_ag_fullname):
            print(
                myEsc.ERROR
                + "names mismatch!!! {} vs {}".format(
                    pythonise_ag_name(_this_ag[0]), _this_ag_fullname
                ),
                end=myEsc.END + "\n",
            )
            exit(1)
            continue

        print("{}".format(_this_ag_fullname), end=myEsc.END + "\n")
        for method_name in method_names:
            if not hasattr(_this_ag_obj, method_name):
                continue

            fn = getattr(_this_ag_obj, method_name)
            if fn is None:
                continue

            source_code = inspect.getsource(fn)

            # exclude method name
            source_code = re.sub("def .*:", "", source_code)
            # exclude references in help texts
            source_code = re.sub('""".*"""', "", source_code)
            # excude what comes before lambda !!
            source_code = re.sub(r".*lambda\s+ag_self\s*:", "", source_code)

            # ag_rx = r"[\w.]+_ag"
            # look for the push dependencies
            for push_method_name in push_method_names + [""]:
                ag_rx = r"[\w.]+_ag"
                if len(push_method_name) > 0:
                    ag_rx = ag_rx + "(?=." + push_method_name + r"\()"
                else:
                    ag_rx = ag_rx + "(?=\W)"

                ag_rx = "(" + ag_rx + ")"
                dum = re.findall(ag_rx, source_code)

                if not dum:
                    continue

                # resolve ag_owner and ag_self first to the full name of the agent...
                # these codewords are used when agent methods are bound to devices,
                # so self resolves to the owner device instead of the agent.
                # proper solution is to assert aht self resloves to...but that would be too hard
                # for now... I am adding another convention which works in any case:
                # refer to agent seklf as ag_self and to owner device as ag_owner!
                #

                dum = [
                    re.sub("ag_owner.", _this_ag_obj.owner_name + ".", _dum)
                    for _dum in dum
                ]
                # dum = [re.sub('self.', _this_ag_obj.owner_name + '.', _dum) for _dum in dum]

                dum = [
                    re.sub("ag_self.", _this_ag_obj.name + ".", _dum) for _dum in dum
                ]

                # resolve self. to the full name of the agent...
                dum = [re.sub("self.", _this_ag_obj.name + ".", _dum) for _dum in dum]

                # this would work in g namespace!

                dum = list(map(pythonise_ag_name, dum))
                _depreag_names = []
                for _dum in dum:
                    try:
                        _depreag_names.append(eval(_dum + ".name", script_globals))
                        # _depreag_names = [eval(_dum+'.name', script_globals) for _dum in dum]  # type: List[str]
                    except NameError:
                        # error_message = str(sys.exc_info()[0])
                        print(
                            myEsc.WARNING
                            + "*_ag name without literal declaration (e.g. in comments) - dependency will be ignored -"
                        )

                # remove duplicates
                _depreag_names = list(set(_depreag_names))
                _depreag_list = [
                    (_ag_name, eval(_ag_name, script_globals))
                    for _ag_name in _depreag_names
                ]  # type: List[Tuple[str, Agent]]

                line_str = "{0}\t{1} {2} \t ({3})"

                if push_method_name:
                    dep_str = push_method_name + " ->"
                    if not method_name.startswith("act_"):
                        # err_str = myEsc.WARNING + '"push method" in none act_ method'
                        err_str = myEsc.SILENT_WARNING
                        # but ignore it
                        # exit(1)
                    else:
                        err_str = ""
                    _this_ag_obj.depend_ags.update(set(_depreag_list))
                    # now push this agent to precedents list of the dependents as well.
                    # at a very low cost, each agent will have both its deps and pres listed.
                    for _depreag in _depreag_list:
                        _depreag_obj = _depreag[1]
                        _depreag_obj.preced_ags.add(_this_ag)
                else:
                    dep_str = "reference" + " <-"

                    if not method_name.startswith("poll_in"[0:3]):
                        # err_str = myEsc.WARNING + 'reference in an action method:' + '\n'
                        err_str = myEsc.SILENT_WARNING
                    else:
                        err_str = ""
                        _this_ag_obj.infer_ags.update(set(_depreag_list))

                    _this_ag_obj.preced_ags.update(set(_depreag_list))
                    for _depreag in _depreag_list:
                        _depreag_obj = _depreag[1]
                        _depreag_obj.depend_ags.add(_this_ag)
                if len(_depreag_names) > 0:
                    print(
                        line_str.format(err_str, dep_str, _depreag_names, method_name),
                        end=myEsc.END + "\n",
                    )
                else:
                    pass

    # clean up duplicates listed under agents
    print("\n----------------\n\n", "Compiling dependencies pass 2", end="...\n \n")

    os.makedirs(excel_out_path, exist_ok=True)
    f = open(os.path.join(excel_out_path, excel_out_file_name), "w+")
    for _this_ag in _agents_list:
        _this_ag_obj = _this_ag[1]  # type: assert isinstance(Agent, object)
        _this_ag_fullname = _this_ag_obj.name

        print(_this_ag_fullname, end="\n")

        # _this_ag_obj.depend_ags = cleanup_ag_list(_this_ag_obj.depend_ags)
        _ag_full_names = [_el[1].name for _el in _this_ag_obj.depend_ags]
        if len(_ag_full_names) > 0:
            print("", end="\td<-")
            print(_ag_full_names)

        _this_ag_obj.preced_ags = _this_ag_obj.preced_ags - _this_ag_obj.infer_ags
        # _this_ag_obj.preced_ags = cleanup_ag_list(_this_ag_obj.preced_ags)
        _ag_full_names = [_el[1].name for _el in _this_ag_obj.preced_ags]
        if len(_ag_full_names) > 0:
            print("", end="\tp->")
            print(_ag_full_names)

        # _this_ag_obj.infer_ags = cleanup_ag_list(_this_ag_obj.infer_ags)
        _ag_full_names = [_el[1].name for _el in _this_ag_obj.infer_ags]
        if len(_ag_full_names) > 0:
            print("", end="\ti->")
            print(_ag_full_names)

        # excel DModel output: infer dependency is saved to file.
        if len(_ag_full_names) == 0:
            infer_str = ""
            input_str = "0"
        elif len(_ag_full_names) == 1:
            infer_str = "= " + excelise_ag_name(_ag_full_names[0])
            input_str = ""
        else:
            infer_str = "= " + functools.reduce(
                lambda a, b: excelise_ag_name(a) + " + " + excelise_ag_name(b),
                _ag_full_names,
            )
            input_str = ""
        print(
            "{}\t{}\t{}".format(
                excelise_ag_name(_this_ag_fullname), infer_str, input_str
            ),
            file=f,
        )

        print()
    f.close()

    print(
        "\n----------------\n\n",
        "Compiling dependencies pass 3: workout dependency levels",
        end="...\n \n",
    )

    lc = 0
    lc_max = len(_agents_list)
    layer_updated = True
    while layer_updated and lc < lc_max:
        lc += 1
        layer_updated = False
        for _this_ag in _agents_list:
            _this_ag_obj = _this_ag[1]  # type: assert isinstance(Agent, object)
            _this_ag_fullname = _this_ag_obj.name

            if _this_ag_obj.layer is None:
                _this_ag_obj.layer = 0

            for _this_ag_infers in _this_ag_obj.infer_ags:
                pre_layer = _this_ag_infers[1].layer if _this_ag_infers[1].layer else 0
                if _this_ag_obj.layer < pre_layer + 1:
                    layer_updated = True
                    _this_ag_obj.layer = pre_layer + 1
                    print("", end=".")

    if layer_updated:
        raise RuntimeError(
            "Failed to compile dependency.\nMax iteration reached while layer stats is not complete.\nPossible circular dependency."
        )
    else:
        print(
            "\n",
            myEsc.SUCCESS + "\n ========================\n",
            "Dependency map compiled",
            end=".\n ======================== \n\n\n" + myEsc.END,
        )


def compile_n_install(initial_dict_of_agents, script_globals, eprefix=None):
    # -- FIND agents

    print("Compiling: looking for agents in supplied framework...")

    device_agent_list = []
    main_globals = script_globals.values()
    main_globals_list = list(main_globals)[:]
    # now add agents defined at level 1 (not under devices)
    for _global in main_globals_list:
        if hasattr(_global, "dmAgentType"):

            _global_name = retrieve_name_in_globals(_global, script_globals)

            # this is an agent, so all of its references SHOULD end with _ag
            if (_global_name.endswith("_ag")) and ("__" not in _global_name):
                _global_agent = [["global", (_global_name, _global)]]
                device_agent_list.extend(_global_agent)
            else:
                raise RuntimeError(
                    f'Agent is referenced with a non-qualified name: "{_global_name}"'
                )
    main_globals_devices = list(
        filter(lambda a: hasattr(a, "dmDeviceType"), main_globals_list)
    )

    # now install agents under devices
    # There might be duplicate copies
    # of agents, hooked on other agents or devices.
    # filter agents which doesn't have the name tag of "_ag".

    device_dict = {}
    for _device in main_globals_devices:
        _device_name = retrieve_name_in_globals(_device, script_globals)

        device_dict.update({_device_name: _device})

        _members = inspect.getmembers(_device)
        _device_agents = [
            [[_device_name, _device], _member]
            for _member in _members
            if hasattr(_member[1], "dmAgentType") and str(_member[0]).endswith("_ag")
        ]
        device_agent_list.extend(_device_agents)

    print(
        "{} devices found. Saving device configurations. May take a littel while... ".format(
            len(device_dict)
        )
    )

    save_device_configs(device_dict)

    _dupls = [
        agent for agent in device_agent_list if not str(agent[1][0]).endswith("_ag")
    ]  # type: List[ra.Agent]

    if _dupls != []:
        print(
            myEsc.ERROR,
            "Duplicate agents defined: {}".format(_dupls),
            end=myEsc.END + " ",
        )
        exit(1)

    agents_list = []

    # INSTALL agents in initial_dict_of_agents
    for dev_ag in device_agent_list:

        _agName = dev_ag[1][0]
        _agent = dev_ag[1][1]

        _devName = dev_ag[0][0] + "__"
        _device = dev_ag[0][1]

        # if agent name does not include its device as a prefix
        if _devName not in _agName:
            _agName = _devName + _agName

        print(_agName, "... ", end="")

        # see if this is a new ag
        if not (_agent in [_ag[1] for _ag in agents_list]):

            if not (_agName in initial_dict_of_agents):
                initial_dict_of_agents.update({_agName: {}})

                _initial_name = _agent.name

                if _initial_name != pythonise_ag_name(_agName):
                    # _agent.name = pythonise_ag_name(_agName)
                    if _initial_name is not None:
                        # print('"{1}" changed to "{0}". '.format(pythonise_ag_name(_agName),  _initial_name)+'\t.\t')
                        print("name set", end="\t.\t")
                    else:
                        print("name verified", end="\t.\t")
                    _agent.name = pythonise_ag_name(_agName)

                print("key added", end="\t.\t")
            else:
                print("key exists", end="\t.\t")

            agents_list.append((_agName, _agent))
            initial_dict_of_agents[_agName].update({"agent": _agent})
            print("object installed", end=".\n")

        else:
            # for duplicated items...
            # put the duplicated name(s) in a list? or do nothing?
            print("object exists", end=".\n")

    # inference engine initial_dict_of_agents size is fixed from this point on
    n = len(initial_dict_of_agents)

    if n != len(agents_list):
        print(
            myEsc.ERROR,
            "WRONG number of agents {} vs {}".format(n, len(agents_list)),
            end=myEsc.END + " ",
        )
        exit(1)
    else:
        print(
            myEsc.SUCCESS,
            " {} agents in initial_dict_of_agents and agent_list".format(n),
            end=myEsc.END + "\n-----------------\n",
        )

    compile_dependencies(agents_list, script_globals)

    # configure items using input files ...
    prep1(initial_dict_of_agents, eprefix=eprefix)

    agents_sorted_by_layer = OrderedDict(
        sorted(initial_dict_of_agents.items(), key=lambda ag: ag[1]["layer"])
    )  # type: OrderedDict[str, dict]

    print("Agents listed by layer:")
    for _ag in agents_sorted_by_layer:
        print("layer {} - {}".format(agents_sorted_by_layer[_ag]["layer"], _ag))

    return agents_sorted_by_layer


def save_device_configs(device_dict):

    # now save the config

    for device_name in device_dict:
        master_config_filename = os.path.join(
            output_dir, device_name + "_master_config.yml"
        )
        device_config_filename = os.path.join(
            output_dir, device_name + "device_config.yml"
        )
        device = device_dict[device_name]
        assert isinstance(device, Device)

        with open(master_config_filename, "w+") as outfile:
            ym.dump(device.master_config, outfile, default_flow_style=False)
            outfile.close()

        device.device_config = {
            key: device.pv_by_name[key].value for key in device.pv_by_name
        }

        with open(device_config_filename, "w+") as outfile:
            ym.dump(device.device_config, outfile, default_flow_style=False)
            outfile.close()

    return


def process_ra_command(ra_commands: list):

    if "RA_TERMINATE" in ra_commands:
        print("Terminating immediately...")
        exit(3)

    if "RA_QUIT" in ra_commands:
        print("Will quit after processing...")
        break_ra_loop = True
        return not break_ra_loop


def process_loop(agents_sorted_by_layer, n_loop=1000000, cycle_period=0.5, debug=False):

    i = 0
    all_ra_commands = set([])
    time_0 = timer()
    next_infer_time = time_0 + cycle_period
    # process loop
    print("\n\n\nProcess loop is running...")

    f = open(os.path.join(html_out_path, html_out_filename), "w")

    while i < n_loop and "RA_QUIT" not in all_ra_commands:
        i += 1
        # this will skip the past samples and prevents fast samples in case of
        # holding
        while next_infer_time < timer():
            next_infer_time += cycle_period
        next_act_time = next_infer_time + cycle_period / 5

        state_record = {
            StateNames.Invalid: 0,
            StateNames.Idle: 0,
            StateNames.Armed: 0,
            StateNames.Done: 0,
            StateNames.Inhibited: 0,
        }

        while timer() < next_infer_time:
            time.sleep(0.02)

        run_time = timer() - time_0

        # INFERENCE: loop through the agents, poll.force vals and update GState but NOT the actions
        poll_print, ra_commands, polls_var_list = inference(
            agents_sorted_by_layer, state_record, debug=debug
        )
        all_ra_commands.update(ra_commands)
        process_ra_command(all_ra_commands)

        table = VarsTable(polls_var_list)
        # this print is equivalent of what logger_debug would do wit additional stdout handler added
        # print_list = [item['name']+' '+item['description'] for item in polls_var_list if item['description'].startswith('*')]
        # print(*print_list, sep='\n')
        f = open(os.path.join(html_out_path, html_out_filename), "w+")
        f.write(table.__html__())
        f.close()

        while timer() < next_act_time:
            time.sleep(0.02)
        # ACTIONS: loop through the agents,
        act_print, ra_commands = action(
            agents_sorted_by_layer, state_record, debug=debug
        )
        all_ra_commands.update(ra_commands)
        process_ra_command(all_ra_commands)

        if poll_print or act_print:
            if debug:
                print("states = {}".format(state_record))
            print(
                "end of cycle {}, {:.3f}s".format(i, run_time),
                end="\n ====================================== \n",
            )

    print("Reactive Agent process loop terminated. \n ==============================\n")


# additional useful functions

# Simple PV mapping agents:
def get_in_pv(self: Agent):
    _in = self.in_PV.value
    return _in, ""


def put_out_pv(self: Agent):
    # mind this: pvc will not be invoked for process every cycle.
    if self.out_PV.value != self.poll.Var:
        self.out_PV.put(self.poll.Var)
    return StateLogics.Done, ""


def reset_out_pv(self: Agent):
    self.out_PV.value = 0
    return StateLogics.Idle, ""


# TODO clean this mess: replace tuple with struct(!)


stat_name_index = 0
stat_severity_index = 1
stat_actionpv_index = 2
stat_inverted_index = 3


def bit_status(_r: int, ref_list: list):

    _stat_list = []
    i = -1
    while i < 15:
        i += 1

        if i in ref_list:

            if len(ref_list[i]) > stat_inverted_index:
                normal_value = ref_list[i][stat_inverted_index]
            else:
                normal_value = 0

            if (_r & 1) ^ normal_value:
                _stat_list.append(ref_list[i])
        elif _r & 1:
            _stat_list.append(["bit_{}".format(i)])
        _r = _r >> 1
    return _stat_list


def bit_stat(ag: Agent):
    _r = int(ag.owner.pv_by_name[ag.stat_pv].value)

    _stat_list = []
    i = -1
    while i < 15:
        i += 1

        if i in ag.ref_list:

            if len(ag.ref_list[i]) > stat_inverted_index:
                normal_value = ag.ref_list[i][stat_inverted_index]
            else:
                normal_value = 0

            if (_r & 1) ^ normal_value:
                _stat_list.append(ag.ref_list[i])
        elif _r & 1:
            _stat_list.append(["bit_{}".format(i)])
        _r = _r >> 1
    return _stat_list, ""


def status_poi(self: SeverityAg):
    _all_status_list = []
    for stat_pv in self.owner.status_ref_dict:

        pv = self.owner.get_pv_by_name(stat_pv)
        status_ref_dict = self.owner.status_ref_dict[stat_pv]
        if pv:
            _r = int(pv.value)
            if type(list(status_ref_dict.keys())[0]) is int:
                # int type index indicates bit number
                _all_status_list += bit_status(_r, status_ref_dict)
            else:
                # float index indicates whole number match
                for ref_val in status_ref_dict:
                    _stat = status_ref_dict[ref_val]
                    inverted_logic = (
                        _stat[stat_inverted_index]
                        if len(_stat) > stat_inverted_index
                        else 0
                    )
                    if (inverted_logic == 1) ^ (_r == ref_val):
                        _all_status_list.append(_stat)
                    else:
                        pass

        else:
            _all_status_list += [[stat_pv + " not installed", 2000]]

    return _all_status_list, ""


def severity_poi(self: SeverityAg):

    _max_severity = 0
    _max_severity_errors = []
    _less_severity_errors = []
    _no_severity_status = []
    for _stat in self.owner.status_ag.poll.Var:
        if len(_stat) > stat_severity_index:
            if len(_stat) > stat_actionpv_index:
                reset_pv = _stat[stat_actionpv_index]
            else:
                reset_pv = None

            if _stat[stat_severity_index] > _max_severity:
                _max_severity = _stat[stat_severity_index]

                _max_severity_errors = [
                    [_stat[stat_name_index], _max_severity, reset_pv]
                ]
            elif _stat[stat_severity_index] == _max_severity:
                _max_severity_errors.append(
                    [_stat[stat_name_index], _max_severity, reset_pv]
                )
            else:
                _less_severity_errors.append(
                    [_stat[stat_name_index], _stat[stat_severity_index], reset_pv]
                )
        else:
            _no_severity_status.append(_stat)

    self.status_record.max_severity = _max_severity
    self.status_record.max_severity_errors = _max_severity_errors
    self.status_record.less_severity_errors = _less_severity_errors
    self.status_record.no_severity_status = _no_severity_status
    return_message = ""

    return _max_severity, return_message


def severity_aov(self: SeverityAg):
    return_message = ""
    """
    here we define the condition for invoking an automatic severity reduction action.
    if severity is risen, then there will be no action unless externally invoked by invalidating severity agent
    Each level of severity should invoke its action only once
    """

    # there is a severity worth action
    if self.poll.Var > 0:

        # there is a stable severity worth actioning
        if self.poll.IsStable and self.poll.Var > 0:

            # last CHANGE of severity has been a decrease
            if self.poll.Diff and (self.poll.Diff < 0):

                """ 
                severity has been constant for the past n cycles, but decreased before that
                it is persistent, there is something to recover from!
                in order to prevent re-entry... we can either reset the Diff by in-forcing a value slightly
                higher than the present one, or add this useful functionality to Agent
                to be able to reset Diff to 0 as if a new era has began! but this
                have potentially deadly side effect... think carefully... maybe we can add iDelta which holds
                the last cycle change... that is useful but not for this purpose because we are already stable
                here meaning Delta is zero! ...

                best is to force a lower severity to flag one try!
                """

                self.poll.force(
                    for_cycles=1,
                    forced_var=self.poll.Var - self.owner.severity_try_decrease_value,
                )

                _fault_str = (
                    "device severity: "
                    + "has decreased to "
                    + self.status_record.max_severity_errors[0][0]
                )
                _stat_rec = self.status_record.max_severity_errors[0]

                if len(_stat_rec) > stat_actionpv_index:
                    self.action_str = _stat_rec[stat_actionpv_index]

                if self.action_str is not None:
                    return StateLogics.Armed, self.action_str
            else:
                return_message = "device severity: " + "severity not decreasing"
        else:
            return_message = "device severity: " + "changed..."
    return StateLogics.Idle, return_message


if __name__ == "__main__":
    pass
