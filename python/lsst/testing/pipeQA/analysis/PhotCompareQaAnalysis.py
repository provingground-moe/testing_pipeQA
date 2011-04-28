import sys, os, re
import lsst.meas.algorithms        as measAlg
import lsst.testing.pipeQA.figures as qaFig
import numpy

import lsst.afw.math                as afwMath
import lsst.testing.pipeQA.TestCode as testCode

import QaAnalysis as qaAna
import RaftCcdData as raftCcdData
import QaAnalysisUtils as qaAnaUtil

import matplotlib.cm as cm
import matplotlib.colors as colors
import matplotlib.font_manager as fm

class PhotCompareQaAnalysis(qaAna.QaAnalysis):

    def __init__(self, magType1='psf', magType2='aperture', cut=20.0):
	testLabel = magType1+"-"+magType2
	qaAna.QaAnalysis.__init__(self, testLabel)

	self.cut = cut
	
	def magType(mType):
	    if re.search("(psf|PSF)", mType):
		return "psf"
	    elif re.search("^ap", mType):
		return "ap"
	    elif re.search("^mod", mType):
		return "mod"
	    elif re.search("^cat", mType):
		return "cat"

	self.magType1 = magType(magType1)
	self.magType2 = magType(magType2)


    def _getFlux(self, mType, s, sref):
	if mType=="psf":
	    return s.getPsfFlux()
	elif mType=="ap":
	    return s.getApFlux()
	elif mType=="mod":
	    return s.getModelFlux()
	elif mType=="cat":
	    return sref.getPsfFlux()
	

    def test(self, data, dataId):
	
	# get data
	self.detector      = data.getDetectorBySensor(dataId)
	self.filter        = data.getFilterBySensor(dataId)
	
	self.diff = raftCcdData.RaftCcdVector(self.detector)
	self.mag  = raftCcdData.RaftCcdVector(self.detector)

	filter = None

	# if we're asked to compare catalog fluxes ... we need a matchlist
	if  self.magType1=="cat" or self.magType2=="cat":
	    self.matchListDict = data.getMatchListBySensor(dataId)
	    for key, matchList in self.matchListDict.items():
		raft = self.detector[key].getParent().getId().getName()
		ccd  = self.detector[key].getId().getName()
		filter = self.filter[key].getName()

		for m in matchList:
		    sref, s, dist = m
		    
		    f1 = self._getFlux(self.magType1, s, sref)
		    f2 = self._getFlux(self.magType2, s, sref)

		    if not (s.getFlagForDetection() & measAlg.Flags.INTERP_CENTER ):
			m1 = -2.5*numpy.log10(f1)
			m2 = -2.5*numpy.log10(f2)

			if numpy.isfinite(m1) and numpy.isfinite(m2):
			    self.diff.append(raft, ccd, m1 - m2)
			    self.mag.append(raft, ccd, m1)

	# if we're not asked for catalog fluxes, we can just use a sourceSet
	else:
	    self.ssDict        = data.getSourceSetBySensor(dataId)
	    for key, ss in self.ssDict.items():
		raft = self.detector[key].getParent().getId().getName()
		ccd  = self.detector[key].getId().getName()

		filter = self.filter[key].getName()

		qaAnaUtil.isStar(ss)  # sets the 'STAR' flag
		for s in ss:
		    f1 = self._getFlux(self.magType1, s, s)
		    f2 = self._getFlux(self.magType2, s, s)
		    
		    if ((f1 > 0.0 and f2 > 0.0) and
			not (s.getFlagForDetection() & measAlg.Flags.INTERP_CENTER )):
			#(s.getFlagForDetection() & measAlg.Flags.STAR)):

			m1 = -2.5*numpy.log10(f1) #self.calib[key].getMagnitude(f1)
			m2 = -2.5*numpy.log10(f2) #self.calib[key].getMagnitude(f2)

			self.diff.append(raft, ccd, m1 - m2)
			self.mag.append(raft, ccd, m2)


		    
	group = dataId['visit']
	testSet = self.getTestSet(group, label=self.magType1+"-"+self.magType2)
	testSet.addMetadata('dataset', data.getDataName())
	testSet.addMetadata('visit', dataId['visit'])
	testSet.addMetadata('filter', filter)
	testSet.addMetadata('magType1', self.magType1)
	testSet.addMetadata('magType2', self.magType2)

	self.means = raftCcdData.RaftCcdData(self.detector)
	self.medians = raftCcdData.RaftCcdData(self.detector)
	self.stds  = raftCcdData.RaftCcdData(self.detector)

	for raft,  ccd in self.mag.raftCcdKeys():
	    dmag = self.diff.get(raft, ccd)
	    mag = self.mag.get(raft, ccd)
	    w = numpy.where((mag > 10) & (mag < self.cut))
	    dmag = dmag[w]

	    if len(dmag) > 0:
		stat = afwMath.makeStatistics(dmag, afwMath.NPOINT | afwMath.MEANCLIP |
					      afwMath.STDEVCLIP | afwMath.MEDIAN)
		mean = stat.getValue(afwMath.MEANCLIP)
		median = stat.getValue(afwMath.MEDIAN)
		std = stat.getValue(afwMath.STDEVCLIP)
		n = stat.getValue(afwMath.NPOINT)

	    else:
		# already using NaN for 'no-data' for this ccd
		#  (because we can't test for 'None' in a numpy masked_array)
		# unfortunately, these failures will have to do
		mean = 99.0
		median = 99.0
		std = 99.0
		n = 0

	    tag = self.magType1+"_vs_"+self.magType2
	    dtag = self.magType1+"-"+self.magType2
	    self.means.set(raft, ccd, mean)
	    label = "mean "+tag +" " + re.sub("\s+", "_", ccd)
	    comment = "mean "+dtag+" (mag lt %.1f, nstar/clip=%d/%d)" % (self.cut, len(dmag),n)
	    testSet.addTest( testCode.Test(label, mean, [-0.02, 0.02], comment) )

	    self.medians.set(raft, ccd, median)
	    label = "median "+tag+" "+re.sub("\s+", "_", ccd)
	    comment = "median "+dtag+" (mag lt %.1f, nstar/clip=%d/%d)" % (self.cut, len(dmag), n)
	    testSet.addTest( testCode.Test(label, median, [-0.02, 0.02], comment) )

	    self.stds.set(raft, ccd, std)
	    label = "stdev "+tag+" " + re.sub("\s+", "_", ccd)
	    comment = "stdev of "+dtag+" (mag lt %.1f, nstar/clip=%d/%d)" % (self.cut, len(dmag), n)
	    testSet.addTest( testCode.Test(label, std, [0.0, 0.02], comment) )
		


    def plot(self, data, dataId, showUndefined=False):

	group = dataId['visit']
	testSet = self.getTestSet(group, label=self.magType1+"-"+self.magType2)

	# fpa figure
	meanFig = qaFig.FpaQaFigure(data.cameraInfo.camera)
	stdFig = qaFig.FpaQaFigure(data.cameraInfo.camera)
	for raft, ccdDict in meanFig.data.items():
	    for ccd, value in ccdDict.items():
		meanFig.data[raft][ccd] = self.means.get(raft, ccd)
		stdFig.data[raft][ccd] = self.stds.get(raft, ccd)
		if not self.means.get(raft, ccd) is None:
		    meanFig.map[raft][ccd] = "mean=%.4f" % (self.means.get(raft, ccd))
		    stdFig.map[raft][ccd] = "std=%.4f" % (self.stds.get(raft, ccd))

	tag = "m$_{"+self.magType1+"}$-m$_{"+self.magType2+"}$"
	dtag = self.magType1+"-"+self.magType2
	wtag = self.magType1+"minus"+self.magType2
	meanFig.makeFigure(showUndefined=showUndefined, cmap="RdBu_r", vlimits=[-0.02, 0.02],
			   title="Mean "+tag)
	testSet.addFigure(meanFig, "mean"+wtag+".png", "mean "+dtag+" mag   (brighter than %.1f)" % (self.cut),
			  saveMap=True, navMap=True)
	stdFig.makeFigure(showUndefined=showUndefined, cmap="YlOrRd", vlimits=[0.0, 0.03],
			  title="Stdev "+tag)
	testSet.addFigure(stdFig, "std"+wtag+".png", "stdev "+dtag+" mag  (brighter than %.1f)" % (self.cut),
			  saveMap=True, navMap=True)
	

	# dmag vs mag
	figsize = (6.5, 3.75)
	fig0 = qaFig.QaFig(size=figsize)
	fig0.fig.subplots_adjust(left=0.125, bottom=0.125)
	ax0_1 = fig0.fig.add_subplot(121)
	ax0_2 = fig0.fig.add_subplot(122)
	
	nKeys = len(self.mag.raftCcdKeys())
	norm = colors.Normalize(vmin=0, vmax=nKeys)
	sm = cm.ScalarMappable(norm, cmap=cm.jet)

	xlim = [14.0, 25.0]
	ylim = [-0.4, 0.4]

	conv = colors.ColorConverter()
	red = conv.to_rgba('r')
	black = conv.to_rgba('k')
	size = 1.0
	
	i = 0
	xmin, xmax = self.mag.summarize('min'), self.mag.summarize('max')
	ymin, ymax = self.diff.summarize('min'), self.diff.summarize('max')
	xrang = xmax-xmin
	xmin, xmax = xmin-0.05*xrang, xmax+0.05*xrang
	yrang = ymax-ymin
	ymin, ymax = ymin-0.05*yrang, ymax+0.05*yrang
	xlim2 = [xmin, xmax]
	ylim2 = [ymin, ymax]

	for raft, ccd in self.mag.raftCcdKeys():
	    mag  = self.mag.get(raft, ccd)
	    diff = self.diff.get(raft, ccd)

	    whereCut = numpy.where(mag < self.cut)

	    print "plotting ", ccd

	    #################
	    # data for one ccd
	    fig = qaFig.QaFig(size=figsize)
	    fig.fig.subplots_adjust(left=0.125, bottom=0.125)
	    ax_1 = fig.fig.add_subplot(121)
	    ax_2 = fig.fig.add_subplot(122)
	    clr = [black] * len(mag)
	    clr = numpy.array(clr)
	    clr[whereCut] = [red] * len(whereCut)

	    tag1 = "m$_{"+self.magType1+"}$"
	    for ax in [ax_1, ax_2]:
		ax.scatter(mag, diff, size, color=clr, label=ccd)
		ax.set_xlabel(tag1)
		
	    ax_2.plot([xlim[0], xlim[1], xlim[1], xlim[0], xlim[0]],
		      [ylim[0], ylim[0], ylim[1], ylim[1], ylim[0]], '-k')
	    ax_1.set_ylabel(tag)
	    ax_1.set_xlim(xlim)
	    ax_2.set_xlim(xlim2)
	    ax_1.set_ylim(ylim)
	    ax_2.set_ylim(ylim2)

	    # move the y axis on right panel
	    ax_2dummy = ax_2.twinx()
	    ax_2dummy.set_ylim(ax_2.get_ylim())
	    ax_2.set_yticks([])
	    ax_2dummy.set_ylabel(tag)

	    label = re.sub("\s+", "_", ccd)
	    testSet.addFigure(fig, "diff_"+dtag+"_"+label+".png",
			      dtag+" vs. "+self.magType1 + ". Point used for statistics shown in red.")


	    ####################
	    # data for all ccds
	    color = sm.to_rgba(i)
	    for ax in [ax0_1, ax0_2]:
		ax.scatter(mag, diff, size, color=color, label=ccd)
	    ax0_1.set_xlim(xlim)
	    ax0_2.set_xlim(xlim2)
	    ax0_1.set_ylim(ylim)
	    ax0_2.set_ylim(ylim2)

	    dmag = 0.1
	    ddiff1 = 0.02
	    ddiff2 = ddiff1*(ylim2[1]-ylim2[0])/(ylim[1]-ylim[0]) # rescale for larger y range
	    for j in range(len(mag)):
		area = (mag[j]-dmag, diff[j]-ddiff1, mag[j]+dmag, diff[j]+ddiff1)
		fig0.addMapArea(label, area, "%.3f_%.3f"% (mag[j], diff[j]), axes=ax0_1)
		area = (mag[j]-dmag, diff[j]-ddiff2, mag[j]+dmag, diff[j]+ddiff2)
		fig0.addMapArea(label, area, "%.3f_%.3f"% (mag[j], diff[j]), axes=ax0_2)
	    i += 1



	# move the yaxis ticks/labels to the other side
	ax0_2dummy = ax0_2.twinx()
	ax0_2dummy.set_ylim(ax0_2.get_ylim())
	ax0_2.set_yticks([])

	ax0_2.plot([xlim[0], xlim[1], xlim[1], xlim[0], xlim[0]],
		  [ylim[0], ylim[0], ylim[1], ylim[1], ylim[0]], '-k')
	ax0_2.set_xlim(xlim2)
	ax0_2.set_ylim(ylim2)

	for ax in [ax0_1, ax0_2dummy]:
	    ax.set_xlabel(tag1)
	    ax.set_ylabel(tag)

	    
	testSet.addFigure(fig0, "diff_"+dtag+"_all.png", dtag+" vs. "+self.magType1, saveMap=True)

