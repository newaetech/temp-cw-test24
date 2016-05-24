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

import sys
from chipwhisperer.common.utils import pluginmanager
from ._base import AttackBaseClass
from ._generic_parameters import AttackGenericParameters
from chipwhisperer.common.ui.ProgressBar import ProgressBar


class CPA(AttackBaseClass, AttackGenericParameters):
    """Correlation Power Analysis Attack"""
    _name = "CPA"

    def __init__(self):
        AttackGenericParameters.__init__(self)
        AttackBaseClass.__init__(self)

        algos = pluginmanager.getPluginsInDictFromPackage("chipwhisperer.analyzer.attacks.cpa_algorithms", False, False)
        self.params.addChildren([
            {'name':'Algorithm', 'key':'CPA_algo', 'type':'list', 'values':algos, 'value':algos["Progressive"], 'set':self.updateAlgorithm},            #TODO: Should be called from the AES module to figure out # of bytes
        ])
        self.setAnalysisAlgorithm(self.findParam('CPA_algo').getValue(), None, None)
        self.updateBytesVisible()
        self.updateScript()

    def updateAlgorithm(self, algo):
        self.setAnalysisAlgorithm(algo, None, None)
        self.updateBytesVisible()
        self.updateScript()

    def setHardwareModel(self, model):
        self.numsubkeys = model.numSubKeys
        self.updateBytesVisible()
        self.updateScript()

    def setAnalysisAlgorithm(self, analysisAlgorithm, hardwareModel, leakageModel):
        self.attack = analysisAlgorithm(self, hardwareModel, leakageModel)

        try:
            self.attackParams = self.attack.paramList()[0]
        except:
            self.attackParams = None

        self.paramListUpdated.emit()

        if hasattr(self.attack, 'scriptsUpdated'):
            self.attack.scriptsUpdated.connect(self.updateScript)

    def updateScript(self, ignored=None):
        self.importsAppend("from chipwhisperer.analyzer.attacks.cpa import CPA")

        analysAlgoStr = self.attack.__class__.__name__
        hardwareStr = self.findParam('hw_algo').getValue().__name__
        leakModelStr = hardwareStr + "." + self.findParam('hw_leak').getValue()

        self.importsAppend("from %s import %s" % (sys.modules[self.attack.__class__.__module__].__name__, analysAlgoStr))
        self.importsAppend("import %s" % hardwareStr)

        self.addFunction("init", "setAnalysisAlgorithm", "%s,%s,%s" % (analysAlgoStr, hardwareStr, leakModelStr), loc=0)

        if hasattr(self.attack, '_smartstatements'):
            self.mergeGroups('init', self.attack, prefix='attack')

        self.addFunction("init", "setTraceSource", "UserScript.traces")

    def processKnownKey(self, inpkey):
        if inpkey is None:
            return None

        if hasattr(self.attack, 'processKnownKey'):
            return self.attack.processKnownKey(inpkey)
        else:
            return inpkey

    def processTraces(self):
        progressBar = ProgressBar("Analysis in Progress", "Attaking with CPA:")
        with progressBar:
            self.attack.setTargetBytes(self.targetBytes())
            self.attack.setReportingInterval(self.getReportingInterval())
            self.attack.getStatistics().clear()
            self.attack.setStatsReadyCallback(self.sigAnalysisUpdated.emit)

            self.sigAnalysisStarted.emit()
            for itNum in range(1, self.getIterations()+1):
                startingTrace = self.getTracesPerAttack() * (itNum - 1) + self.getTraceStart()
                endingTrace = startingTrace + self.getTracesPerAttack() - 1
                #TODO:  pointRange=self.TraceRangeList[1:17]
                self.attack.addTraces(self.traceSource(), (startingTrace, endingTrace), progressBar, pointRange=self.getPointRange())
                if progressBar and progressBar.wasAborted():
                    return

        self.sigAnalysisDone.emit()

    def getStatistics(self):
        return self.attack.getStatistics()

    def paramList(self):
        l = [self.params, self.pointsParams, self.traceParams]
        if self.attackParams is not None:
            l.append(self.attackParams)
        return l
