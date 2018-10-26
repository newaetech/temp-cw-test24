#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2016, NewAE Technology Inc
# All rights reserved.
#
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.assembla.com/spaces/chipwhisperer
#
#    This file is part of chipwhisperer.
#
#    chipwhisperer is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    chipwhisperer is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with chipwhisperer.  If not, see <http://www.gnu.org/licenses/>.
#=================================================
import numpy as np

class OutputVsTimeNoGUI(object):
    def __init__(self, stats = None, keys = None):
        self._stats = stats
        self._keys = keys

    def update_stats(self, stats):
        self._stats = stats
    def update_keys(self, keys):
        self._keys = keys

    def getPlotData(self, bnum):
        if self._stats is None:
            return None
        if self._keys is None:
            return None
        ## get < key data
        key = self._keys[bnum]
        data = self._stats.diffs[bnum]
        xrangelist = range(0, len(data[0]))

        max1 = np.amax(data[0:key-1], 0)
        min1 = np.amin(data[0:key-1], 0)

        arr1 = np.zeros(len(data[0]))
        for obj in enumerate(max1):
            i = obj[0]
            if abs(max1[i]) > abs(min1[i]):
                arr1[i] = max1[i]
            else:
                arr1[i] = min1[i]

        ## get > key data
        max2 = np.amax(data[key+1:-1], 0)
        min2 = np.amin(data[key+1:-1], 0)

        arr2 = np.zeros(len(data[0]))
        for obj in enumerate(max1):
            i = obj[0]
            if abs(max2[i]) > abs(min2[i]):
                arr2[i] = max2[i]
            else:
                arr2[i] = min2[i]

        return [xrangelist, data[key], arr1, arr2]

