#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2014, NewAE Technology Inc
# All rights reserved.
#
# Authors: Colin O'Flynn
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
#
#
#
# This example captures data using the ChipWhisperer Rev2 api hardware. The target is a SimpleSerial board attached
# to the ChipWhisperer.
#
# Data is saved into both a project file and a MATLAB array
#

import sys
from chipwhisperer.common.api.CWCoreAPI import CWCoreAPI  # Import the ChipWhisperer API
import chipwhisperer.capture.ui.CWCaptureGUI as cwc       # Import the ChipWhispererCapture GUI
from chipwhisperer.common.scripts.base import UserScriptBase
from chipwhisperer.common.utils.parameter import Parameter
from chipwhisperer.capture.utils.XMEGAProgrammer import XMEGAProgrammer


class UserScript(UserScriptBase):
    _name = "ChipWhisperer-Lite: AES SimpleSerial on XMEGA"
    _description = "SimpleSerial with Standard Target for AES (XMEGA)"

    def __init__(self, api):
        super(UserScript, self).__init__(api)

    def run(self):
        #User commands here
        self.api.setParameter(['Generic Settings', 'Scope Module', 'ChipWhisperer/OpenADC'])
        self.api.setParameter(['Generic Settings', 'Target Module', 'Simple Serial'])
        self.api.setParameter(['Generic Settings', 'Trace Format', 'None'])
        self.api.setParameter(['Simple Serial', 'Connection', 'ChipWhisperer-Lite'])
        self.api.setParameter(['ChipWhisperer/OpenADC', 'Connection', 'ChipWhisperer-Lite'])

        self.api.connect()

        #Example of using a list to set parameters. Slightly easier to copy/paste in this format
        lstexample = [
            ['OpenADC', 'Clock Setup', 'Freq Counter Src', 'CLKGEN Output'],
            ['OpenADC', 'Clock Setup', 'CLKGEN Settings', 'Desired Frequency', 7370000.0],
            ['OpenADC', 'Clock Setup', 'ADC Clock', 'Reset ADC DCM', None],
            ['Glitch Module', 'Clock Source', 'CLKGEN'],
            ['CW Extra Settings', 'Target HS IO-Out', 'Glitch Module'],
            ['CW Extra Settings', 'Target IOn Pins', 'Target IO1', 'Serial RXD'],
            ['CW Extra Settings', 'Target IOn Pins', 'Target IO2', 'Serial TXD']
        ]
        for cmd in lstexample: self.api.setParameter(cmd)

        xmega = XMEGAProgrammer()
        xmega.setUSBInterface(self.api.getScope().scopetype.dev.xmega)
        xmega._logging = None
        xmega.find()
        xmega.erase()
        xmega.program(r"glitchsimple.hex", memtype="flash", verify=True)
        xmega.close()

        lstexample = [
            ['Glitch Module', 'Glitch Width (as % of period)', 10],
            ['Glitch Module', 'Glitch Offset (as % of period)', 26.6],
            ['Glitch Module', 'Repeat', 105],
            ['Glitch Module', 'Glitch Trigger', 'Manual'],
            ['Glitch Module', 'Manual Trigger / Single-Shot Arm', None],
        ]
        for cmd in lstexample: self.api.setParameter(cmd)

        lstexample = [
            ['Generic Settings', 'Auxiliary Module', 'Reset AVR/XMEGA via CW-Lite'],
            ['Simple Serial', 'Load Key Command', u''],
            ['Simple Serial', 'Go Command', u''],
            ['Simple Serial', 'Output Format', u''],
        ]
        for cmd in lstexample: self.api.setParameter(cmd)

        self.api.capture1()
        self.api.capture1()
        self.api.capture1()

        lstexample = [
            ['OpenADC', 'Clock Setup', 'ADC Clock', 'Source', 'CLKGEN x4 via DCM'],
            ['OpenADC', 'Clock Setup', 'ADC Clock', 'Reset ADC DCM', None],
            ['OpenADC', 'Trigger Setup', 'Mode', 'rising edge'],
            ['OpenADC', 'Trigger Setup', 'Total Samples', 1000],
            ['OpenADC', 'Gain Setting', 'Setting', 40],
        ]
        for cmd in lstexample: self.api.setParameter(cmd)

        self.api.capture1()
        self.api.capture1()
        self.api.capture1()

        self.api.setParameter(['Glitch Module', 'Glitch Trigger', 'Ext Trigger:Single-Shot'])

        self.api.capture1()
        self.api.capture1()
        self.api.capture1()

        self.api.setParameter(['Simple Serial', 'Output Format', u'$GLITCH$'])

        self.api.capture1()
        self.api.capture1()
        self.api.capture1()

        lstexample = [
            ['Glitch Explorer', 'Normal Response', u"s == '\\x00hello\\nA'"],
            ['Glitch Explorer', 'Successful Response', u"s.endswith('1234')"],
            ]
        for cmd in lstexample: self.api.setParameter(cmd)

        self.api.capture1()
        self.api.capture1()
        self.api.capture1()

        lstexample = [
            ['Glitch Explorer', 'Tuning Parameters', 1],
            ['Glitch Explorer', 'Tuning Parameter 0', 'Name', u'Offset\n'],
            ['Glitch Explorer', 'Tuning Parameter 0', 'Parameter Path', u"['Glitch Module', 'Glitch Offset (as % of period)']\n"],
            ['Glitch Explorer', 'Tuning Parameter 0', 'Data Format', 'Float'],
            ['Glitch Explorer', 'Tuning Parameter 0', 'Range', (-30, 30)],
            ['Glitch Explorer', 'Tuning Parameter 0', 'Value', -30.0],
            ['Glitch Explorer', 'Tuning Parameter 0', 'Step', 0.5],
            ['Glitch Explorer', 'Tuning Parameter 0', 'Repeat', 1],
            ['Glitch Module', 'Repeat', 10],
            ['Glitch Module', 'Glitch Width (as % of period)', 8.0],
            ['Generic Settings', 'Acquisition Settings', 'Number of Traces', 121]
        ]
        for cmd in lstexample: self.api.setParameter(cmd)
        self.api.captureM()


if __name__ == '__main__':
    app = cwc.makeApplication()                     # Comment this line if you don't want to use the GUI
    Parameter.usePyQtGraph = True                   # Comment this line if you don't want to use the GUI
    api = CWCoreAPI()                               # Instantiate the API
    # app.setApplicationName("Capture Scripted")    # If you DO NOT want to overwrite settings from the GUI
    gui = cwc.CWCaptureGUI(api)                     # Comment this line if you don't want to use the GUI
    gui.show()
    gui.glitchMonitor.show()
    gui.serialTerminal.show()
    api.runScriptClass(UserScript)                  # Run the User Script

    sys.exit(app.exec_())