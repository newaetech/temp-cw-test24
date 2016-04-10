#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2014, NewAE Technology Inc
# All rights reserved.
#
# Author: Colin O'Flynn
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
from chipwhisperer.common.api.config_parameter import ConfigParameter
from chipwhisperer.analyzer.preprocessing.PreprocessingBase import PreprocessingBase

def getClass():
    """"Returns the Main Class in this Module"""
    return AddNoiseRandom


class AddNoiseRandom(PreprocessingBase):
    name = "Add Noise: Amplitude"
    descrString = "Add random noise"
     
    def setupParameters(self):
        ssParams = [{'name':'Enabled', 'key':'enabled', 'type':'bool', 'value':self.enabled, 'set':self.updateScript},
                         {'name':'Noise Std-Dev', 'key':'noisestddev', 'type':'float', 'step':0.001, 'value':0.005, 'limits':(0, 1.0), 'set':self.updateScript},
                         {'name':'Description', 'type':'text', 'value':self.descrString, 'readonly':True}
                      ]
        self.params = ConfigParameter.create_extended(self, name=self.name, type='group', children=ssParams)
        self._maxNoise = 0
        self.updateScript()

    def updateScript(self, ignored=None):
        self.addFunction("init", "setEnabled", "%s" % self.findParam('enabled').value())
        self.addFunction("init", "setMaxNoise", '%f' % self.findParam('noisestddev').value())

    def setMaxNoise(self, maxNoise):
        self._maxNoise = maxNoise
   
    def getTrace(self, n):
        if self.enabled:
            trace = self.traceSource.getTrace(n)
            if trace is None:
                return None
            
            if self._maxNoise == 0:
                return trace
            else:
                return trace + np.random.normal(scale=self._maxNoise, size=len(trace))
        else:
            return self.traceSource.getTrace(n)
