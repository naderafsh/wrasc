#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/wrasc/examples/xfm-rascan2-indent.py $
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
import argparse
import yaml
import rascan2_ra as rscn2


parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('default_eprefix', metavar='eprefix', type=str, nargs='*', default=['WORKSHOP01'],
                    help='default epics prefix (default: WORKSHOP01)')

parser.add_argument('--debug', metavar='option_debug', type=bool, nargs='*', default=True,
                    help='Debug mode')

#global args
args = parser.parse_args()

# configuration info
default_eprefix = args.default_eprefix[0]
print(default_eprefix)

micro_rscn = rscn2.Rascan2(eprefix=default_eprefix, dev_prefix=':RSCN')

# Intialise DModel agents from file
predefined_agents = {}

for dev_ag in predefined_agents:
    execStr = dev_ag + "= ra.Agent(first_name='" + ra.pythonise_ag_name(dev_ag) + "', eprefix=default_eprefix)"
    exec(execStr)


# XFM Indentation:
"""
Rascan2 accepts runtime indentation to fast axis range. There are two PV's:
D1_INDL_REQ and D1_INDR_REQ (meaning "indent from Left" and "indent from Right" respectively. 
Left and Right as seen on the sample view
These PV's are combined set/readbacks 
Changes apply to the next line

contraints:
- These PV's should be reset to zero when the scan is being compiled,
- The PV's can not be set unless scan is running (hence first line is always complete)

actions:
d2_next_line_ag reads 
    d2_Start 
    d2_Step 
    line_N
    provides:
    Y_line
    
next_indL_ag 
 reads 
    a CSV file of (d2, d1L,d1R) i.e. (Y,X_indent_from_out, X_indent_from_in), 
    d2_next_line_ag    
 sets 
    :D1_INDL_REQ
    :D1_INDR_REQ
    

activator_ag 
 reads
    :DEV_STATE
 activates 
    next_indL_ag 

- 
 
"""


def d2_next_line_in(self: ra.Agent):
    _in = micro_rscn.d2_start_ag.poll.VarDebounced + micro_rscn.d2_step_ag.poll.VarDebounced * (1 + micro_rscn.line_n_ag.poll.VarDebounced)
    return _in, ''


d2_next_line_ag = ra.Agent(poll_in=d2_next_line_in, verbose=2)


def indent_table_in(self: ra.Agent):

    _msg = '\n Reading ' + self.indent_profile_filename + ' ...'
    with open(self.indent_profile_filename, 'r') as fin:
        versiscan_record = yaml.load(fin)

    d2_pos = versiscan_record[0]['d2_pos']
    d1_ind_l = versiscan_record[0]['d1_ind_l']
    d1_ind_r = versiscan_record[0]['d1_ind_r']

    _in = (d2_pos, d1_ind_l, d1_ind_r)
    return _in, _msg


indent_table_ag = ra.Agent(poll_in=indent_table_in, verbose=2
                           , initial_value=[[0, 1], [0, 0], [0, 0]])
indent_table_ag.indent_profile_filename = '/beamline/perforce/tec/mc/pmacRascan/trunk/midLayer/SCS/' + 'versiscan_record.yaml'

# indent_table_ag.poll.force([[0, 1], [0, 0.55], [0, 0.33]], for_cycles=1)


def next_ind_in(self: ra.Agent):

    x = d2_next_line_ag.poll.Var
    xp = indent_table_ag.poll.Var[0]
    left_f = indent_table_ag.poll.Var[1]
    right_f = indent_table_ag.poll.Var[2]
    # check if xp is increasing:
    if np.all(np.diff(xp) > 0):
        _next_ind_left = np.interp(x, xp, left_f)
        _next_ind_right = np.interp(x, xp, right_f)

        if np.isfinite(_next_ind_left) and np.isfinite(_next_ind_right):
            return (_next_ind_left, _next_ind_right), ''

    return None, ''


def next_ind_out(self: ra.Agent):
    # ONLY do this if there is enough permit

    if self.poll.Changed:
        micro_rscn.d1_indl_req_ag.poll.force(self.poll.Var[0])
        micro_rscn.d1_indr_req_ag.poll.force(self.poll.Var[1])
        return ra.StateLogics.Armed, ''
    else:
        return ra.StateLogics.Idle, ''

def next_ind_hold(self: ra.Agent):
    # just made a forced output, rest here!

    return ra.StateLogics.Done, ''


next_ind_ag = ra.Agent(poll_in=next_ind_in, act_on_valid=next_ind_out, act_on_armed=next_ind_hold, verbose=2)

#input('press a key or break...')
# dm module called to compile and install agents
agents_sorted_by_layer = ra.compile_n_install(predefined_agents, globals().copy(), default_eprefix)

#input('press any key to start the process loop...')

# dm module takes control of the process loop
ra.process_loop(agents_sorted_by_layer, n_loop=10000, cycle_period=0.2, debug=args.debug)
