#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015, NewAE Technology Inc.
# All rights reserved.
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
import sys

from PySide.QtCore import *
from PySide.QtGui import *

import time

try:
    from pyqtgraph.parametertree import Parameter
except ImportError:
    print "ERROR: PyQtGraph is required for this program"
    sys.exit()

from chipwhisperer.capture.auxiliary.AuxiliaryTemplate import AuxiliaryTemplate
from openadc.ExtendedParameter import ExtendedParameter

class ResetCW1173Read(AuxiliaryTemplate):
    paramListUpdated = Signal(list)

    def setupParameters(self):
        ssParams = [{'name':'Interface', 'type':'list', 'key':'target', 'values':['xmega (PDI)', 'avr (ISP)'], 'value':'xmega (PDI)'},
                    {'name':'Post-Reset Delay', 'type':'int', 'key':'toggledelay', 'limits':(0, 10E3), 'value':0, 'suffix':'mS'},
                    {'name':'Test Reset', 'type':'action', 'action':self.testReset}
                    ]
        self.params = Parameter.create(name='Reset AVR/XMEGA via CW-Lite', type='group', children=ssParams)
        ExtendedParameter.setupExtended(self.params, self)

    def captureInit(self):
        pass

    def captureComplete(self):
        pass

    def traceArmPost(self):
        target = self.findParam('target').value()
        if target == 'xmega (PDI)':
            self.parent().scope.scopetype.cwliteXMEGA.readSignature()
        else:
            self.parent().scope.scopetype.cwliteAVR.readSignature()

        dly = self.findParam('toggledelay').value()
        if dly > 0:
            self.nonblockingSleep(dly / 1000.0)

    def traceDone(self):
        pass

    def testReset(self):
        self.traceArmPost()


    def nonblockingSleep_done(self):
        self._sleeping = False

    def nonblockingSleep(self, stime):
        """Sleep for given number of seconds (~50mS resolution), but don't block GUI while we do it"""
        QTimer.singleShot(stime * 1000, self.nonblockingSleep_done)
        self._sleeping = True
        while(self._sleeping):
            time.sleep(0.01)
            QApplication.processEvents()
