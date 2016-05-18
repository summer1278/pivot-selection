"""
Forked Code from Danushka Bollegala
Implementation of SFA following steps after pivot selection
Used for evaluation of pivot selection methods
"""
import sys
import math
import numpy as np
import scipy.io as sio 
import scipy.sparse as sp
from sparsesvd import sparsesvd
import subprocess

import select_pivots as pi

def trainLBFGS(train_file, model_file):
    """
    Train lbfgs on train file. and evaluate on test file.
    Read the output file and return the classification accuracy.
    """
    retcode = subprocess.call(
        "classias-train -tb -a lbfgs.logistic -pc1=0 -pc2=1 -m %s %s > /dev/null"  %\
        (model_file, train_file), shell=True)
    return retcode


def testLBFGS(test_file, model_file):
    """
    Evaluate on the test file.
    Read the output file and return the classification accuracy.
    """
    output = "../work/output"
    retcode = subprocess.call("cat %s | classias-tag -m %s -t > %s" %\
                              (test_file, model_file, output), shell=True)
    F = open(output)
    accuracy = 0
    correct = 0
    total = 0
    for line in F:
        if line.startswith("Accuracy"):
            p = line.strip().split()
            accuracy = float(p[1])
    F.close()
    return accuracy


def getCounts(S, M, fname):
    """
    Get the feature co-occurrences in the file fname and append 
    those to the dictionary M. We only consider features in S.
    """
    count = 0
    F = open(fname)
    for line in F:
        count += 1
        #if count > 1000:
        #   break
        allP = line.strip().split()
        p = []
        for w in allP:
            if w in S:
                p.append(w) 
        n = len(p)
        for i in range(0,n):
            for j in range(i + 1, n):
                pair = (p[i], p[j])
                rpair = (p[j], p[i])
                if pair in M:
                    M[pair] += 1
                elif rpair in M:
                    M[rpair] += 1
                else:
                    M[pair] = 1
    F.close()
    pass

def selectTh(h, t):
    """
    Select all elements of the dictionary h with frequency greater than t. 
    """
    p = {}
    for (key, val) in h.iteritems():
        if val > t:
            p[key] = val
    del(h)
    return p

def getVal(x, y, M):
    """
    Returns the value of the element (x,y) in M.
    """
    if (x,y) in M:
        return M[(x,y)] 
    elif (y,x) in M:
        return M[(y,x)]
    else:
        return 0
    pass

def createMatrix(source, target, method, n):
    """
    Read the unlabeled data (test and train) for both source and the target domains. 
    Compute the full co-occurrence matrix. Drop co-occurrence pairs with a specified
    minimum threshold. For a feature w, compute its score(w),

    and sort the features in the descending order of their scores. 
    Write the co-occurrence matrix to a file with name source-target.cooc (fid, fid, cooc) and the 
    scores to a file with name source-target.pmi (feat, fid, score).
    """

    # Parameters
    domainTh = {'books':5, 'dvd':5, 'kitchen':5, 'electronics':5}
    coocTh = 5
    #n = 500

    print "Source = %s, Target = %s" % (source, target)
    
    # Load domain independent feature list 
    pivotsFile = "../work/%s-%s/obj/%s" % (source, target, method)
    features = pi.load_stored_obj(pivotsFile)
    DI = dict(features[:n]).keys()
    print "selecting top-%d features in %s as pivots" % (n, method)
    # print DI

    # Load features and get domain specific features
    feats = selectTh(dict(features),domainTh[source])
    print "total features = ", len(feats)
    # print feats.keys()

    DSList = [item for item in feats if item not in DI]
    # print len(DSList), len(feats)
    
    nDS = len(DSList)
    nDI = len(DI)
    
    # Get the union (and total frequency in both domains) for all features.
    V = feats
    # Compute the co-occurrences of features in reviews
    M = {}
    print "Vocabulary size =", len(V)
    getCounts(V, M, "../data/%s/train.positive" % source)
    print "%s positive %d" % (source, len(M)) 
    getCounts(V, M, "../data/%s/train.negative" % source)
    print "%s negative %d" % (source, len(M))
    getCounts(V, M, "../data/%s/train.unlabeled" % source)
    print "%s unlabeled %d" % (source, len(M))
    getCounts(V, M, "../data/%s/train.positive" % target)
    print "%s positive %d" % (target, len(M))   
    getCounts(V, M, "../data/%s/train.negative" % target)
    print "%s negative %d" % (target, len(M))   
    getCounts(V, M, "../data/%s/train.unlabeled" % target)
    print "%s unlabeled %d" % (target, len(M))  
    # Remove co-occurrence less than the coocTh
    M = selectTh(M, coocTh)

    # Compute matrix DSxSI and save it. 
    R = np.zeros((nDS, nDI), dtype=np.float)
    for i in range(0, nDS):
        for j in range(0, nDI):
            val = getVal(DSList[i], DI[j], M)
            if val > coocTh:
                R[i,j] = val
    print "Writing DSxDI.mat...",
    sio.savemat("../work/%s-%s/DSxDI.mat" % (source, target), {'DSxDI':R})
    print "Done"
    pass

def learnProjection(sourceDomain, targetDomain):
    """
    Learn the projection matrix and store it to a file. 
    """
    h = 50 # no. of latent dimensions.
    print "Loading the bipartite matrix...",
    coocData = sio.loadmat("../work/%s-%s/DSxDI.mat" % (sourceDomain, targetDomain))
    M = sp.lil_matrix(coocData['DSxDI'])
    (nDS, nDI) = M.shape
    print "Done."
    print "Computing the Laplacian...",
    D1 = sp.lil_matrix((nDS, nDS), dtype=np.float64)
    D2 = sp.lil_matrix((nDI, nDI), dtype=np.float64)
    for i in range(0, nDS):
        D1[i,i] = 1.0 / np.sqrt(np.sum(M[i,:].data[0]))
    for i in range(0, nDI):
        D2[i,i] = 1.0 / np.sqrt(np.sum(M[:,i].T.data[0]))
    B = (D1.tocsr().dot(M.tocsr())).dot(D2.tocsr())
    print "Done."
    print "Computing SVD...",
    ut, s, vt = sparsesvd(B.tocsc(), h)
    sio.savemat("../work/%s-%s/proj.mat" % (sourceDomain, targetDomain), {'proj':ut.T})
    print "Done."    
    pass


def evaluate_SA(source, target, project,n):
    """
    Report the cross-domain sentiment classification accuracy. 
    """
    gamma = 1.0
    print "Source Domain", source
    print "Target Domain", target
    if project:
        print "Projection ON", "Gamma = %f" % gamma
    else:
        print "Projection OFF"
    # Load the projection matrix.
    M = sp.csr_matrix(sio.loadmat("../work/%s-%s/proj.mat" % (source, target))['proj'])
    (nDS, h) = M.shape
    # Load the domain specific features.
    pivotsFile = "../work/%s-%s/obj/%s" % (source, target, method)
    features = pi.load_stored_obj(pivotsFile)
    DSfeat = dict(features[:n])
    
    # write train feature vectors.
    trainFileName = "../work/%s-%s/trainVects.SFA" % (source, target)
    testFileName = "../work/%s-%s/testVects.SFA" % (source, target)
    featFile = open(trainFileName, 'w')
    count = 0
    for (label, fname) in [(1, 'train.positive'), (-1, 'train.negative')]:
        F = open("../data/%s/%s" % (source, fname))
        for line in F:
            count += 1
            #print "Train ", count
            words = set(line.strip().split())
            # write the original features.
            featFile.write("%d " % label)
            x = sp.lil_matrix((1, nDS), dtype=np.float64)
            for w in words:
                #featFile.write("%s:1 " % w)
                if w in DSfeat:
                    x[0, DSfeat[w] - 1] = 1
            # write projected features.
            if project:
                y = x.tocsr().dot(M)
                for i in range(0, h):
                    featFile.write("proj_%d:%f " % (i, gamma * y[0,i])) 
            featFile.write("\n")
        F.close()
    featFile.close()
    # write test feature vectors.
    featFile = open(testFileName, 'w')
    count = 0
    for (label, fname) in [(1, 'test.positive'), (-1, 'test.negative')]:
        F = open("../data/%s/%s" % (target, fname))
        for line in F:
            count += 1
            #print "Test ", count
            words = set(line.strip().split())
            # write the original features.
            featFile.write("%d " % label)
            x = sp.lil_matrix((1, nDS), dtype=np.float64)
            for w in words:
                #featFile.write("%s:1 " % w)
                if w in DSfeat:
                    x[0, DSfeat[w] - 1] = 1
            # write projected features.
            if project:
                y = x.dot(M)
                for i in range(0, h):
                    featFile.write("proj_%d:%f " % (i, gamma * y[0,i])) 
            featFile.write("\n")
        F.close()
    featFile.close()
    # Train using classias.
    modelFileName = "../work/%s-%s/model.SFA" % (source, target)
    trainLBFGS(trainFileName, modelFileName)
    # Test using classias.
    acc = testLBFGS(testFileName, modelFileName)
    print "Accuracy =", acc
    print "###########################################\n\n"
    return acc


def batchEval():
    """
    Evaluate on all 12 domain pairs. 
    """
    resFile = open("../work/batchSFA.csv", "w")
    domains = ["books", "electronics", "dvd", "kitchen"]
    resFile.write("Source, Target, NoProj, Proj\n")
    for source in domains:
        for target in domains:
            if source == target:
                continue
            createMatrix(source, target)
            learnProjection(source, target)
            resFile.write("%s, %s, %f, %f\n" % (source, target, 
                evaluate_SA(source, target, False), evaluate_SA(source, target, True)))
            resFile.flush()
    resFile.close()
    pass

if __name__ == "__main__":
    source = "electronics"
    target = "dvd"
    method = "freq"
    #generateFeatureVectors("books")
    #generateFeatureVectors("dvd")
    #generateFeatureVectors("electronics")
    #generateFeatureVectors("kitchen")
    #generateAll()
    createMatrix(source, target, method, 500)
    learnProjection(source, target)
    #evaluate_SA(source, target, False)
    evaluate_SA(source, target, True,500)
    # batchEval()