#!/usr/bin/env python

import ROOT
ROOT.gROOT.SetBatch(True)
from ROOT import *

import os,re,sys,math

import MNTriggerStudies.MNTriggerAna.Util

from array import array
import resource
import time

import multiprocessing

class FitThread(multiprocessing.Process):
    def __init__(self, inputMap):
        super(FitThread, self).__init__()
        self.inputMap = inputMap

    def run(self):
        inputMap = self.inputMap
        canvas = ROOT.TCanvas()
        #dsReduced = inputMap["dsReduced"]

        dsReduced =  inputMap["ds"].reduce(inputMap["cut"])
        myVar = inputMap["myVar"]

        #myVar = vars[t][vary("balance")]
        meanVal = dsReduced.mean(myVar)
        sigma   = dsReduced.sigma(myVar)

        print "XXXXX", meanVal, sigma

        #rangeLow = meanVal - sigma*0.75
        #rangeHigh = meanVal + sigma*0.75
        rangeLow = meanVal - sigma*1.5
        rangeHigh = meanVal + sigma*1.5

        mean2 = RooRealVar("mean","mean of gaussian", 0, -1.5, 1.5)
        sigma2 = RooRealVar("sigma","width of gaussian", .1, 0, 1)
        gauss2 = RooGaussian("gauss","gaussian PDF",myVar, mean2, sigma2)
        gauss2.fitTo(dsReduced, ROOT.RooFit.Range(rangeLow, rangeHigh), ROOT.RooFit.PrintLevel(-1)) # this exludes -1 point ("no jet matched point")

        balanceVariable = "diJet balance"
        frame = myVar.frame(ROOT.RooFit.Range(-1.5,1))
        frame.GetXaxis().SetTitle(balanceVariable)
        #sampleList[s]["RooDS"].plotOn(frame)
        dsReduced.plotOn(frame)
        gauss2.plotOn(frame)

        gauss2.paramOn(frame, ROOT.RooFit.Layout(0.2, 0.5,0.95)) # , RooFit.Label("Gauss Fit"))

        # myVar = treeReader.variables[balanceVariable]["RooVar"]
        ptProbeJetVar = inputMap["ptProbeJetVar"]
        meanPT = dsReduced.mean(ptProbeJetVar)
        sigmaPT = dsReduced.sigma(ptProbeJetVar)

        etaMin = inputMap["etaMin"]
        etaMax = inputMap["etaMax"]
        minPtAVG = inputMap["minPtAVG"] 

        box = ROOT.TPaveText(0.2,0.45, 0.50, 0.8, "BRNDC")
        box.SetFillColor(0)
        #box.AddText(tag)
        box.AddText("avg(p^{probe}_{T})=%10.2f" % meanPT)
        box.AddText("\sigma(p^{probe}_{T})=%10.2f" % sigmaPT )
        box.AddText(str(etaMin) + " < |#eta_{probe}| < "+str(etaMax))
        box.AddText("p_{T}^{ave} > "+str(minPtAVG))
        #box.AddText("probe jet p_{T} > "+str(minPtAVG))

        frame.addObject(box)
        frame.Draw()
        odir = "~/tmp/balance/"
        preName = odir + myVar.GetName() + "_" + inputMap["name"] + "_ptAveMin_" + str(minPtAVG)  \
        + "_etaMin_" + str(etaMin).replace(".", "_") \
        + "_etaMax_" + str(etaMax).replace(".", "_") 
        #+ "_" + tag
        fname = preName + "__2.png"
        canvas.Print(fname)

        fitResult = {}
        fitResult["iEta"] = inputMap["iEta"]
        fitResult["mean"]      = mean2.getVal()
        fitResult["meanErr"] = mean2.getError()
        fitResult["gaussWidth"] = sigma2.getVal()
        fitResult["gaussWidthErr"] = sigma2.getError()
        self.queue.put(fitResult)


def main():

    sampleList=MNTriggerStudies.MNTriggerAna.Util.getAnaDefinition("sam")

    infile = "treeDiJetBalance.root"

    f = ROOT.TFile(infile, "r")
    lst = f.GetListOfKeys()


    trees = {}
    trees["MC_jet15"] = []
    trees["data_jet15"] = []

    samplesData = ["Jet-Run2010B-Apr21ReReco-v1", "JetMETTau-Run2010A-Apr21ReReco-v1", "JetMET-Run2010A-Apr21ReReco-v1"]

    for l in lst:
        #print "Going through", l.GetName(), l.ClassName()
        currentDir = l.ReadObj()

        if not currentDir:
            print "Problem reading", l.GetName(), " - skipping"
            continue

        if type(currentDir) != ROOT.TDirectoryFile:
            print "Expected TDirectoryFile,", type(currentDir), "found"
            continue

        sampleName = l.GetName()
        if sampleName not in sampleList:
            raise Exception("Thats confusing...")
        tree = currentDir.Get("data")
        isData = sampleList[sampleName]["isData"]
        if isData:
            if sampleName in samplesData:
                #tree.SetDirectory(0)
                trees["data_jet15"].append(tree)
                
        else:
            #tree.SetDirectory(0)
            trees["MC_jet15"].append(tree)

        print sampleName, tree.GetEntries()

        #print d

    dummyFile = ROOT.TFile("/tmp/dummy.root", "recreate")
    for t in trees:
        tlist = ROOT.TList()
        if len(trees[t]) == 1 and False:
            trees[t] = trees[t][0]
        else:
            for tree in trees[t]:
                tlist.Add(tree)
            trees[t] =  ROOT.TTree.MergeTrees(tlist)
            print "data tree after merge: ", trees[t].GetEntries()


    vars = {} # note: we whave to save the variables outside the loop, otherwise they get
              #       garbage collected by python leading to a crash

    ds = {}

    variations = set()


    for t in trees:
        print "RooDataset:",t
        vars[t] = {}
        tree = trees[t]
        observables = ROOT.RooArgSet()
        print "  min/max"
        for b in tree.GetListOfBranches():
            name =  b.GetName()
            if name != "weight":
                variation = name.split("_")[-1]
                variations.add(variation)

            rmin = tree.GetMinimum(name)
            rmax = tree.GetMaximum(name)
            rmin = rmin-abs(rmin/100.)
            rmax = rmax+abs(rmin/100.)
            #print name, rmin, rmax
            roovar = ROOT.RooRealVar( name, name, rmin, rmax, "")
            vars[t][name] = roovar
            print "Creating variable", name, type(roovar)
            sys.stdout.flush()
            observables.add(roovar)
        #importCMD = RooFit.Import(tree)
        #cutCMD = RooFit.Cut(preselectionString)
        print "  create dataset..."
        ds[t] = ROOT.RooDataSet(t, t, tree, observables, "", "weight")
        print "        ...done"

        print "Dataset:", t, ds[t].numEntries()

    if "central" not in variations:
        raise Exception("Central value not found!")


    etaRanges = []
    etaRanges.extend([1.401, 1.701, 2.001, 2.322, 2.411, 2.601, 2.801, 3.001, 3.201, 3.501, 3.801, 4.101, 4.701])
    #etaRanges.extend([4.101, 4.701])
    minPtAVG = 45


    curPath = ROOT.gDirectory.GetPath()
    of = ROOT.TFile("~/tmp/balanceHistos.root","RECREATE")
    outputHistos = {}
    outputHistos["data_jet15"] = of.mkdir("data_jet15")
    outputHistos["MC_jet15"] = of.mkdir("MC_jet15")
    ROOT.gDirectory.cd(curPath)
    
    for t in ds:
        for v in variations:

            queue = multiprocessing.Queue()
            if t=="data_jet15" and v != "central":
                continue


            myThreads = []
            results = []
            for iEta in xrange(1, len(etaRanges)):
                etaMin = etaRanges[iEta-1]
                etaMax = etaRanges[iEta]
                print "Doing", t, v, etaMin, etaMax

                def vary(x, v=v):
                    return x + "_" + v

                cut = vary("tagPt") + " > 35"
                cut += " && " + vary("probePt") + " > 35 "
                cut += " && abs(" + vary("probeEta") + ") >  " + str(etaMin)
                cut += " && abs(" + vary("probeEta") + ") <  " + str(etaMax)
                cut += " && " + vary("ptAve") + " > " + str(minPtAVG)
                print cut

                #print "Reduce"
                #dsReduced = ds[t].reduce(cut)
                #print "Reduce...done"
            

                inputMap = {}
                inputMap["name"] = t
                #inputMap["dsReduced"] = dsReduced
                #inputMap["ds"] =  ds[t].Clone()
                inputMap["ds"] =  ds[t]
                inputMap["myVar"] = vars[t][vary("balance")]
                inputMap["ptProbeJetVar"] = vars[t][vary("probePt")]
                inputMap["etaMin"] = etaMin
                inputMap["etaMax"] = etaMax
                inputMap["minPtAVG"] = minPtAVG
                inputMap["iEta"] = iEta # xcheck only
                inputMap["cut"] = cut


                thr = FitThread(inputMap)
                thr.queue = queue
                thr.start()
                myThreads.append(thr)
                #ptProbeJetVar
                #fitResult = fit(inputMap)
                #results.append(fitResult)

                #t = threading.Thread(target=fit, args = (dsReduced, queue))
                #t.daemon = False
                #t.start()

            for thr in myThreads:
                print "Joining!"
                thr.join()
                ret = queue.get()
                print ret
                results.append(ret)
            #sys.exit()            


            # all etas done. Create summary (vs eta) histogram
            etaArray = array('d', etaRanges)
            histName = "balance_"+v + "_jet15"
            #print etaRanges
            #print etaArray
            hist = ROOT.TH1F(histName, histName, len(etaArray)-1, etaArray)
            for i in xrange(len(results)):
                res = results[i]
                iEta = res["iEta"]
                etaMin = etaRanges[iEta-1]
                etaMax = etaRanges[iEta]
                etaAvg = (etaMin+etaMax)/2.
                bin = hist.FindBin(etaAvg)
                if bin != iEta:
                    print bin, iEta, etaAvg
                    raise Exception("Problem with binning")
                hist.SetBinContent(bin, res["mean"])
                hist.SetBinError(bin, res["meanErr"])
            outputHistos[t].WriteTObject(hist,histName)


        # all variations done








    #print "Sleep"
    #time.sleep(60)
    #print "Meminfo:", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    #todo = {}
    #todo["MC"] = 
    #                 branches =  current.GetListOfBranches()


                




if __name__ == "__main__":
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
    ROOT.gSystem.Load("libFWCoreFWLite.so")
    AutoLibraryLoader.enable()
    main()
    print "./drawPlots.py -s -i ~/tmp/balanceHistos.root"

