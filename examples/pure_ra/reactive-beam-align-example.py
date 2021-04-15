#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/wrasc/examples/reactive-beam-align-example.py $
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

import numpy as np
from wrasc import reactive_agent as ra
from wrasc import reactive_positioner as rpos
from wrasc.reactive_utils import myEsc, clip_abs


# configuration info
default_eprefix = 'WORKSHOP01'

# Intialise DModel agents from file
predefined_agents = {}

# DEFINE DModel.agents from predefined_agents
for dev_ag in predefined_agents:
    execStr = dev_ag + "= ra.Agent(first_name='" + ra.pythonise_ag_name(dev_ag) + "', eprefix=default_eprefix)"
    exec(execStr)


# SAX Example:
"""
User finds position to cut the beam in half by the sample
Height Scan to find halfway by 20u
Angle course and fine scan to maximise the count


SAX has this implemented as an outer sequence of bluesky plans
"""


# ultimately, user is asked to set the height
# assuming: there is a PV which returns COUNTS, which is our ultimate goal variable:
# ---------------


# motors

height_mot = rpos.Motor(device_name='height_mot',
                       eprefix=default_eprefix, dev_prefix=':MOT3',
                       pvs_by_name=rpos.default_motor_fields,
                       unit='mm')

height_mot.severity_ag.poll.force(1000, for_cycles=1)

angle_mot = rpos.Motor(device_name='angle_mot',
                      eprefix=default_eprefix, dev_prefix=':MOT4',
                      pvs_by_name=rpos.default_motor_fields,
                      unit='mrad')


# simulator

def beam_detector_sim(self: ra.Agent):
    """This agent simulates the beam residue detected at the detector_ag, using a virtual motor"""
    # simulated

    beam_h = 0
    beam_top = beam_h + self.beam_radius
    beam_bot = beam_h - self.beam_radius

    stage_h = height_mot.rbv_ag.poll.Var + self.sample_length * abs(np.sin(angle_mot.rbv_ag.poll.Var/1000))

    beam_area = np.pi * self.beam_radius**2
    cut_h = stage_h - self.sample_h_offset

    if cut_h <= beam_bot:
        beam_cut_ratio = 0
    elif cut_h >= beam_top:
        beam_cut_ratio = 1
    elif cut_h >= beam_h:
        alpha = np.arccos(cut_h/self.beam_radius)
        transmission_area = alpha * self.beam_radius ** 2 - cut_h * self.beam_radius * np.sin(alpha)
        beam_cut_ratio = 1 - transmission_area/beam_area
    elif cut_h <= beam_h:
        alpha = np.arccos(cut_h/self.beam_radius)
        transmission_area = alpha * self.beam_radius ** 2 - cut_h * self.beam_radius * np.sin(alpha)
        beam_cut_ratio = 1 - transmission_area/beam_area
    else:
        raise ValueError('did not expect this!!!')

    _in = 1 - beam_cut_ratio
    self.out_PV.value = 1 - beam_cut_ratio

    self.poll.Err = 0.002

    return _in, ''


beam_detector_ag = ra.Agent(first_name='beam_detector_ag', verbose=1,
                            poll_in=beam_detector_sim,
                            unit='f.s.')
beam_detector_ag.install_pvs(eprefix=default_eprefix, dev_prefix='', outpvname=':DM:RESIDUE', inpvname=None)
beam_detector_ag.sample_length = 100 # mm
beam_detector_ag.beam_radius = 0.1 # mm
beam_detector_ag.sample_h_offset = 0.0 # mm


def gen_cost_evaluate(self: ra.Agent):
    """

    :type self: ra.Agent
    """

    v = self.detector_ag.poll.Var
    r = abs(self.targetVal - v)

    return r, ''


def gen_cost_invalid(self: ra.Agent):
    # useless code, just as an example of act_on_invalid
    v = self.detector_ag.poll.Var
    return v, 'I DO NOT KNOW...'


angle_cost_ag = ra.Agent(first_name='angle_cost_ag',
                         poll_in=gen_cost_evaluate,
                         act_on_invalid=gen_cost_invalid,
                         unit='',
                         verbose=0
                         )

angle_cost_ag.detector_ag = beam_detector_ag
angle_cost_ag.targetVal = 1

height_cost_ag = ra.Agent(first_name='height_cost_ag',
                          poll_in=gen_cost_evaluate,
                          act_on_invalid=gen_cost_invalid,
                          unit='',
                          verbose=0)

height_cost_ag.detector_ag = beam_detector_ag
height_cost_ag.targetVal = 0.5


# defining a gen_scan_ag to monitor and capture minimum
def gen_scan_observe(self: ra.Agent):
    """ALWAYS set default return and message
    :param self: ra.Agent
    :return:
    """
    r = self.poll.Var
    detector_lc = self.detector_ag  # type: ra.Agent
    cost_lc = self.cost_ag  # type: ra.Agent
    motor_ = self.positioner  # type: rpos.Motor
    return_message = ''
    detector_value = self.detector_ag.poll.Var
    cost_value = cost_lc.poll.Var

    if detector_value is not None:
        if self.poll.Var is None:
            return_message = 'initiated'
            self.opt_found_count = 0
            self.scan_cost_change_time = ra.timer()
            self.scan_cost_decreasing = False
            self.scan_cost_is_flat = True
            r = {'optVal': detector_value
                 , 'optPos': self.positioner.rbv_ag.poll.Var
                 , 'optPosErrb': self.positioner.rbv_err_ag.poll.Var
                 , 'optCost': cost_value
                 }
            self.out_PV.value = detector_value
        else:
            r = self.poll.Var.copy()
            r.update({'costDelta': cost_lc.in_delta()[0]})

            if r['costDelta'] == 0:
                if not self.scan_cost_is_flat:
                    self.opt_found_count = 0
                    self.scan_cost_is_flat = True
                else:
                    self.opt_found_count += 1
            else:
                self.scan_cost_is_flat = False
                if r['costDelta'] > 0:
                    if self.scan_cost_decreasing:
                        self.opt_found_count = 0
                        self.scan_cost_decreasing = False
                    else:
                        self.opt_found_count += 1

                elif r['costDelta'] < 0:
                    if not self.scan_cost_decreasing:
                        self.opt_found_count = 0
                        self.scan_cost_decreasing = True
                    else:
                        self.opt_found_count += 1

            if cost_value < self.poll.Var['optCost']:
                return_message = 'new optimum found'
                r.update({'optVal': detector_value
                          , 'optPos': self.positioner.rbv_ag.poll.Var
                          , 'optCost': cost_value
                          , 'optPosErrb': self.positioner.rbv_err_ag.poll.Var
                          })
                # output the valid minima onto an external PV, purely for display reasons
                self.scan_cost_change_time = ra.timer()
                self.out_PV.value = detector_value

    return r, return_message


# decide when and how the next scan goes
def gen_scan_decide(self: ra.Agent):
    """ there is a valid minima found... do nothing if it is still changing
    but if it is not changing, then try to make a tweak towards the minimum
    :param self: ra.Agent
    :return: """

    if (self.poll.Var['optPosErrb'] is None) or (self.positioner.pos_prec_ag.poll.Var is None):
        return ra.StateLogics.Idle, "can't search without defined positioning error bands"
    else:
        actual_pos_errb = abs(self.poll.Var['optPosErrb'])

    # check if optimum is found within tolerance
    if abs(self.poll.Var['optCost']) < self.detector_ag.poll.Err:
        if actual_pos_errb < self.positioner.pos_prec_ag.poll.Var:
            self.positioner.move_to_ag.poll.force([self.poll.Var['optPos'], 0.05])
            self.act.hold(for_cycles=-1, reset_var=True)
            return ra.StateLogics.Done, 'optimum found : moving and permanently act.holding'
        else:
            pass

    # CASE 2, timeout
    lapsed_time = ra.timer() - self.scan_cost_change_time
    if (self.time_out is not None) and lapsed_time > self.time_out:
        self.positioner.move_to_ag.poll.force([self.poll.Var['optPos'], 0.05])
        self.act.hold(for_cycles=-1, reset_var=True)
        return ra.StateLogics.Idle, 'Timed out: moving and permanently act.holding'

    lapsed_time_str = '{:3.3f}s/{:3.3f}s'.format(lapsed_time, self.time_out)

    # case 3: monitor the possible changes
    if self.opt_found_count < 1:
        retuple = ra.StateLogics.Idle, 'no change'
    else:
        if self.scan_cost_is_flat:
            if self.scan_cost_decreasing:
                retuple = ra.StateLogics.Idle, 'at max'
            else:
                retuple = ra.StateLogics.Idle, 'at min'
        elif self.scan_cost_decreasing:
            retuple = ra.StateLogics.Idle, 'converging... '
        else:
            self.positioner.pvs_by_name_PVs['.STOP'].value = 1
            retuple = ra.StateLogics.Armed, 'turnaround'

    return retuple[0], lapsed_time_str + ' ' + retuple[1]


# activate the scan move
def gen_scan_move(self: ra.Agent):
    """
    When it comnes here, there is a valid minimum which has not been changing for at least one major cycle.
    A stop is sent to the angle_motor, so it should be ready now to move the next step
    :param self: ra.Agent
    :return:
    """

    if not self.positioner.pvs_by_name_PVs['.DMOV'].value > 0:
        return ra.StateLogics.Armed, 'Waiting for positioner to stop'

    max_move_time = self.time_out/2 #sec
    min_move_time = self.positioner.max_sync_time_ag.poll.Var
    min_move = min(0.002, self.positioner.pos_prec_ag.poll.Var)
    max_move = 10

    # How far past the optimal point?
    pos_diff = self.poll.Var['optPos'] - self.positioner.rbv_ag.poll.Var
    pos_diff = clip_abs(pos_diff, min_move, max_move)

    # what is the precision (confidence) of this position info
    this_precision = min(abs(pos_diff)/2, self.poll.Var['optPosErrb']/2)

    error_margin = abs(abs(self.poll.Var['optPosErrb']) / pos_diff)
    this_twv = pos_diff * (1 + error_margin) * 2
    vel_abs_max = abs(this_twv / min_move_time) / 4
    vel_abs_min = abs(this_twv / max_move_time)

    next_vel = this_precision / self.positioner.max_sync_time_ag.poll.Var / 4
    next_vel = clip_abs(next_vel, vel_abs_min, vel_abs_max)

    self.this_twv = this_twv
    self.this_vel = next_vel

    self.positioner.tweak_ag.poll.force([self.this_twv, self.this_vel])

    self.act.hold(for_cycles=2)

    return ra.StateLogics.Idle, 'started a search move...'


angle_scan_ag = ra.Agent(first_name='angle_scan_ag',
                         poll_in=gen_scan_observe,
                         act_on_valid=gen_scan_decide,
                         act_on_armed=gen_scan_move,
                         unit=beam_detector_ag.unit,
                         time_out=20,
                         verbose=2
                         )


angle_scan_ag.positioner = angle_mot
angle_scan_ag.detector_ag = beam_detector_ag
angle_scan_ag.cost_ag = angle_cost_ag

angle_scan_ag.install_pvs(eprefix=default_eprefix, outpvname=':DM:OPT_SCATTER')
angle_scan_ag.act.hold(for_cycles=-1, reset_var=True)


height_scan_ag = ra.Agent(first_name='height_scan_ag',
                          poll_in=gen_scan_observe,
                          act_on_valid=gen_scan_decide,
                          act_on_armed=gen_scan_move,
                          unit=beam_detector_ag.unit,
                          time_out=20,
                          verbose=2
                          )

height_scan_ag.positioner = height_mot
height_scan_ag.detector_ag = beam_detector_ag
height_scan_ag.cost_ag = height_cost_ag
height_scan_ag.install_pvs(eprefix=default_eprefix, outpvname=':DM:OPT_RESIDUE')
height_scan_ag.act.hold(for_cycles=-1, reset_var=True)


# Now we need a trigger to turn the scans on

def gen_trigger_infer(self: ra.Agent):
    trigger = (self.in_PV.value == 0)
    return trigger, ''


def gen_trigger_trigger(self: ra.Agent):

    if self.poll.Var:
        self.in_PV.value = 1
        self.receiver_ag.poll.force(forced_var=None)
        return ra.StateLogics.Armed, 'triggered'
    else:
        return ra.StateLogics.Idle, 'standby'


def gen_trigger_unhold(self: ra.Agent):
    self.receiver_ag.act.unhold()
    self.receiver_ag.opt_found_count = 0
    return ra.StateLogics.Idle, 'standby'


angle_scan_trigger_ag = ra.Agent(first_name='angle_scan_trigger_ag', poll_in=gen_trigger_infer,
                                 act_on_valid=gen_trigger_trigger,
                                 act_on_armed=gen_trigger_unhold)
angle_scan_trigger_ag.in_PV = angle_scan_ag.positioner.pv_by_name[':SAVE_USER']
angle_scan_trigger_ag.receiver_ag = angle_scan_ag


height_scan_trigger_ag = ra.Agent(first_name='height_scan_trigger_ag'
                                  , poll_in=gen_trigger_infer
                                  , act_on_valid=gen_trigger_trigger
                                  , act_on_armed=gen_trigger_unhold
                                  )
height_scan_trigger_ag.in_PV = height_scan_ag.positioner.pv_by_name[':SAVE_USER']
height_scan_trigger_ag.receiver_ag = height_scan_ag


# and a mechanism to turn a scan off


def gen_reset_scan(self: ra.Agent):
    return_message = ''

    if self.poll.Var:  # self reference what is the right way to do this ?
        return_message = myEsc.GREEN + ' Uninitialised, resetting the monitor...' + myEsc.END
        # poll.hold the search
        self.owner.scan_ag.poll.hold()
        self.owner.scan_ag.act.hold(for_cycles=-1, reset_var=True)

        return_message += 'done.'

    return True, return_message


angle_mot.can_init_ag.setup(act_on_valid=gen_reset_scan)
angle_mot.scan_ag = angle_scan_ag

height_mot.can_init_ag.setup(act_on_valid=gen_reset_scan)
height_mot.scan_ag = height_scan_ag


# ----------------
# Extra icing

angle_scan_ag.positioner.tweak_ag.set(verbose=0)
height_scan_ag.positioner.tweak_ag.set(verbose=0)

#----
# Testing auto severity
#
angle_mot.severity_ag.poll.force(1000, for_cycles=1)
height_mot.severity_ag.poll.force(1000, for_cycles=1)
# ----------------
# IRRELEVANT syntax examples

example_name_mist_ag = ra.Agent(first_name='mismatch_name')
example_no_name_ag = ra.Agent()
# example_illegal__name_ag = ra.Agent()

# example_illegal_name_a = ra.Agent(first_name='example_illegal_name_a')


# ---------------

# dm module called to compile and install agents
agents_sorted_by_layer = ra.compile_n_install(predefined_agents, globals(), default_eprefix)


# input('press any key to start the process loop...')

# dm module takes control of the process loop
ra.process_loop(agents_sorted_by_layer, n_loop=10000, cycle_period=0.2, debug=False)

# end
