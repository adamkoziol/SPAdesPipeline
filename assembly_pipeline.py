#!/usr/bin/env python3
from spadespipeline.typingclasses import GeneSippr, ResFinder, Resistance, Prophages, Plasmids, Univec, \
    Virulence
from accessoryFunctions.accessoryFunctions import MetadataObject, GenObject, printtime, make_path
from sixteenS.sixteens_full import SixteenS as SixteensFull
import spadespipeline.metadataprinter as metadataprinter
import spadespipeline.primer_finder_bbduk as vtyper
import spadespipeline.GeneSeekr as GeneSeekrMethod
import spadespipeline.runMetadata as runMetadata
from spadespipeline.basicAssembly import Basic
import spadespipeline.fastqmover as fastqmover
import spadespipeline.spadesRun as spadesRun
# import spadespipeline.compress as compress
import spadespipeline.prodigal as prodigal
import spadespipeline.reporter as reporter
import spadespipeline.versions as versions
import spadespipeline.quality as quality
import spadespipeline.quaster as quaster
import spadespipeline.univec as univec
import spadespipeline.depth as depth
import spadespipeline.sistr as sistr
from MLSTsippr.mlst import GeneSippr as MLSTSippr
from metagenomefilter import automateCLARK
from serosippr.serosippr import SeroSippr
import coreGenome.core as core
import MASHsippr.mash as mash
from argparse import ArgumentParser
from psutil import virtual_memory
import multiprocessing
from time import time
import subprocess
import gc
import os

__author__ = 'adamkoziol'


class RunSpades(object):

    def main(self):
        """
        Run the methods in the correct order
        """
        # Start the assembly
        self.helper()
        # Create the quality object
        self.create_quality_object()
        # Run the quality analyses
        self.quality()
        # Print the metadata to file
        metadataprinter.MetadataPrinter(self)
        # Perform assembly
        self.assemble()
        # Perform genus-agnostic typing
        self.agnostictyping()
        # Perform typing
        self.typing()
        # Create a report
        reporter.Reporter(self)
        '''
        compress.Compress(self)
        '''
        # Get all the versions of the software used
        versions.Versions(self)
        metadataprinter.MetadataPrinter(self)
        gc.collect()

    def helper(self):
        """Helper function for file creation (if desired), manipulation, quality assessment,
        and trimming as well as the assembly"""
        # Simple assembly without requiring accessory files (SampleSheet.csv, etc).
        if self.basicassembly:
            self.runmetadata = Basic(self)
        else:
            # Populate the runmetadata object by parsing the SampleSheet.csv, GenerateFASTQRunStatistics.xml, and
            # RunInfo.xml files
            self.runinfo = os.path.join(self.path, 'RunInfo.xml')
            self.runmetadata = runMetadata.Metadata(self)
            # Extract the flowcell ID and the instrument name if the RunInfo.xml file was provided
            self.runmetadata.parseruninfo()
            # Populate the lack of bclcall and nohup call into the metadata sheet
            for sample in self.runmetadata.samples:
                sample.commands = GenObject()
                sample.commands.nohupcall = 'NA'
                sample.commands.bclcall = 'NA'
            # Move/link the FASTQ files to strain-specific working directories
            fastqmover.FastqMover(self)
        # Print the metadata to file
        metadataprinter.MetadataPrinter(self)

    def create_quality_object(self):
        """

        :return:
        """
        # Create the quality object
        self.qualityobject = quality.Quality(self)

    def quality(self):
        """
        Creates quality objects and runs the quality assessment (FastQC), and quality trimming (bbduk) on the
        supplied sequences
        """
        # Run FastQC on the unprocessed fastq files
        self.fastqc_raw()
        # Perform quality trimming and FastQC on the trimmed files
        self.quality_trim()
        # Run FastQC on the trimmed files
        self.fastqc_trimmed()
        # Perform error correcting on the reads
        self.error_correct()
        # Detect contamination in the reads
        self.contamination_detection()
        # Run FastQC on the processed fastq files
        self.fastqc_trimmedcorrected()
        # Normalise the reads to a kmer depth of 100
        self.normalise_reads()
        # Run FastQC on the normalised fastq files
        self.fastqc_normalised()
        # Merge paired end reads into a single file based on overlap
        self.merge_reads()
        # Run FastQC on the merged fastq files
        self.fastqc_merged()
        metadataprinter.MetadataPrinter(self)
        # Exit if only pre-processing of data is requested
        if self.preprocess:
            printtime('Pre-processing complete', starttime)
            quit()

    def fastqc_raw(self):
        """

        """
        self.qualityobject.fastqcthreader('Raw')
        metadataprinter.MetadataPrinter(self)

    def quality_trim(self):
        """

        """
        # Perform quality trimming and FastQC on the trimmed files
        self.qualityobject.trimquality()
        metadataprinter.MetadataPrinter(self)

    def fastqc_trimmed(self):
        """

        """
        self.qualityobject.fastqcthreader('Trimmed')
        metadataprinter.MetadataPrinter(self)

    def error_correct(self):
        """

        """
        # Perform error correcting on the reads
        self.qualityobject.error_correction()

    def contamination_detection(self):
        """

        """
        # Calculate the levels of contamination in the reads
        self.qualityobject.contamination_finder()
        metadataprinter.MetadataPrinter(self)

    def fastqc_trimmedcorrected(self):
        """

        """
        # Run FastQC on the processed fastq files
        self.qualityobject.fastqcthreader('trimmedcorrected')
        metadataprinter.MetadataPrinter(self)

    def normalise_reads(self):
        """

        """
        # Normalise the reads to a kmer depth of 100
        self.qualityobject.normalise_reads()
        metadataprinter.MetadataPrinter(self)

    def fastqc_normalised(self):
        """

        """
        # Run FastQC on the normalised fastq files
        self.qualityobject.fastqcthreader('normalised')
        metadataprinter.MetadataPrinter(self)

    def merge_reads(self):
        """

        """
        # Merge paired end reads into a single file based on overlap
        self.qualityobject.merge_pairs()
        metadataprinter.MetadataPrinter(self)

    def fastqc_merged(self):
        """

        """
        # Run FastQC on the merged fastq files
        self.qualityobject.fastqcthreader('merged')
        metadataprinter.MetadataPrinter(self)

    def assemble(self):
        """
        Assemble genomes and perform some basic quality analyses
        """
        # Run spades
        self.run_spades()
        # Calculate the depth of coverage as well as other quality metrics using Qualimap
        self.qualimap()
        # Run quast assembly metrics
        self.quast()
        # ORF detection
        self.prodigal()
        # CLARK analyses
        self.clark()

    def run_spades(self):
        """

        """
        # Run spades
        spadesRun.Spades(self)
        metadataprinter.MetadataPrinter(self)

    def qualimap(self):
        """

        """
        # Calculate the depth of coverage as well as other quality metrics using Qualimap
        qual = depth.QualiMap(self)
        qual.main()
        metadataprinter.MetadataPrinter(self)

    def quast(self):
        """

        """
        # Run quast assembly metrics
        quaster.Quast(self)
        metadataprinter.MetadataPrinter(self)

    def prodigal(self):
        """

        """
        # ORF detection
        prodigal.Prodigal(self)
        metadataprinter.MetadataPrinter(self)

    def clark(self):
        """

        """
        # Determine the amount of physical memory in the system
        mem = virtual_memory()
        # If the total amount of memory is greater than 100GB (this could probably be lowered), run CLARK
        if mem.total >= 100000000000:
            # Run CLARK typing on the .fastq and .fasta files
            automateCLARK.PipelineInit(self)
        else:
            printtime('Not enough RAM to run CLARK!', self.starttime)

    def agnostictyping(self):
        """
        Perform typing that does not require the genus of the organism to be known
        """
        # Run mash
        mash.Mash(self, 'mash')
        # Run rMLST
        MLSTSippr(self, self.commit, self.starttime, self.homepath, 'rMLST', 1.0, True)
        metadataprinter.MetadataPrinter(self)
        # Run the 16S analyses
        SixteensFull(self, self.commit, self.starttime, self.homepath, 'sixteens_full', 0.95)
        metadataprinter.MetadataPrinter(self)
        # Find genes of interest
        GeneSippr(self, self.commit, self.starttime, self.homepath, 'genesippr', 0.8, False, False)
        metadataprinter.MetadataPrinter(self)
        # Plasmid finding
        Plasmids(self, self.commit, self.starttime, self.homepath, 'plasmidfinder', 0.8, False, True)
        # Resistance finding
        Resistance(self, self.commit, self.starttime, self.homepath, 'resfinder', 0.8, False, True)
        ResFinder(self)
        # Prophage detection
        pro = GeneSeekrMethod.PipelineInit(self, 'prophages', False, 90, True)
        Prophages(pro)
        # Univec contamination search
        uni = univec.PipelineInit(self, 'univec', False, 80, True)
        Univec(uni)
        metadataprinter.MetadataPrinter(self)
        # Virulence
        Virulence(self, self.commit, self.starttime, self.homepath, 'virulence', 0.95, False, True)
        metadataprinter.MetadataPrinter(self)

    def typing(self):
        """
        Perform analyses that use genera-specific databases
        """
        # Run modules and print metadata to file
        # MLST
        MLSTSippr(self, self.commit, self.starttime, self.homepath, 'MLST', 1.0, True)
        # Serotyping
        SeroSippr(self, self.commit, self.starttime, self.homepath, 'serosippr', 0.95, True)
        # Virulence typing
        vtyper.PrimerFinder(self, 'vtyper')
        # Core genome calculation
        coregen = GeneSeekrMethod.PipelineInit(self, 'coregenome', True, 70, False)
        core.CoreGenome(coregen)
        core.AnnotatedCore(self)
        # Sistr
        sistr.Sistr(self, 'sistr')
        metadataprinter.MetadataPrinter(self)

    def __init__(self, args, pipelinecommit, startingtime, scriptpath):
        """
        :param args: list of arguments passed to the script
        Initialises the variables required for this class
        """
        printtime('Welcome to the CFIA de novo bacterial assembly pipeline {}'.format(pipelinecommit.decode('utf-8')),
                  startingtime, '\033[1;94m')
        gc.enable()
        # Define variables from the arguments - there may be a more streamlined way to do this
        self.args = args
        self.path = os.path.join(args.path, '')
        self.reffilepath = os.path.join(args.referencefilepath)
        self.numreads = args.numreads
        self.kmers = args.kmerrange
        self.preprocess = args.preprocess
        # Define the start time
        self.starttime = startingtime
        self.customsamplesheet = args.customsamplesheet
        if self.customsamplesheet:
            assert os.path.isfile(self.customsamplesheet), 'Cannot find custom sample sheet as specified {}'\
                .format(self.customsamplesheet)

        self.basicassembly = args.basicassembly
        if not self.customsamplesheet and not os.path.isfile(os.path.join(self.path, 'SampleSheet.csv')):
            self.basicassembly = True
            printtime('Could not find a sample sheet. Performing basic assembly (no run metadata captured)',
                      self.starttime)
        # Use the argument for the number of threads to use, or default to the number of cpus in the system
        self.cpus = args.threads if args.threads else multiprocessing.cpu_count()
        # Assertions to ensure that the provided variables are valid
        make_path(self.path)
        assert os.path.isdir(self.path), 'Supplied path location is not a valid directory {0!r:s}'.format(self.path)
        self.reportpath = os.path.join(self.path, 'reports')
        assert os.path.isdir(self.reffilepath), 'Reference file path is not a valid directory {0!r:s}'\
            .format(self.reffilepath)
        self.commit = pipelinecommit.decode('utf-8')
        self.homepath = scriptpath
        self.logfile = os.path.join(self.path, 'logfile')
        self.runinfo = str()
        self.pipeline = True
        self.qualityobject = MetadataObject()
        # Initialise the metadata object
        self.runmetadata = MetadataObject()


# If the script is called from the command line, then call the argument parser
if __name__ == '__main__':
    # from .accessoryFunctions import printtime
    # Get the current commit of the pipeline from git
    # Extract the path of the current script from the full path + file name
    homepath = os.path.split(os.path.abspath(__file__))[0]
    # Find the commit of the script by running a command to change to the directory containing the script and run
    # a git command to return the short version of the commit hash
    commit = subprocess.Popen('cd {} && git tag | tail -n 1'.format(homepath),
                              shell=True, stdout=subprocess.PIPE).communicate()[0].rstrip()
    # Parser for arguments
    parser = ArgumentParser(description='Assemble genomes from Illumina fastq files')
    parser.add_argument('-v', '--version',
                        action='version', version='%(prog)s commit {}'.format(commit))
    parser.add_argument('path',
                        help='Specify path')
    parser.add_argument('-n', '--numreads',
                        default=2,
                        type=int,
                        help='Specify the number of reads. Paired-reads:'
                        ' 2, unpaired-reads: 1. Default is paired-end')
    parser.add_argument('-t', '--threads',
                        help='Number of threads. Default is the number of cores in the system')
    parser.add_argument('-r', '--referencefilepath',
                        help='Provide the location of the folder containing the pipeline accessory files (reference '
                             'genomes, MLST data, etc.')
    parser.add_argument('-k', '--kmerrange',
                        default='21,33,55,77,99,127',
                        help='The range of kmers used in SPAdes assembly. Default is 21,33,55,77,99,127')
    parser.add_argument('-c', '--customsamplesheet',
                        help='Path of folder containing a custom sample sheet and name of sample sheet file '
                             'e.g. /home/name/folder/BackupSampleSheet.csv. Note that this sheet must still have the '
                             'same format of Illumina SampleSheet.csv files')
    parser.add_argument('-b', '--basicassembly',
                        action='store_true',
                        help='Performs a basic de novo assembly, and does not collect run metadata')
    parser.add_argument('-p', '--preprocess',
                        action='store_true',
                        help='Perform quality trimming and error correction only. Do not assemble the trimmed + '
                             'corrected reads')
    # Get the arguments into an object
    arguments = parser.parse_args()
    starttime = time()
    # Run the pipeline
    pipeline = RunSpades(arguments, commit, starttime, homepath)
    pipeline.main()
    printtime('Assembly and characterisation complete', starttime)
    quit()
