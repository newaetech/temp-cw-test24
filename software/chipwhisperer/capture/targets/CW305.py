#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015-2016, NewAE Technology Inc
# All rights reserved.
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.chipwhisperer.com . ChipWhisperer is a registered
# trademark of NewAE Technology Inc in the US & Europe.
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
import time
import math
from functools import partial

from PySide.QtCore import *
from PySide.QtGui import *
from pip._vendor.requests.packages.chardet.latin1prober import FREQ_CAT_NUM

try:
    from pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType
except ImportError:
    print "ERROR: PyQtGraph is required for this program"
    sys.exit()
    
from openadc.ExtendedParameter import ExtendedParameter
from TargetTemplate import TargetTemplate
from chipwhisperer.capture.scopes.ChipWhispererLite import CWLiteUSB

class CW305(TargetTemplate):
     
    def setupParameters(self): 
        self.hw = None
        self.reffreq = 12.0E6
        ssParams = [
                    {'name':'PLL Settings', 'type':'group', 'children':[
                        {'name':'Enabled', 'key':'pllenabled', 'type':'bool', 'value':False, 'set':self.enableset, 'get':self.enableget},
                        {'name':'CLK-SMA (X6)', 'type':'group', 'children':[
                            {'name':'CLK-SMA Enabled', 'key':'pll0enabled', 'type':'bool', 'value':False, 'set':partial(self.outputSetEnabled, outnum=0), 'get':partial(self.outputGetEnabled, outnum=0), },
                            {'name':'CLK-SMA Source', 'key':'pll0source', 'type':'list', 'values':['PLL0', 'PLL1', 'PLL2'], 'value':'PLL0', 'set':partial(self.outputSetSource, outnum=0), 'get':partial(self.outputGetSource, outnum=0), },
                            {'name':'CLK-SMA Slew Rate', 'key':'pll0slew', 'type':'list', 'values':['+3nS', '+2nS', '+1nS', '+0nS'], 'value':'+0nS', 'set':partial(self.outputSetSlew, outnum=0), 'get':partial(self.outputGetSlew, outnum=0)},
                            {'name':'PLL0 Frequency', 'key':'pll0freq', 'type':'float', 'limits':(0.625E6, 167E6), 'value':0, 'step':1E6,
                                'siPrefix':True, 'suffix':'Hz', 'set':partial(self.outputSetFreq, outnum=0), 'get':partial(self.outputGetFreq, outnum=0)},
                        ]},
                        {'name':'CLK-N13 (FGPA Pin N13)', 'type':'group', 'children':[
                            {'name':'CLK-N13 Enabled', 'key':'pll1enabled', 'type':'bool', 'value':False, 'set':partial(self.outputSetEnabled, outnum=1), 'get':partial(self.outputGetEnabled, outnum=1), },
                            {'name':'CLK-N13 Source', 'key':'pll1source', 'type':'list', 'values':['PLL1'], 'value':'PLL1'},
                            {'name':'CLK-N13 Slew Rate', 'key':'pll1slew', 'type':'list', 'values':['+3nS', '+2nS', '+1nS', '+0nS'], 'value':'+0nS', 'set':partial(self.outputSetSlew, outnum=1), 'get':partial(self.outputGetSlew, outnum=1)},
                            {'name':'PLL1 Frequency', 'key':'pll1freq', 'type':'float', 'limits':(0.625E6, 167E6), 'value':0, 'step':1E6,
                                'siPrefix':True, 'suffix':'Hz', 'set':partial(self.outputSetFreq, outnum=1), 'get':partial(self.outputGetFreq, outnum=1)},
                        ]},
                        {'name':'CLK-E12 (FGPA Pin E12)', 'type':'group', 'children':[
                            {'name':'CLK-E12 Enabled', 'key':'pll2enabled', 'type':'bool', 'value':False, 'set':partial(self.outputSetEnabled, outnum=2), 'get':partial(self.outputGetEnabled, outnum=2), },
                            {'name':'CLK-E12 Source', 'key':'pll2source', 'type':'list', 'values':['PLL2'], 'value':'PLL2'},
                            {'name':'CLK-E12 Slew Rate', 'key':'pll2slew', 'type':'list', 'values':['+0nS', '+1nS', '+2nS', '+3nS'], 'value':'+0nS', 'set':partial(self.outputSetSlew, outnum=2), 'get':partial(self.outputGetSlew, outnum=2)},
                            {'name':'PLL2 Frequency', 'key':'pll2freq', 'type':'float', 'limits':(0.625E6, 167E6), 'value':0, 'step':1E6,
                                'siPrefix':True, 'suffix':'Hz', 'set':partial(self.outputSetFreq, outnum=2), 'get':partial(self.outputGetFreq, outnum=2)},
                        ]},
                        {'name':'Save as Default', 'type':'action', 'action':self.cdce906writeEEPROM},
                        ]},
                    {'name':'Disable CLKUSB For Capture', 'key':'clkusbautooff', 'type':'bool', 'value':True},
                    {'name':'Time CLKUSB Disabled for', 'key':'clksleeptime', 'type':'int', 'range':(1, 50000), 'value':50, 'suffix':'mS'},
                    {'name':'CLKUSB Manual Setting', 'key':'clkusboff', 'key':'clkusboff', 'type':'bool', 'value':True, 'set':self.setClkUSB},
                    {'name':'Send Trigger', 'type':'action', 'action':self.toggleTrigger},
                    # {'name':'VCC-INT', 'key':'vccint', 'type':'float', 'value':1.00, 'range':(0.6, 1.05), 'suffix':'V'},
                    # {'name':'FPGA Bitstream'},
                    # {'name':''}
                    ]
        self.params = Parameter.create(name='Target Connection', type='group', children=ssParams)
        ExtendedParameter.setupExtended(self.params, self)      
        self.oa = None

    def setClkUSB(self, status):
        """ Turn on or off the Data Clock to the FPGA """
        if status:
            self.cwtestusb.sendCtrl(0x22, 0x05)
        else:
            self.cwtestusb.sendCtrl(0x22, 0x04)

    def toggleTrigger(self):
        """ Toggle the trigger line high then low """
        self.cwtestusb.sendCtrl(0x22, 0x06)

    def outputSetFreq(self, freq, outnum):        
        """
        Set the PLL Output Frequency
        
        Args:
            freq (int): Frequency in Hz
            outnum (int): PLL Number (0,1,2)                            
        """
        if freq is None or freq is 0: return
        best = self.calcMulDiv(freq, self.reffreq)
        self.pllwrite(outnum, N=best[0], M=best[1], outdiv=best[2])
        self.outputUpdateOutputs(outnum)
        
    def outnumToPin(self, outnum):
        """Convert from PLL Number to actual output pin"""
        if outnum == 0:
            return 0
        elif outnum == 1:
            return 1
        elif outnum == 2:
            return 4
        else:
            raise ValueError("Invalid output number = %d"%outnum)
        
    def outputUpdateOutputs(self, outnum):
        """Update the output pins with enabled/disabled, slew rate, etc"""
        #Map to output pins on CDCE906 Chip
        if outnum == 0:
            outpin = 0
            src = self.findParam('pll0source').value()
            if src == 'PLL0':
                divsrc = 0
            elif src == 'PLL1':
                divsrc = 1
            elif src == 'PLL2':
                divsrc = 2
        elif outnum == 1:
            outpin = 1
            divsrc = 1
        elif outnum == 2:
            outpin = 4
            divsrc = 2
        self.cdce906setoutput(outpin, divsrc, slewrate=self.findParam('pll%dslew' % outnum).value(), enabled=self.findParam('pll%denabled' % outnum).value())
        
    def outputGetFreq(self, outnum):
        """Read the programmed output frequency from a PLL"""
        settings = self.pllread(outnum)        
        freq = ((self.reffreq * float(settings[0])) / float(settings[1])) / float(settings[2])
        return freq
        
    def outputSetEnabled(self, enabled, outnum):
        """Enable or disable one of the PLLs"""
        self.outputUpdateOutputs(outnum)
    
    def outputGetEnabled(self, outnum):
        """Get if an output is enabled or not"""
        outpin = self.outnumToPin(outnum)
        data = self.cdce906read(19+outpin)        
        return bool(data & (1 << 3))
        
    def outputSetSlew(self, enabled, outnum):
        """Updates slew rates from GUI settings"""
        self.outputUpdateOutputs(outnum)

    def outputGetSlew(self, outnum):
        """Get slew rate of PLL output"""
        outpin = self.outnumToPin(outnum)
        data = self.cdce906read(19+outpin)
        slew = data & (3 << 4)
        
        if slew == (0 << 4):
            return "+3nS"
        elif slew == (1 << 4):
            return "+2nS"
        elif slew == (2 << 4):
            return "+1nS"
        else:
            return "+0nS"

    def outputSetSource(self, source, outnum):
        """Updates sources from GUI settings"""
        self.outputUpdateOutputs(outnum)
        
    def outputGetSource(self, outnum):
        """Get output source settings"""
        outpin = self.outnumToPin(outnum)
        data = self.cdce906read(19 + outpin)
        divsrc = data & 0x07
        
        if divsrc == 0:
            return "PLL0"
        elif divsrc == 1:
            return "PLL1"
        elif divsrc == 2:
            return "PLL2"
        else:
            return "UNKNOWN"

    def cdce906writeEEPROM(self):
        """Save PLL settings to EEPROM, making them power-on defaults"""
        # Set bit high to enable write
        data = self.cdce906read(26) & (~(1 << 7))
        self.cdce906write(26, data | (1 << 7))

        # Wait until done
        while(self.cdce906read(24) & (1 << 7)):
            time.sleep(0.05)

        # Set bit low
        self.cdce906write(26, data)


    def cdce906write(self, addr, data):
        """ Write a byte to the CDCE906 External PLL Chip """

        # print "Write %d = %x" % (addr, data)
        self.cwtestusb.sendCtrl(0x30, data=[0x01, addr, data])
        resp = self.cwtestusb.readCtrl(0x30, dlen=2)
        if resp[0] != 2:
            raise IOError("CDCE906 Write Error, response = %d" % resp[0])
        
    def cdce906read(self, addr):
        """ Read a byte from the CDCE906 External PLL Chip """
        self.cwtestusb.sendCtrl(0x30, data=[0x00, addr, 0])
        resp = self.cwtestusb.readCtrl(0x30, dlen=2)
        if resp[0] != 2:
            raise IOError("CDCE906 Read Error, response = %d" % resp[0])
        return resp[1]

    def cdce906init(self):
        """ Set defaults on CDCE906 PLL Chip """
        # Default is:
        # Y0 = P0
        # Y1 = P1
        # Y2,Y3,Y5 = disabled
        # Y4 = P2
        self.outputUpdateOutputs(0)
        self.outputUpdateOutputs(1)
        self.outputUpdateOutputs(2)
        
        self.cdce906setoutput(2, 0, enabled=False)
        self.cdce906setoutput(3, 0, enabled=False)
        self.cdce906setoutput(5, 0, enabled=False)

        self.cdce906write(9, (1 << 5) | (self.cdce906read(9) & 0x1F))  # PLL 1
        self.cdce906write(10, (2 << 5) | (self.cdce906read(10) & 0x1F))  # PLL2 not SSC
        self.cdce906write(11, 4 | (self.cdce906read(11) & 0xF8)) #PLL 3

    def cdce906setoutput(self, outpin, divsource, slewrate='+0nS', enabled=True, inverted=False):
        """Setup the outputs for the PLL chip"""
        data = 0
        if enabled:
            data |= 1 << 3
        data |= divsource
        if slewrate == "+0nS":
            data |= (3 << 4)
        elif slewrate == "+1nS":
            data |= (2 << 4)
        elif slewrate == "+2nS":
            data |= (1 << 4)
        elif slewrate == "+3nS":
            data |= (0 << 4)
        else:
            raise ValueError("Invalid slew rate: %s" % str(slewrate))
        if inverted:
            data |= 1 << 6
        self.cdce906write(19 + outpin, data)

    def enableset(self, enabled):
        """Enable or disable the PLL chip"""
        base = self.cdce906read(12)
        if enabled:
            self.cdce906write(12, base & ~(1 << 6))
        else:
            self.cdce906write(12, base | (1 << 6))

    def enableget(self):
        """Read if PLL chip is enabled or disabled"""
        base = self.cdce906read(12)
        if base & (1 << 6):
            return False
        else:
            return True

    def calcMulDiv(self, freqdesired, freqsource):
        """Calculate Multiply & Divide settings for PLL based on input frequency"""

        lowerror = 1E99
        best = (0, 0, 0)

        # Figured out divider settings to put fvco in range 80-300
        maxoutdiv = int(math.floor(300E6 / freqdesired))
        minoutdiv = int(math.ceil(80E6 / freqdesired))
        maxoutdiv = min(maxoutdiv, 127)

        # If finds an exact match, this is very fast... if not this
        # can take a little while to calculate
        for outdiv in range(minoutdiv, maxoutdiv + 1):
            fvco = freqdesired * outdiv
            for N in xrange(1, 4096):
                for M in xrange(1, 512):
                    err = abs(fvco - ((freqsource * N) / M))
                    if err < lowerror:
                        lowerror = err / outdiv
                        best = (N, M, outdiv)
                        if lowerror == 0:
                            return best
        return best


    def pllwrite(self, pllnum, N, M, outdiv):
        """Write N/M/output divisors to PLL chip"""
        offset = 3 * pllnum

        self.cdce906write(1 + offset, M & 0xFF)
        self.cdce906write(2 + offset, N & 0xFF)
        base = self.cdce906read(3 + offset)
        base = base & 0xE0  # Mask out lower bits
        base |= (M & (0x100)) >> 8
        base |= (N & (0xF00)) >> 7
        self.cdce906write(3 + offset, base)
        self.cdce906write(13 + pllnum, outdiv & 0x7F)

        # Set PLL Mode (high-speed or regular)
        fvco = (self.reffreq * float(N)) / float(M)
        if fvco < 80E6 or fvco > 300E6:
            raise IOError("Fvco set to $d, out of range"%fvco)
        
        data = self.cdce906read(6)
        if pllnum == 0: pllbit = 7
        elif pllnum == 1: pllbit = 6
        elif pllnum == 2: pllbit = 5

        data &= ~(1<<pllbit)         
        if fvco > 180E6:
            # High-speed mode (180-300 MHz)
            data |= 1<<pllbit
        self.cdce906write(6, data)

    def pllread(self, pllnum):
        """Read N/M/output divisors from PLL chip"""
        offset = 3 * pllnum

        # Read M & N
        M = self.cdce906read(1 + offset)
        N = self.cdce906read(2 + offset)
        temp = self.cdce906read(3 + offset)
        M |= ((temp & 0x01)) << 8
        N |= (temp & 0x1E) << 7

        outdiv = self.cdce906read(13 + pllnum) & 0x7F

        return (N, M, outdiv)

    def con(self):   
        """Connect to CW305 board, download bitstream"""
        self.cwtestusb = CWLiteUSB()
        self.cwtestusb.con(idProduct=0xC305)
        force = False
        if self.cwtestusb.isFPGAProgrammed() == False or force:
            from datetime import datetime
            starttime = datetime.now()
            # self.cwtestusb.FPGAProgram(open(r"C:\Users\colin\dropbox\engineering\git_repos\CW305_ArtixTarget\temp\artix7test\artix7test.runs\impl_1\cw305_top.bit", "rb"))
            self.cwtestusb.FPGAProgram(open(r"C:\Users\colin\dropbox\engineering\git_repos\CW305_ArtixTarget\temp_vivado\CW305_VivadoSample\CW305_VivadoSample.runs\impl_1\cw305_blockexample.bit", "rb"))
            stoptime = datetime.now()
            print "FPGA Config time: %s" % str(stoptime - starttime)
        self.cwtestusb.cmdWriteMem(0x100, [0])
        self.params.getAllParameters()
        self.cdce906init()

    def checkEncryptionKey(self, key):
        """Validate encryption key"""
        return key 

    def loadEncryptionKey(self, key):
        """Write encryption key to FPGA"""
        key = key[::-1]
        self.cwtestusb.cmdWriteMem(0x200, key)

    def loadInput(self, inputtext):
        """Write input to FPGA"""
        text = inputtext[::-1]
        self.cwtestusb.cmdWriteMem(0x300, text)

    def isDone(self):
        """Check if FPGA is done"""
        result = self.cwtestusb.cmdReadMem(0x110, 1)[0]

        if result == 0x00:
            return False
        else:
            self.cwtestusb.cmdWriteMem(0x100, [0])
            return True
        
    def readOutput(self):
        """"Read output from FPGA"""
        data = self.cwtestusb.cmdReadMem(0x600, 16)
        data = data[::-1]        
        return data

    def go(self):
        """Disable USB clock (if requested), perform encryption, re-enable clock"""
        if self.findParam('clkusbautooff').value():
            self.setClkUSB(False)

        time.sleep(0.01)
        self.toggleTrigger()
        # self.cwtestusb.cmdWriteMem(0x100, [1])
        # self.cwtestusb.cmdWriteMem(0x100, [0])

        if self.findParam('clkusbautooff').value():
            time.sleep(self.findParam('clksleeptime').value() / 1000.0)
            self.setClkUSB(True)

