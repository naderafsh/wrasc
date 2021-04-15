#!/usr/bin/env python3
#
# $File: //ASP/Personal/afsharn/wrasc/examples/dynap-set-positions.py $
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


""" A test for my relative programming idea!
"""

from wrasc import reactive_agent as ra
from wrasc import reactive_positioner as rpos

import argparse
from numpy import sqrt, clip
from math import atan

import dynap_ra

import copy

import os

DEBUGGING = True


# DONOT import Agent from reactive_agent!!!!

parser = argparse.ArgumentParser(description='Set positions of DynAp motors on the trajectory.')

parser.add_argument('--default_eprefix', type=str, default='SR08ID01ZORRO', help='default epics prefix')

parser.add_argument('--debug', action='store_true', help='Debug mode', default=DEBUGGING)

parser.add_argument('-v', '--verbose', action='count', default=0)

parser.add_argument('--conti', action='store_true', default=False, \
    help='continue forcing positions - otherwuise: quits after positions are set')

parser.add_argument('--R_r', type=float, default=10, help='Request radius [mm]')

parser.add_argument('--R_m', type=float, default=20, help='Mask radius [mm]')

parser.add_argument('--B_h', type=float, default=0, help='Beam height [mm]')

parser.add_argument('--cycles', type=int, default=10000, help='maximum process cycles')

parser.add_argument('--cycle_period', type=float, default=0.2, help='process cycle period [seconds]')

#os.environ["EPICS_CA_ADDR_LIST"] = '10.244.66.91' #'10.42.19.91'  # '10.244.66.91'
#os.environ["EPICS_CA_AUTO_ADDR_LIST"] = 'NO'

_VERBOSE_ = 2

#global args
args = parser.parse_args()

# configuration info
default_eprefix = args.default_eprefix
R_m = args.R_m
R_r = args.R_r
B_h = args.B_h

print(args)

# Intialise DModel agents from file
predefined_agents = {}

for dev_ag in predefined_agents:
    execStr = dev_ag + "= ra.Agent(first_name='" + ra.pythonise_ag_name(dev_ag) + "', eprefix=default_eprefix)"
    exec(execStr)


"""Dynamic Aperture DynAp
is consisted of two slits of X_Y and a scan Y motor.
CS 4 is defined to drives all of the 5 motors 

The motors need to be moved to a consistent initial position "lock position" before a move is requested, 
to prevent motors stall due to impossible fast initial moves. 

initialise and home the motors, then move them into the correct position, then let the vitual motor move.

"""

dynap01 = dynap_ra.DynAp(eprefix=default_eprefix, dev_prefix=':DYNAP')

dynap01.r_mask_q21_ag.poll.force(R_m)
dynap01.r_req_q20_ag.poll.force(R_r)
dynap01.cs_number_ag.poll.force(4)

# define the motors:
y_sample_mot = rpos.Motor(eprefix=default_eprefix, dev_prefix=':DUMMY_Z',
                          pvs_by_name=rpos.default_motor_fields,
                          unit='mm')
# force lowest severity to DISABLE automated fault recovery.
y_sample_mot.severity_ag.poll.force(0, for_cycles=1)

l_x_mot = rpos.Motor(eprefix=default_eprefix, dev_prefix=':LEFT_Y',
                     pvs_by_name=rpos.default_motor_fields,
                     unit='mm')
# force highest severity to invoke automated fault recovery at start!
l_x_mot.severity_ag.poll.force(1000, for_cycles=1)

l_y_mot = rpos.Motor(eprefix=default_eprefix, dev_prefix=':LEFT_Z',
                     pvs_by_name=rpos.default_motor_fields,
                     unit='mm')
# force highest severity to invoke automated fault recovery at start!
l_y_mot.severity_ag.poll.force(1000, for_cycles=1)

r_x_mot = rpos.Motor(eprefix=default_eprefix, dev_prefix=':RIGHT_Y',
                     pvs_by_name=rpos.default_motor_fields,
                     unit='mm')
# force highest severity to invoke automated fault recovery at start!
r_x_mot.severity_ag.poll.force(1000, for_cycles=1)

r_y_mot = rpos.Motor(eprefix=default_eprefix, dev_prefix=':RIGHT_Z',
                     pvs_by_name=rpos.default_motor_fields,
                     unit='mm')
# force highest severity to invoke automated fault recovery at start!
r_y_mot.severity_ag.poll.force(1000, for_cycles=1)


# define rascan
# micro_rscn = rscn2.Rascan2(eprefix=default_eprefix, dev_prefix=':RSCN')


"""methods"""


def poser_on_traj_in(self: ra.Agent):
    _on_target = False
    self.positioner = self.positioner  # type: rpos.Motor

    _fault_str = None
    if self.positioner.severity_ag.poll.Var > rpos.severity_ready_5:
        _fault_str = 'positioner ' + self.positioner.severity_ag.statrec.max_severity_errors[0][0] \
            if len(self.positioner.severity_ag.statrec.max_severity_errors) > 0 else ''
    elif not self.positioner.severity_ag.poll.IsStable:
        _fault_str = 'positioner ' + 'recovering...'
    elif y_sample_mot.severity_ag.poll.Var > rpos.severity_ready_5 \
            or not self.positioner.severity_ag.poll.IsStable:
        # moving target: target is not known
        _fault_str = 'target is not valid/stable'

    if _fault_str:
        _in = {'on_target': None, 'pos_diff': None, 'moveto_pos': None, 'error': _fault_str}
        return _in, _fault_str

    # Y = clip(y_sample_mot.rbv_ag.poll.Var, -R_r, +R_r)
    Y = y_sample_mot.rbv_ag.poll.Var

    _pos_target = self.kin(Y)
    _pos_diff = self.kin(Y) - self.positioner.rbv_ag.poll.Var
    _on_target = abs(_pos_diff) + abs(self.positioner.rbv_err_ag.poll.Var) < self.positioner.pos_prec_ag.poll.Var*2
    if _on_target:
        _pos_target = None

    _in = {'on_target': _on_target, 'pos_diff': _pos_diff, 'moveto_pos': _pos_target, 'error': 'none'}
    return _in, ''


def decide_to_move(self: ra.Agent):
    if self.poll.Var['moveto_pos'] is not None:
        # need to move if it is permitted
        if self.positioner.pv_by_name['.DMOV'].value == 1:
            return ra.StateLogics.Armed, 'Arming to move'
        else:
            return ra.StateLogics.Idle, 'Not ready to move'
    else:
        # nothing to do
        return ra.StateLogics.Idle, 'on target'


def move_to_trajpos(self: ra.Agent):
    # need to move if it is permitted
    # TODO hardcoded velocity and wait cycles

    if self.poll.Var['moveto_pos'] is not None:
        # need to move if it is permitted
        self.positioner.move_to_ag.poll.force([self.poll.Var['moveto_pos'], 10])
        self.act.hold(for_cycles=10, reset_var=True)

    return ra.StateLogics.Done, 'moving to trajectory position and act.holding for 10 cycles'


# main function definitions
l_x_mot_on_traj_ag = ra.Agent(verbose=_VERBOSE_)
l_x_mot_on_traj_ag.positioner = l_x_mot
l_x_mot_on_traj_ag.reference_pos = y_sample_mot
l_x_mot_on_traj_ag.setup(poll_in=poser_on_traj_in, act_on_valid=decide_to_move, act_on_armed=move_to_trajpos, verbose=_VERBOSE_)

l_y_mot_on_traj_ag = ra.Agent(verbose=_VERBOSE_, poll_in=poser_on_traj_in)
l_y_mot_on_traj_ag.positioner = l_y_mot
l_y_mot_on_traj_ag.reference_pos = l_x_mot_on_traj_ag.reference_pos
l_y_mot_on_traj_ag.setup(poll_in=poser_on_traj_in, act_on_valid=decide_to_move, act_on_armed=move_to_trajpos, verbose=_VERBOSE_)

r_x_mot_on_traj_ag = ra.Agent(verbose=_VERBOSE_)
r_x_mot_on_traj_ag.positioner = r_x_mot
r_x_mot_on_traj_ag.reference_pos = l_x_mot_on_traj_ag.reference_pos
r_x_mot_on_traj_ag.setup(poll_in=poser_on_traj_in, act_on_valid=decide_to_move, act_on_armed=move_to_trajpos, verbose=_VERBOSE_)

r_y_mot_on_traj_ag = ra.Agent(verbose=_VERBOSE_)
r_y_mot_on_traj_ag.positioner = r_y_mot
r_y_mot_on_traj_ag.reference_pos = l_x_mot_on_traj_ag.reference_pos
r_y_mot_on_traj_ag.setup(poll_in=poser_on_traj_in, act_on_valid=decide_to_move, act_on_armed=move_to_trajpos, verbose=_VERBOSE_)

x_over_max = 0

# Y stages margin shall not be less than beam height 
y_over_max = min(B_h/2, 1.4/2+0.5)

# kinematic function definitions
def kin_xy(y_sample: float, R_m, R_r, B_h):

    
    y_eff = y_sample + B_h/2 *(y_sample / R_r)
    y_capped = y_eff

    if y_eff < -R_r:

        x_blade = atan(-R_r - y_eff)/1.5708*x_over_max
    
        if y_capped < -R_r - y_over_max:
            y_capped = -R_r - y_over_max

    else:
        if y_eff > R_r:

            x_blade = atan(y_eff - R_r)/1.5708*x_over_max

            if y_capped > R_r + y_over_max:
                y_capped = R_r + y_over_max
        else:
            # the beam is through the slits
            x_blade = -((R_r-R_m)*sqrt(R_r-y_eff)*sqrt(y_eff+R_r))/R_r
            y_capped = y_capped

    x_of_Y = x_blade
    y_of_Y =  R_m*y_capped/R_r 

    return x_of_Y, y_of_Y


def kin_x(Y: float):
    return kin_xy(Y, R_m, R_r, B_h)[0]


def kin_y(Y: float):
    return kin_xy(Y, R_m, R_r, B_h)[1]

l_x_mot_on_traj_ag.kin = kin_x
l_y_mot_on_traj_ag.kin = kin_y
r_x_mot_on_traj_ag.kin = l_x_mot_on_traj_ag.kin
r_y_mot_on_traj_ag.kin = l_y_mot_on_traj_ag.kin

# Now if all of them are on trajectory then stop process and exit using RA_QUIT


def all_on_traj(self: ra.Agent):
    if \
            l_x_mot_on_traj_ag.poll.VarDebounced['on_target'] \
            and l_y_mot_on_traj_ag.poll.VarDebounced['on_target'] \
            and r_x_mot_on_traj_ag.poll.VarDebounced['on_target'] \
            and r_y_mot_on_traj_ag.poll.VarDebounced['on_target']:

        return True, ''
    else:
        return False, ''


def setup_virt_motor(self: ra.Agent):
    if self.poll.VarDebounced:

        # TODO: before you set the virtual motor to Go: 
        # Make sure the correct CS is chosen 
        # Set this motor's VAL to its RBV if you don't want it to move


        self.scan_spmg.poll.force(3)
        return ra.StateLogics.Armed, self.scan_spmg.outpvname + ' is on Go'
    else:
        if self.scan_spmg.poll.Var != 0:
            self.scan_spmg.poll.force(0)
        return ra.StateLogics.Idle, self.scan_spmg.outpvname + ' is on Stop'


def done_condition(self: ra.Agent):
    is_done = all_on_traj_ag.poll.VarDebounced
    return is_done, ''


def arm_to_quit(self: ra.Agent):
    if self.poll.Var:
        # inform and log, confirm with other agents...
        return ra.StateLogics.Armed, 'quitting...'


def quit_act(self: ra.Agent):

    if self.poll.Var:
        return ra.StateLogics.Done, 'RA_QUIT'
    else:
        return ra.StateLogics.Idle, 'RA_NOT_YET'


all_on_traj_ag = ra.Agent(verbose=_VERBOSE_, poll_in=all_on_traj, act_on_valid=setup_virt_motor)
all_on_traj_ag.scan_spmg = dynap01.scan_spmg_ag

quit_if_all_done_ag = ra.Agent(verbose=_VERBOSE_, poll_in=done_condition, act_on_valid=arm_to_quit, act_on_armed=quit_act)

if args.conti:
    print("won't quit after success")
    quit_if_all_done_ag.poll.hold(for_cycles=-1)


# else:
#     all_on_traj_ag.set(act_on_armed=quit)



""" ra model compiler and process loop"""

# input('press a key or break...')

# dm module called to compile and install agents
agents_sorted_by_layer = ra.compile_n_install(predefined_agents, globals().copy(), default_eprefix)

# input('press any key to start the process loop...')

# dm module takes control of the process loop
ra.process_loop(agents_sorted_by_layer, args.cycles, cycle_period=args.cycle_period, debug=args.debug)
