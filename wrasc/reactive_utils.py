#!/usr/bin/env python
#
# $File: //ASP/Personal/afsharn/wrasc/wrasc/reactive_utils.py $
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

import os
import inspect
import numpy as np


class myEsc:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    JUMP = '\033[2J\033[1;1H'
    SAVE = '\033[s'
    REST = '\033[u'

    ERROR = RED + 'ERROR: '
    WARNING = YELLOW + 'WARNING: '
    SUCCESS = GREEN + 'SUCCESS: '
    SILENT_WARNING = YELLOW


def cls():
    os.system('cls' if os.name == 'nt' else 'clear')


def move_cursor(y, x):
    print("<")
    print("\033[%d;%dH" % (y, x))
    print(">")


def ptop(window):
    height, width = window.getmaxyx()
    for i in range(10):
        window.addstr(height - 1, 0, "[" + ("=" * i) + ">" + (" " * (10 - i)) + "]")
        window.refresh()


def retrieve_name(var):
    callers_local_vars = inspect.currentframe().f_back.f_locals.items()
    return [var_name for var_name, var_val in callers_local_vars if var_val is var]


def retrieve_name_in_globals(var, _globals):
    return [var_name for var_name, var_val in _globals.items() if var_val is var][0]


def clip_abs(n, abs_minn, abs_maxn):

    if n < 0:
        return np.clip(n, -abs(abs_maxn), -abs(abs_minn))
    else:
        return np.clip(n, abs(abs_minn), abs(abs_maxn))
