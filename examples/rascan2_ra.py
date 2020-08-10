#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/wrasc/examples/rascan2_ra.py $
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


""" Rascan 2 Reactive Agents library
"""

from wrasc import reactive_agent as ra
from inspect import getmembers


class Rascan2(ra.Device):

    def __init__(self, unit=None, **kwargs):
        self.dmDeviceType = 'RASCAN2'
        self.default_dev_prefix = ':RSCN'
        self.default_dev_pvs = None

        super().__init__(**kwargs)

        self.dev_state_ag = ra.Agent(poll_in=ra.get_in_pv, verbose=1)
        self.d2_start_ag = ra.Agent(poll_in=ra.get_in_pv, verbose=1)
        self.d2_step_ag = ra.Agent(poll_in=ra.get_in_pv, verbose=1)
        self.line_n_ag = ra.Agent(poll_in=ra.get_in_pv, verbose=1)
        self.d1_ind_hlm_ag = ra.Agent(poll_in=ra.get_in_pv, verbose=1)

        self.d1_indl_req_ag = ra.Agent(act_on_valid=ra.put_out_pv, act_on_invalid=ra.reset_out_pv, verbose=1)
        self.d1_indr_req_ag = ra.Agent(act_on_valid=ra.put_out_pv, act_on_invalid=ra.reset_out_pv, verbose=1)

        # just setting eprefix and dev_prefix if there was no pv_list in kwargs
        self.install_dev_pvs(**kwargs)

        # setting agent pv's
        self.set_ag_pvs()

    def set_ag_pvs(self):

        names = [memb[0] for memb in getmembers(self)]
        ag_names = [nam for nam in names if nam.endswith('_ag')]
        pv_names = [':' + nam.strip('_ag').upper() for nam in ag_names]

        if self.eprefix is not None\
            and self.dev_prefix is not None\
            and len(pv_names) > 0:

            for pvname in pv_names:
                agname = pvname.strip(':').lower() + '_ag'
                exec_str = "self.{0}.install_pvs(inpvname='{1}', outpvname='{1}', dev_prefix='{2}', eprefix='{3}')"\
                    .format(agname, pvname, self.dev_prefix, self.eprefix)
                exec(exec_str)


if __name__ == '__main__':
    pass

