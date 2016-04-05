#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014, NewAE Technology Inc
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

"""
This module has an interface to the PicoTech PicoScope device. It uses the
picoscope library at https://github.com/colinoflynn/pico-python which you
must install
"""

import collections
import time

from picoscope import ps2000
from picoscope import ps5000a
from picoscope import ps6000

from chipwhisperer.capture.scopes.ScopeTemplate import ScopeTemplate
from chipwhisperer.common.api.config_parameter import ConfigParameter
from chipwhisperer.common.utils import Util


def getInstance(*args):
    return PicoScopeInterface(*args)

class PicoScope(object):
    paramListUpdated = Util.Signal()
    dataUpdated = Util.Signal()

    def __init__(self, psClass):
        self.ps = psClass
        
        chlist = {}
        for t in self.ps.CHANNELS:
            if self.ps.CHANNELS[t] < self.ps.CHANNELS['MaxChannels']:
                chlist[t] = self.ps.CHANNELS[t]

        # Rebuild channel range as string + api value
        chRange = collections.OrderedDict()
        for key in sorted(self.ps.CHANNEL_RANGE):
            chRange[ key['rangeStr'] ] = key['rangeV']

        scopeParams = [
                      {'name':'Trace Measurement', 'type':'group', 'children':[
                         {'name':'Source', 'key':'tracesource', 'type':'list', 'values':chlist, 'value':0, 'set':self.updateCurrentSettings},
                         {'name':'Probe Att.', 'key':'traceprobe', 'type':'list', 'values':{'1:1':1, '1:10':10}, 'value':1, 'set':self.updateCurrentSettings},
                         {'name':'Coupling', 'key':'tracecouple', 'type':'list', 'values':self.ps.CHANNEL_COUPLINGS, 'value':0, 'set':self.updateCurrentSettings},
                         {'name':'Y-Range', 'key':'traceyrange', 'type':'list', 'values':chRange, 'value':1.0, 'set':self.updateCurrentSettings}, ]},
                      {'name':'Trigger', 'type':'group', 'children':[
                         {'name':'Source', 'key':'trigsource', 'type':'list', 'values':chlist, 'value':1, 'set':self.updateCurrentSettings},
                         {'name':'Probe Att.', 'key':'trigprobe', 'type':'list', 'values':{'1:1':1, '1:10':10}, 'value':10, 'set':self.updateCurrentSettings},
                         {'name':'Coupling', 'key':'trigcouple', 'type':'list', 'values':self.ps.CHANNEL_COUPLINGS, 'value':1, 'set':self.updateCurrentSettings},
                         {'name':'Y-Range', 'key':'trigrange', 'type':'list', 'values':chRange, 'value':5.0, 'set':self.updateCurrentSettings},
                         {'name':'Trigger Direction', 'key':'trigtype', 'type':'list', 'values':self.ps.THRESHOLD_TYPE, 'value':2, 'set':self.updateCurrentSettings},
                         {'name':'Trigger Level', 'key':'triglevel', 'type':'float', 'step':1E-2, 'siPrefix':True, 'suffix':'V', 'limits':(-5, 5), 'value':0.5, 'set':self.updateCurrentSettings},
                         ]},
                      {'name':'Sample Rate', 'key':'samplerate', 'type':'int', 'step':1E6, 'limits':(10000, 5E9), 'value':100E6, 'set':self.UpdateSampleRateFreq, 'siPrefix':True, 'suffix':'S/s'},
                      {'name':'Sample Length', 'key':'samplelength', 'type':'int', 'step':5000, 'limits':(1, 500E6), 'value':5000, 'set':self.UpdateSampleRateFreq},
                      {'name':'Sample Offset', 'key':'sampleoffset', 'type':'int', 'step':1000, 'limits':(0, 100E6), 'value':0, 'set':self.UpdateSampleRateFreq},
                  ]
        
        for t in self.getAdditionalParams():
            scopeParams.append(t)

        self.params = ConfigParameter.create_extended(self, name='Scope Settings', type='group', children=scopeParams)
            
    def getAdditionalParams(self):
        """Override this to define additional parameters"""
        return []
            
    def UpdateSampleRateFreq(self, ignored=None):
        if self.ps.handle is not None:
            paramSR = self.findParam('samplerate')
            paramSL = self.findParam('samplelength')
            self.ps.setSamplingFrequency(paramSR.value(), paramSL.value() + self.findParam('sampleoffset').value(), 1)
            paramSR.setValue(self.ps.sampleRate)
            paramSL.setValue(min(self.ps.maxSamples, paramSL.value()))
    #         QTimer.singleShot(0, self.UpdateSampleParameters)
    #
    # def UpdateSampleParameters(self):
    #     paramSR = self.findParam('samplerate')
    #     paramSL = self.findParam('samplelength')
    #     paramSR.setValue(self.ps.sampleRate)
    #     paramSL.setValue(min(self.ps.maxSamples, paramSL.value()))

    def con(self):
        self.ps.open()
        self.updateCurrentSettings()
            
    def paramList(self):
        return [self.params]
    
    def updateCurrentSettings(self, ignored=False):
        if self.ps.handle is None: return

        try:
            # Turn off all channels
            for c in self.ps.CHANNELS:
                self.ps.setChannel(c, enabled=False)
        except IOError:
            pass

        try:
            # Trace Channel
            TraceCh = self.findParam('tracesource').value()
            TraceCo = self.findParam('tracecouple').value()
            TraceY = self.findParam('traceyrange').value()
            TraceP = self.findParam('traceprobe').value()
            self.ps.setChannel(channel=TraceCh, coupling=TraceCo, VRange=TraceY, probeAttenuation=TraceP, enabled=True)

            # Trigger Channel
            TrigCh = self.findParam('trigsource').value()
            TrigCo = self.findParam('trigcouple').value()
            TrigY = self.findParam('trigrange').value()
            TrigP = self.findParam('trigprobe').value()
            self.ps.setChannel(channel=TrigCh, coupling=TrigCo, VRange=TrigY, probeAttenuation=TrigP, enabled=True)

            # Trigger
            self.ps.setSimpleTrigger(TrigCh, self.findParam('triglevel').value(), direction=self.findParam('trigtype').value(), timeout_ms=1000)

            self.UpdateSampleRateFreq()
        except IOError, e:
            raise IOError("Caught Error: %s" % str(e))


    def arm(self):       
        self.ps.runBlock()
        
    def capture(self):
        while(self.ps.isReady() == False): time.sleep(0.01)
        data = self.ps.getDataV(self.findParam('tracesource').value(), self.findParam('samplelength').value(), startIndex=self.findParam('sampleoffset').value(), returnOverflow=True)
        if data[1] is True:
            print "WARNING: OVERFLOW IN DATA"
        self.datapoints = data[0]
        self.dataUpdated.emit(self.datapoints, 0)
#        waitingCallback()

        # No timeout?
        return False

class PicoScopeInterface(ScopeTemplate):
    dataUpdated = Util.Signal()

    def __init__(self):
        super(PicoScopeInterface, self).__init__()
        self.scopetype = None

        scope_cons = {}
        scope_cons["PS6000"] = ps6000.PS6000(connect=False)
        scope_cons["PS5000a"] = ps5000a.PS5000a(connect=False)
        scope_cons["PS2000"] = ps2000.PS2000(connect=False)
        defscope = scope_cons["PS5000a"]

        self.advancedSettings = None
        
        scopeParams = [{'name':'Scope Type', 'type':'list', 'values':scope_cons, 'value':defscope, 'set':self.setCurrentScope},
                      ]
        
        self.params = ConfigParameter.create_extended(self, name='PicoScope Interface', type='group', children=scopeParams)
        self.setCurrentScope(defscope)

    def passUpdated(self, lst, offset):
        self.datapoints = lst
        self.offset = offset
        self.dataUpdated.emit(lst, offset)

    def setCurrentScope(self, scope, update=True):
        if scope is not None:
            self.scopetype = PicoScope(scope)
            self.scopetype.dataUpdated.connect(self.passUpdated)
        else:
            self.scopetype = scope

        if update:
            self.paramListUpdated.emit()
   
    def con(self):
        if self.scopetype is not None:
            self.scopetype.con()
            self.connectStatus.setValue(True)

    def dis(self):
        if self.scopetype is not None:
            self.scopetype.dis()  
            self.connectStatus.setValue(False)

    def doDataUpdated(self,  l, offset=0):
        self.datapoints = l
        self.offset = offset
        if len(l) > 0:
            self.dataUpdated.emit(l, offset)

    def arm(self):
        try:
            self.scopetype.arm()
        except Exception:
            self.dis()
            raise

    def capture(self, update=True, NumberPoints=None, waitingCallback=None):
        """Raises IOError if unknown failure, returns 'True' if successful, 'False' if timeout"""
        return self.scopetype.capture(update, NumberPoints, waitingCallback)
        
    def paramList(self):
        p = []       
        p.append(self.params)  
         
        if self.scopetype is not None:
            for a in self.scopetype.paramList(): p.append(a)
            
        #if self.advancedSettings is not None:
        #    for a in self.advancedSettings.paramList(): p.append(a)    
            
        return p

    def validateSettings(self):
        return []

    def getName(self):
        return "PicoScope"