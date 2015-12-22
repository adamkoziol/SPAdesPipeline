#!/usr/bin/env python
from accessoryFunctions import MetadataObject, GenObject
import os
# Import ElementTree - try first to import the faster C version, if that doesn't
# work, try to import the regular version
try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree

__author__ = 'adamkoziol'


class Metadata(object):

    def parseruninfo(self):
        """Extracts the flowcell ID, as well as the instrument name from RunInfo.xml. If this file is not provided,
        NA values are substituted"""
        # Check if the RunInfo.xml file is provided, otherwise, yield N/A
        try:
            runinfo = ElementTree.ElementTree(file="%sRunInfo.xml" % self.path)
            # pull the text from flowcell and instrument values using the .iter(tag="X") function
            for elem in runinfo.iter(tag="Flowcell"):
                self.flowcell = elem.text
            for elem in runinfo.iter(tag="Instrument"):
                self.instrument = elem.text
        except IOError:
            pass
        # Extract run statistics from either GenerateRunStatistics.xml or indexingQC.txt
        self.parserunstats()

    def parsesamplesheet(self):
        """Parses the sample sheet (SampleSheet.csv) to determine certain values
        important for the creation of the assembly report"""
        import copy
        # Initialise variables
        reads = []
        # Create and start to populate the header object
        header = GenObject()
        # Open the sample sheet
        with open("%s/SampleSheet.csv" % self.path, "rb") as samplesheet:
            # Iterate through the sample sheet
            for line in samplesheet:
                # Remove new lines, and split on commas
                data = line.rstrip().split(",")
                # Pull out the desired information from the sample sheet
                if "Investigator" in line:
                    header.investigator = data[1]
                if "Experiment" in line:
                    header.experiment = data[1].replace("  ", " ")
                if "Date" in line:
                    header.date = data[1]
                # Iterate through the file until [Reads] is encountered, then go until [Settings]
                if "Reads" in line:
                    for subline in samplesheet:
                        # Stop reading once "Settings" is encountered
                        if "Settings" in subline:
                            break
                        # Append the forward and reverse reads to the list
                        reads.append(subline.rstrip().split(",")[0])
                    # Extract the read lengths from the list of reads
                    header.forwardlength = int(reads[0])
                    header.reverselength = int(reads[1])
                if "Adapter" in line:
                    header.adapter = data[1]
                if "Sample_ID" in line:
                    for subline in samplesheet:
                        subdata = [x.rstrip() for x in subline.rstrip().split(",")]
                        # Capture Sample_ID, Sample_Name, I7_Index_ID, index1, I5_Index_ID,	index2, Sample_Project
                        # Try and replicate the Illumina rules to create file names from "Sample_Name"
                        samplename = samplenamer(subdata)
                        # Create an object for storing nested static variables
                        strainmetadata = MetadataObject()
                        # Set the sample name in the object
                        strainmetadata.name = samplename
                        # Add the header object to strainmetadata
                        strainmetadata.run = GenObject(copy.copy(header.datastore))
                        # Create the run object, so it will be easier to populate the object (eg run.SampleName = ...
                        # instead of strainmetadata.run.SampleName = ...
                        run = strainmetadata.run
                        run.SampleName = subdata[0]
                        # Comprehension to populate the run object from a stretch of subdata
                        run.I7IndexID, run.index1, run.I5IndexID, run.index2, run.Project = subdata[4:9]
                        # Append the strainmetadata object to a list
                        self.samples.append(strainmetadata)
        # print json.dumps([x.dump() for x in self.samples], sort_keys=True, indent=4, separators=(',', ': '))

    def parserunstats(self):
        """Parses the XML run statistics file (GenerateFASTQRunStatistics.xml). In some cases, the file is not
        available. Equivalent data can be pulled from Basespace.Generate a text file  name indexingQC.txt containing
        the copied tables from the Indexing QC tab of the run on Basespace"""
        # metadata = GenObject()
        # If the default file GenerateFASTQRunStatistics.xml is present, parse it
        if os.path.isfile("%sGenerateFASTQRunStatistics.xml" % self.path):
            # Create a list of keys for which values are to be extracted
            datalist = ["SampleNumber", "SampleID", "SampleName", "NumberOfClustersPF"]
            # Load the file as an xml ElementTree object
            runstatistics = ElementTree.ElementTree(file="%sGenerateFASTQRunStatistics.xml" % self.path)
            # Iterate through all the elements in the object
            # .iterfind() allow for the matching and iterating though matches
            # This is stored as a float to allow subsequent calculations
            tclusterspf = [float(element.text) for element in runstatistics.iterfind("RunStats/NumberOfClustersPF")][0]
            # Iterate through all the elements (strains) in the OverallSamples/SummarizedSampleStatistics category
            for element in runstatistics.iterfind("OverallSamples/SummarizedSampleStatistics"):
                # List comprehension. Essentially iterate through each element for each category in datalist:
                # (element.iter(category) and pull out the value for nestedelement
                straindata = [nestedelement.text for category in datalist for nestedelement in element.iter(category)]
                # Try and replicate the Illumina rules to create file names from "Sample_Name"
                samplename = samplenamer(straindata)
                # Calculate the percentage of clusters associated with each strain
                percentperstrain = "%.2f" % (float(straindata[3]) / tclusterspf * 100)
                # Use the sample number -1 as the index in the list of objects created in parsesamplesheet
                strainindex = int(straindata[0]) - 1
                # Set run to the .run object of self.samples[index]
                run = self.samples[strainindex].run
                # An assertion that compares the sample computer above to the previously entered sample name
                # to ensure that the samples are the same
                assert self.samples[strainindex].name == samplename, \
                    "Sample name does not match object name %r" % straindata[1]
                # Add the appropriate values to the strain metadata object
                run.SampleNumber = straindata[0]
                run.NumberofClustersPF = straindata[3]
                run.TotalClustersinRun = tclusterspf
                run.PercentOfClusters = percentperstrain
                run.flowcell = self.flowcell
                run.instrument = self.instrument
        elif os.path.isfile("%sindexingQC.txt" % self.path):
            from linecache import getline
            # Grab the first element from the second line in the file
            tclusterspf = float(getline("%sindexingQC.txt" % self.path, 2).split("\t")[0])
            # Open the file and extract the relevant data
            with open("%sindexingQC.txt" % self.path) as indexqc:
                # Iterate through the file
                for line in indexqc:
                    # Once "Index" is encountered, iterate through the rest of the file
                    if "Index" in line:
                        for subline in indexqc:
                            straindata = [x.rstrip() for x in subline.rstrip().split("\t")]
                            # Try and replicate the Illumina rules to create file names from "Sample_Name"
                            samplename = samplenamer(straindata, 1)
                            # Use the sample number -1 as the index in the list of objects created in parsesamplesheet
                            strainindex = int(straindata[0]) - 1
                            # Set run to the .run object of self.samples[index]
                            run = self.samples[strainindex].run
                            # An assertion that compares the sample computer above to the previously entered sample name
                            # to ensure that the samples are the same
                            assert self.samples[strainindex].name == samplename, \
                                "Sample name does not match object name %r" % straindata[1]
                            # Extract and format the percent of reads (passing filter) associated with each sample
                            percentperstrain = float("%.2f" % float(straindata[5]))
                            # Calculate the number of reads passing filter associated with each sample:
                            # percentage of reads per strain times the total reads passing filter divided by 100
                            numberofclusterspf = int(percentperstrain * tclusterspf / 100)
                            # Update the object with the variables
                            run.SampleNumber = straindata[0]
                            run.NumberofClustersPF = numberofclusterspf
                            run.TotalClustersinRun = tclusterspf
                            run.PercentOfClusters = percentperstrain
                            run.flowcell = self.flowcell
                            run.instrument = self.instrument

    def __init__(self, passed):
        """Initialise variables"""
        self.path = passed.path
        self.flowcell = "NA"
        self.instrument = "NA"
        self.samples = []
        self.ids = []
        self.date = ""
        # Extract data from SampleSheet.csv
        self.parsesamplesheet()


def samplenamer(listofdata, indexposition=0):
    """Tries to replicate the Illumina rules to create file names from 'Sample_Name'
    :param listofdata: a list of data extracted from a file
    :param indexposition:
    """
    samplename = listofdata[indexposition].rstrip().replace(" ", "-").replace(".", "-").replace("=", "-")\
        .replace("+", "").replace("/", "-").replace("#", "").replace("---", "-").replace("--", "-")
    return samplename
