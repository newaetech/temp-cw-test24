#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2014, NewAE Technology Inc
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

__version__ = "V3"

import os.path
import sys
import traceback
from functools import partial

from chipwhisperer.capture.api.AcquisitionController import AcquisitionController, AcqKeyTextPattern_Basic, AcqKeyTextPattern_CRITTest
from chipwhisperer.capture.api.ExtendedParameter import ExtendedParameter
from chipwhisperer.capture.api.manager import Manager
from chipwhisperer.capture.ui.CaptureProgressDialog import CaptureProgressDialog
from chipwhisperer.capture.ui.EncryptionStatusMonitor import EncryptionStatusMonitor
from chipwhisperer.capture.utils.GlitchExplorerDialog import GlitchExplorerDialog as GlitchExplorerDialog
from chipwhisperer.capture.utils.SerialTerminalDialog import SerialTerminalDialog as SerialTerminalDialog
from chipwhisperer.common.api.ProjectFormat import ProjectFormat
from chipwhisperer.common.ui.MainChip import MainChip
from chipwhisperer.common.ui.ValidationDialog import ValidationDialog
from chipwhisperer.common.utils import util

try:
    from PySide.QtCore import *
    from PySide.QtGui import *
except ImportError:
    print "ERROR: PySide is required for this program"
    sys.exit()

try:
    import writer_dpav3
except ImportError:
    writer_dpav3 = None
    writer_dpav3_str = sys.exc_info()

try:
    import pyqtgraph as pg
    import pyqtgraph.multiprocess as mp
    import pyqtgraph.parametertree.parameterTypes as pTypes
    from pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType
    #print pg.systemInfo()
except ImportError:
    print "ERROR: PyQtGraph is required for this program"
    sys.exit()

class ChipWhispererCapture(MainChip):
    MaxRecentFiles = 4

    def __init__(self, rootdir="."):
        super(ChipWhispererCapture, self).__init__(name=("ChipWhisperer" + u"\u2122" + " Capture " + __version__), icon="cwiconC")
        util.main_window = self
        self.console = self.addConsole()

        # This is a hack for paths hardcoded into the application. todo: fix this properly.
        util.globalSettings.setValue("cwcapture-starting-root", rootdir)
        self._rootdir = rootdir
        self.auxList = None
        self.esm = EncryptionStatusMonitor(self)
        self.serialTerminal = SerialTerminalDialog(self)
        self.glitchMonitor = GlitchExplorerDialog(self, showScriptParameter=self.showScriptParameter)
        self.paramTrees.append(self.glitchMonitor.paramTree)

        self.manager = Manager()


        self.da = None
        self.numTraces = 100
        self.numSegments = 1

        self.addToolbars()
        self.addWaveforms()
        self.addToolMenu()
        self.addExampleScripts()
        self.restoreDockGeometry()
        self.newFile.connect(self.newProject)
        self.saveFile.connect(self.saveProject)

        self.fixedPlain = False

        valid_scopes = Manager.getScopeModules(self._rootdir + "/scopes", self, self.showScriptParameter);
        valid_targets =  Manager.getTargetModules(self._rootdir + "/targets", self.showScriptParameter);
        valid_traces = Manager.getTraceFormats(self._rootdir + "/../common/traces");
        valid_aux = Manager.getAuxiliaryModules(self._rootdir + "/auxiliary", self.showScriptParameter);

        self.manager.setScope(valid_scopes["None"])
        self.manager.setTarget(valid_targets["None"])
        self.manager.setTraceClass(valid_traces["ChipWhisperer/Native"])
        self.newProject()

        valid_acqPatterns = {"Basic":AcqKeyTextPattern_Basic(showScriptParameter=self.showScriptParameter)}
        if AcqKeyTextPattern_CRITTest:
            valid_acqPatterns['CRI T-Test'] = AcqKeyTextPattern_CRITTest(showScriptParameter=self.showScriptParameter)
        self.setAcqPattern(valid_acqPatterns['Basic'], reloadList=False)

        self.cwParams = [
                {'name':'Scope Module', 'type':'list', 'values':valid_scopes, 'value':self.manager.getScope(), 'set':self.manager.setScope},
                {'name':'Target Module', 'type':'list', 'values':valid_targets, 'value':self.manager.getTarget(), 'set':self.manager.setTarget},
                {'name':'Trace Format', 'type':'list', 'values':valid_traces, 'value':self.manager.getTraceClass(), 'set':self.traceChanged},
                {'name':'Auxiliary Module', 'type':'list', 'values':valid_aux, 'value':None, 'set':self.auxChanged},

                # {'name':'Key Settings', 'type':'group', 'children':[
                #        {'name':'Encryption Key', 'type':'str', 'value':self.textkey, 'set':self.setKey},
                #        {'name':'Send Key to Target', 'type':'bool', 'value':True},
                #        {'name':'New Encryption Key/Trace', 'key':'newKeyAlways', 'type':'bool', 'value':False},
                #    ]},

                {'name':'Acquisition Settings', 'type':'group', 'children':[
                        {'name':'Number of Traces', 'type':'int', 'limits':(1, 1E9), 'value':100, 'set':self.setNumTraces, 'get':self.getNumTraces},
                        {'name':'Capture Segments', 'type':'int', 'limits':(1, 1E6), 'value':1, 'set':self.setNumSegments, 'get':self.getNumSegments, 'tip':'Break capture into N segments, '
                         'which may cause data to be saved more frequently. The default capture driver requires that NTraces/NSegments is small enough to avoid running out of system memory '
                         'as each segment is buffered into RAM before being written to disk.'},
                        {'name':'Open Monitor', 'type':'action', 'action':self.esm.show},
                        {'name':'Key/Text Pattern', 'type':'list', 'values':valid_acqPatterns, 'value':valid_acqPatterns['Basic'], 'set':self.setAcqPattern},
                        # {'name':'Fixed Plaintext', 'type':'bool', 'value':False, 'set':self.setFixedPlain },
                        # {'name':'Fixed Plaintext Value', 'type':'str', 'value':self.plaintextStr, 'set':self.setPlaintext},
                    ]},

                # {'name':''}
                ]

        self.addSettingsDocks()
        self.dockifySettings()
        self.settingsAuxDock.setVisible(False)
        self.reloadParamList()

        self.manager.signals.paramListUpdated.connect(self.reloadTargetParamList)
        self.manager.signals.newInputData.connect(self.newTargetData)
        self.manager.signals.connectStatus.connect(self.targetStatusChanged)
        self.manager.signals.newTextResponse.connect(self.esm.newData)
        self.manager.signals.traceDone.connect(self.glitchMonitor.traceDone)
        self.manager.signals.campaignStart.connect(self.glitchMonitor.campaignStart)
        self.manager.signals.campaignDone.connect(self.glitchMonitor.campaignDone)
        self.manager.signals.scopeChanged.connect(self.scopeChanged)
        self.manager.signals.targetChanged.connect(self.targetChanged)
        self.manager.signals.connectStatus.connect(self.targetStatusChanged)

    def newTargetData(self, data):
        self.glitchMonitor.addResponse(data)

    def scopeChanged(self):
        self.ScopeToolbar.setEnabled(self.manager.hasScope())

        if self.manager.hasScope():
            self.manager.getScope().paramListUpdated.connect(self.reloadScopeParamList)
            self.manager.getScope().dataUpdated.connect(self.newScopeData)
            self.manager.getScope().connectStatus.connect(self.scopeStatusChanged)
            self.reloadScopeParamList()

    def targetChanged(self):
        self.TargetToolbar.setEnabled(self.manager.hasTarget())

        if self.manager.hasTarget():
            self.manager.getTarget().connectStatus.connect(self.targetStatusChanged)
            self.acqPattern.setTarget(self.manager.getTarget())

    def masterStatusChanged(self):
        # Deal with multiple
        if self.scopeStatus.defaultAction() == self.scopeStatusActionCon or self.targetStatus.defaultAction() == self.targetStatusActionCon:
            self.captureStatus.setDefaultAction(self.captureStatusActionCon)
        else:
            self.captureStatus.setDefaultAction(self.captureStatusActionDis)

    def scopeStatusChanged(self):
        """Callback when scope connection successful"""
        if self.manager.getScope().getStatus():
            self.scopeStatus.setDefaultAction(self.scopeStatusActionCon)
        else:
            self.scopeStatus.setDefaultAction(self.scopeStatusActionDis)

        self.masterStatusChanged()

    def targetStatusChanged(self):
        """Callback when target connection successful"""
        if self.manager.getTarget().getStatus():
            self.targetStatus.setDefaultAction(self.targetStatusActionCon)
        else:
            self.targetStatus.setDefaultAction(self.targetStatusActionDis)

        self.masterStatusChanged()

    def setAcqPattern(self, pat, reloadList=True):
        self.acqPattern = pat
        if self.manager.hasTarget():
            self.acqPattern.setTarget(self.manager.getTarget())

        if reloadList:
            self.reloadParamList()

    def setFixedPlain(self, x):
        self.fixedPlain = x

    def getNumTraces(self):
        return self.numTraces

    def setNumTraces(self, t):
        self.numTraces = t

    def setNumSegments(self, s):
        self.numSegments = s

    def getNumSegments(self):
        return self.numSegments

    def FWLoaderGo(self):
        print "NOTE: Call to cap.FWLoaderGo() not required anymore, will be removed in future versions"

    def addExampleScripts(self):
        self.exampleScriptAct = QAction('&Example Scripts', self, statusTip='Predefined Scripts')
        self.projectMenu.addSeparator()
        self.projectMenu.addAction(self.exampleScriptAct)
        subMenu = QMenu("Submenu", self)

        for script in Manager.getExampleScripts(self._rootdir + "/scripts"):
            subMenu.addAction(QAction(script.name(), self, statusTip=script.tip(), triggered=partial(self.runScript, script)))

        self.exampleScriptAct.setMenu(subMenu)

    def runScript(self, mod):
        print("****Running Script: %s"%mod.name())
        m = mod.userScript(self)
        m.run()
        print("****Finished Script: %s"%mod.name())

    def addToolMenu(self):
        self.TerminalAct = QAction('Open Terminal', self,
                                   statusTip='Open Simple Serial Terminal',
                                   triggered=self.serialTerminal.show)

        self.toolMenu.addAction(self.TerminalAct)


        self.GlitchMonitorAct = QAction('Open Glitch Monitor', self,
                                     statusTip='Open Glitch Monitor Table',
                                     triggered=self.glitchMonitor.show)

        self.toolMenu.addAction(self.GlitchMonitorAct)

        # Keep track of add-ins
        self._scopeToolMenuItems = []


    def addWaveforms(self):
        self.waveformDock = self.addTraceDock("Capture Waveform (Channel 1)")

        #TODO: FIX THIS HACK
        #Should be something in ScopeInterface class maybe
        self.waveformDock.widget().setDefaultYRange(-0.5, 0.5)
        self.waveformDock.widget().YDefault()

    def addSettingsDocks(self):
        self.setupParametersTree()
        self.settingsNormalDock = self.addSettings(self.paramTree, "General Settings")
        self.settingsScopeDock = self.addSettings(self.scopeParamTree, "Scope Settings")
        self.settingsTargetDock = self.addSettings(self.targetParamTree, "Target Settings")
        self.settingsTraceDock = self.addSettings(self.traceParamTree, "Trace Settings")
        self.settingsAuxDock = self.addSettings(self.auxParamTree, "Aux Settings")
        self.settingsAuxDock.setVisible(False)

    def setupParametersTree(self):
        self.params = Parameter.create(name='Generic Settings', type='group', children=self.cwParams)
        ExtendedParameter.setupExtended(self.params, self)
        self.paramTree = ParameterTree()
        self.paramTree.setParameters(self.params, showTop=False)

        self.scopeParamTree = ParameterTree()
        self.targetParamTree = ParameterTree()
        self.traceParamTree = ParameterTree()
        self.auxParamTree = ParameterTree()

    def reloadScopeParamList(self, lst = None):
        # Remove all old scope actions that don't apply for new selection
        for act in self._scopeToolMenuItems:
            self.toolMenu.removeAction(act)
        self._scopeToolMenuItems = []

        if self.manager.hasScope():
            ExtendedParameter.reloadParams(self.manager.getScope().paramList(), self.scopeParamTree, help_window=self.helpbrowser.helpwnd)

            # Check for any tools to add too
            if hasattr(self.manager.getScope(), "guiActions") and len(self.manager.getScope().guiActions()) > 0:
                sep = self.toolMenu.addSeparator()
                acts = self.manager.getScope().guiActions()
                self.toolMenu.addActions(acts)
                self._scopeToolMenuItems.extend(acts)
                self._scopeToolMenuItems.append(sep)

    def reloadTargetParamList(self, lst=None):
        ExtendedParameter.reloadParams(self.manager.getTarget().paramList(), self.targetParamTree, help_window=self.helpbrowser.helpwnd)

    def reloadTraceParamList(self, lst=None):
        if self.traceparams is not None:
            try:
                ExtendedParameter.reloadParams(self.traceparams.paramList(), self.traceParamTree, help_window=self.helpbrowser.helpwnd)
            except AttributeError:
                #Some trace writers have no configuration options
                pass

    def reloadAuxParamList(self, lst=None):
        if self.auxList is not None:
            try:
                ExtendedParameter.reloadParams(self.auxList[0].paramList(), self.auxParamTree, help_window=self.helpbrowser.helpwnd)
            except AttributeError:
                # Some trace writers have no configuration options
                pass

    def reloadParamList(self, lst=None):
#        ExtendedParameter.reloadParams(self.paramList(), self.paramTree, help_window=self.helpbrowser.helpwnd)
        pass

    def paramList(self):
        p = []
        p.append(self.params)

        if self.acqPattern is not None:
            acqParams = self.acqPattern.paramList()
            for ap in acqParams:
                p.append(ap)
        return p

    def newScopeData(self,  data=None, offset=0):
        self.waveformDock.widget().passTrace(data, offset)

    def setConfigWidget(self, widget):
        self.configdock.setWidget(widget)

    def addToolbars(self):
        self.addCaptureTools()

    def addCaptureTools(self):
        self.capture1Act = QAction(QIcon(':/images/play1.png'), 'Capture 1', self)
        self.capture1Act.triggered.connect(self.capture1)
        self.capture1Act.setCheckable(True)
        self.captureMAct = QAction(QIcon(':/images/playM.png'), 'Capture Multi', self)
        self.captureMAct.triggered.connect(self.captureM)
        self.captureMAct.setCheckable(True)

        self.captureStatus = QToolButton()
        self.captureStatusActionDis = QAction(QIcon(':/images/status_disconnected.png'), 'Master: Disconnected', self)
        self.captureStatusActionDis.triggered.connect(self.doConDis)
        self.captureStatusActionCon = QAction(QIcon(':/images/status_connected.png'), 'Master: Connected', self)
        self.captureStatus.setDefaultAction(self.captureStatusActionDis)

        self.CaptureToolbar = self.addToolBar('Capture Tools')
        self.CaptureToolbar.setObjectName('Capture Toolbar')
        self.CaptureToolbar.addAction(self.capture1Act)
        self.CaptureToolbar.addAction(self.captureMAct)
        self.CaptureToolbar.addWidget(QLabel('Master:'))
        self.CaptureToolbar.addWidget(self.captureStatus)
        # Unknown bug on MAC OS X requires this + the different name for setObjectName
        self.CaptureToolbar.show()

        # Scope Toolbar
        self.scopeStatus = QToolButton()
        self.scopeStatusActionDis = QAction(QIcon(':/images/status_disconnected.png'), 'Scope: Disconnected', self)
        self.scopeStatusActionDis.triggered.connect(self.doConDisScope)
        self.scopeStatusActionCon = QAction(QIcon(':/images/status_connected.png'), 'Scope: Connected', self)
        self.scopeStatus.setDefaultAction(self.scopeStatusActionDis)

        self.ScopeToolbar = self.addToolBar('Scope Toolbar')
        self.ScopeToolbar.setObjectName('Scope Toolbar')
        self.ScopeToolbar.addWidget(QLabel('Scope:'))
        self.ScopeToolbar.addWidget(self.scopeStatus)
        self.ScopeToolbar.setEnabled(False)

        # Target Toolbar
        self.targetStatus = QToolButton()
        self.targetStatusActionDis = QAction(QIcon(':/images/status_disconnected.png'), 'Target: Disconnected', self)
        self.targetStatusActionDis.triggered.connect(self.doConDisTarget)
        self.targetStatusActionCon = QAction(QIcon(':/images/status_connected.png'), 'Target: Connected', self)
        self.targetStatus.setDefaultAction(self.targetStatusActionDis)

        self.TargetToolbar = self.addToolBar('Target Toolbar')
        self.TargetToolbar.setObjectName('Target Toolbar')
        self.TargetToolbar.addWidget(QLabel('Target:'))
        self.TargetToolbar.addWidget(self.targetStatus)
        self.TargetToolbar.setEnabled(False)

        # Other Stuff
        self.miscValidateAction = QAction(QIcon(':/images/validate.png'), 'Validate', self)
        self.miscValidateAction.triggered.connect(self.validateSettings)

        self.MiscToolbar = self.addToolBar('Misc Tools')
        self.MiscToolbar.setObjectName('Misc Tools')
        self.MiscToolbar.addAction(self.miscValidateAction)

    def doConDisScope(self):
        if self.scopeStatus.defaultAction() == self.scopeStatusActionDis:
            self.manager.connectScope()
        else:
            self.manager.disconnectScope()

    def doConDisTarget(self):
        if self.targetStatus.defaultAction() == self.targetStatusActionDis:
            self.manager.connectTarget()
        else:
            self.manager.disconnectTarget()

    def doConDis(self):
        """Toggle connect button pushed (master): attempts both target & scope connection"""
        if self.captureStatus.defaultAction() == self.captureStatusActionDis:
            self.manager.connect()
            self.statusBar().showMessage("Target and Scope Connected")
        else:
            self.manager.disconnect()
            self.statusBar().showMessage("Target and Scope Disconnected")

    def validateSettings(self, warnOnly=False):
        # Validate settings from all modules before starting multi-capture
        vw = ValidationDialog(onlyOkButton=not warnOnly)

        for i in self.manager.validateSettings():
            vw.addMessage(*i)

        if self.project().dataDirIsDefault:
             vw.addMessage("info", "File Menu", "Project not saved, using default-data-dir", "Save project file before capture", "8c9101ff-7553-4686-875d-b6a8a3b1d2ce")

        tracesPerRun = int(self.numTraces / self.numSegments)
        if tracesPerRun > 10E3:
             vw.addMessage("warn", "General Settings", "Very Long Capture (%d traces)" % tracesPerRun, "Set 'Capture Segments' to '%d'" % (self.numTraces / 10E3), "1432bf95-9026-4d8c-b15d-9e49147840eb")

        if vw.numWarnings() > 0 or warnOnly == False:
            return vw.exec_()
        else:
            return True

    def capture1(self):
        try:
            self.capture1Act.setEnabled(False)
            self.captureMAct.setEnabled(False)
            self.manager.capture1(self.auxList, self.acqPattern)
            self.statusBar().showMessage("One Capture Complete")
        except IOError, e:
            self.statusBar().showMessage("Error: %s" % str(e))
            print "Exception caught: %s" % str(e)
            print traceback.format_exc()

        self.capture1Act.setChecked(False)
        self.capture1Act.setEnabled(True)
        self.captureMAct.setEnabled(True)

    def captureM(self):
        # if self.validateSettings(True) == False:
        #     return
        self.capture1Act.setEnabled(False)
        self.captureMAct.setEnabled(False)

        cprog = CaptureProgressDialog(ntraces=self.numTraces, nsegs=self.numSegments)
        cprog.startCapture()

        try:
            self.manager.signals.traceDone.connect(cprog.traceDoneSlot)
            self.manager.captureM(self.project().datadirectory, self.numTraces, self.numSegments, self.auxList, self.acqPattern)
            self.manager.signals.traceDone.disconnect(cprog.traceDoneSlot)
        except IOError, e:
            self.statusBar().showMessage("Error: %s" % str(e))
            print "Exception caught: %s" % str(e)
            print traceback.format_exc()

        self.captureMAct.setChecked(False)
        self.capture1Act.setEnabled(True)
        self.captureMAct.setEnabled(True)

    def traceChanged(self, newTrace):
        self.manager.setTraceClass(newTrace)
        self.traceparams = newTrace.getParams
        self.reloadTraceParamList()

    def auxChanged(self, newaux):
        self.auxList = [newaux]
        try:
            newaux.paramList()
            newaux.paramListUpdated.connect(self.reloadAuxParamList)
            self.reloadAuxParamList()
            self.settingsAuxDock.setVisible(True)
        except AttributeError:
            self.settingsAuxDock.setVisible(False)
        except TypeError:
            self.settingsAuxDock.setVisible(False)

    def newProject(self):
        self.setProject(ProjectFormat(self))
        self.project().setProgramName("ChipWhisperer-Capture")
        self.project().setProgramVersion(__version__)
        self.project().addParamTree(self)
        self.project().addParamTree(self.manager.getScope())
        self.project().addParamTree(self.manager.getTarget())
        self.project().setTraceManager(self.manageTraces)
        self.setCurrentFile(None)

        # TODO: Fix this hack
        self.macWorkArounds()

    def saveProject(self):
        if self.project().hasFilename() == False :
            fd = QFileDialog.getSaveFileName(self, 'Save New File', '.','*.cwp')
            if not fd.exec_():
                return

            fname = fd.selectedFiles()[0]
            self.project().setFilename(fname)
            self.setCurrentFile(fname)

        self.project().save()
        self.dirty = False
        self.updateTitleBar()
        self.statusBar().showMessage("Project Saved")


def makeApplication():
    # Create the Qt Application
    app = QApplication(sys.argv)
    app.setOrganizationName("ChipWhisperer")
    app.setApplicationName("Capture "+__version__)
    return app

def main():
    app = makeApplication()

    # Create and show the form
    window = ChipWhispererCapture(os.path.join('chipwhisperer', 'capture'))
    window.show()

    # Run the main Qt loop
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()