#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2016, NewAE Technology Inc
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

import _OpenADCInterface as openadc
from chipwhisperer.common.utils.parameter import Parameterized, Parameter
from chipwhisperer.common.utils import util, timer


class OpenADCQt(Parameterized):
    _name= 'OpenADC'

    def __init__(self, parentParam=None):
        self.dataUpdated = util.Signal()

        self.params = Parameter(name=self.getName(), type='group').register()

        self.offset = 0.5
        self.ser = None
        self.sc = None
        self.parm_hwinfo = None
        self.parm_gain = None
        self.parm_trigger = None
        self.parm_clock = None

        self.datapoints = []

        self.timerStatusRefresh = timer.Timer()
        self.timerStatusRefresh.timeout.connect(self.statusRefresh)

    def setEnabled(self, enabled):
        pass

    def statusRefresh(self):
        pass

    def processData(self, data):
        fpData = []

        #lastpt = -100;

        if data[0] != 0xAC:
            print "Unexpected sync byte: 0x%x" % data[0]
            return None

        for i in range(2, len(data)-1, 2):
            if (0x80 & data[i + 1]) or ((0x80 & data[i + 0]) == 0):
                print "Error at byte %d" % i
                print("Bytes: %x %x"%(data[i], data[i+1]))
                return None

            #Convert
            intpt = data[i + 1] | ((data[i+0] & 0x07) << 7)

            #input validation test: uncomment following and use
            #ramp input on FPGA
            ##if (intpt != lastpt + 1) and (lastpt != 0x3ff):
            ##    print "intpt: %x lstpt %x\n"%(intpt, lastpt)
            ##lastpt = intpt;

            fpData.append(float(intpt) / 1024.0 - self.offset)

        return fpData

    def arm(self):
        self.sc.arm()

    def read(self, update=True, NumberPoints=None):
        if NumberPoints == None:
            NumberPoints = self.parm_trigger.maxSamples()

        try:
            self.datapoints = self.sc.readData(NumberPoints)
        except IndexError, e:
            raise IOError("Error reading data: %s"%str(e))

        self.dataUpdated.emit(self.datapoints, -self.parm_trigger.presamples(True))

    def capture(self, update=True, NumberPoints=None):
        timeout = self.sc.capture()
        self.read(update, NumberPoints)
        return timeout

    def reset(self):
        self.sc.setReset(True)
        self.params.refreshAllParameters()

    def test(self):
        self.sc.testAndTime()

    def con(self, ser):
        self.ser = ser
        #See if device seems to be attached
        self.sc = openadc.OpenADCInterface(self.ser)

        self.parm_hwinfo = openadc.HWInformation(self.sc)
        self.params.append(self.parm_hwinfo.getParams())

        self.parm_gain = openadc.GainSettings(self.sc)
        self.params.append(self.parm_gain.getParams())

        self.parm_trigger = openadc.TriggerSettings(self.sc)
        self.params.append(self.parm_trigger.getParams())

        self.parm_clock = openadc.ClockSettings(self.sc, hwinfo=self.parm_hwinfo)
        self.params.append(self.parm_clock.getParams())

        deviceFound = False
        numTries = 0

        #Try a few times
        while(deviceFound == False):

            if self.sc.devicePresent():
                deviceFound = True
                break

            numTries += 1

            if (numTries == 5):
                try:
                    portname = self.ser.name
                except:
                    portname = "UNKNOWN"
                # self.ser.close()
                self.close()

                raise IOError("Opened port %s but failed to find OpenADC" % portname)

        self.params.refreshAllParameters()
        self.setEnabled(True)

    def close(self):
        if self.ser:
            self.ser = None
            if self.parm_hwinfo is not None:
                self.parm_hwinfo.getParams().remove()

            if self.parm_gain is not None:
                self.parm_gain.getParams().remove()

            if self.parm_trigger is not None:
                self.parm_trigger.getParams().remove()

            if self.parm_clock is not None:
                self.parm_clock.getParams().remove()

    def __del__(self):
        self.close()
