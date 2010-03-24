#
#    Copyright (c) 2009, 2010 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
#    $Revision$
#    $Author$
#    $Date$
#
"""Engine for generating reports"""

import os.path
import glob
import shutil
import syslog
import threading

import configobj

import weewx.archive
import weewx.genfiles
import weewx.genimages
import weewx.ftpdata
import weeutil.weeutil

class StdReportEngine(threading.Thread):
    """Reporting engine for weewx.
    
    This engine runs zero or more reports. Each report uses a skin. A skin
    has its own configuration file specifying things such as which 'generators'
    should be run, which templates are to be used, what units are to be used, etc.. 
    A 'generator' is a class inheriting from class ReportGenerator, that produces the parts
    of the report, such as image plots, HTML files. 
    
    StdReportEngine inherits from threading.Thread, so it will be run in a separate
    thread.
    
    See below for examples of generators.
    """
    
    def __init__(self, config_dict, gen_ts = None, first_run = True):
        """Initializer for the report engine. 
        
        config_dict: the configuration dictionary.
        
        gen_ts: The timestamp for which the output is to be current [Optional; default
        is the last time in the database]
        
        first_run: True if this is the first time the report engine has been run.
        If this is the case, then any 'one time' events should be done.
        """
        threading.Thread.__init__(self, name="ReportThread")
        self.config_dict = config_dict
        self.gen_ts      = gen_ts
        self.first_run   = first_run
        
    def setup(self):
        if self.gen_ts:
            syslog.syslog(syslog.LOG_DEBUG, "reportengine: Running reports for time %s" % 
                          weeutil.weeutil.timestamp_to_string(self.gen_ts))
        else:
            syslog.syslog(syslog.LOG_DEBUG, "reportengine: Running reports for latest time in the database.")
        
    
    def run(self):
        """This is where the actual work gets done.
        
        Runs through the list of reports. """
        
        self.setup()

        # Iterate over each requested report
        for report in self.config_dict['Reports'].sections:
            
            syslog.syslog(syslog.LOG_DEBUG, "reportengine: Running report %s" % report)
            
            # Figure out where the configuration file is for the skin used for this report:
            skin_config_path = os.path.join(self.config_dict['Station']['WEEWX_ROOT'],
                                            self.config_dict['Reports']['SKIN_ROOT'],
                                            self.config_dict['Reports'][report].get('skin', 'Standard'),
                                            'skin.conf')
            # Retrieve the configuration dictionary for the skin. Wrap it in a try
            # block in case we fail
            try :
                skin_dict = configobj.ConfigObj(skin_config_path, file_error=True)
                syslog.syslog(syslog.LOG_DEBUG, "reportengine: Found configuration file %s for report %s" % (skin_config_path, report))
            except IOError:
                syslog.syslog(syslog.LOG_INFO, "reportengine: No skin configuration file for report %s" % report)
                syslog.syslog(syslog.LOG_INFO, "        ****  Report ignored...")
                continue
                
            # Inject any overrides the user may have specified in the weewx.conf
            # configuration file for all reports:
            for scalar in self.config_dict['Reports'].scalars:
                skin_dict[scalar] = self.config_dict['Reports'][scalar]
            
            # Now inject any overrides for this specific report:
            skin_dict.merge(self.config_dict['Reports'][report])
            
            # If this is the first time the report engine has been run, then
            # run the 'singleton list' of generators.
            if self.first_run and skin_dict.has_key('singleton_list'):
                    singleton_list = skin_dict.as_list('singleton_list')
                    self.runGenerators(skin_dict, singleton_list)

            # Now run all the regular generators:
            self.runGenerators(skin_dict, skin_dict.as_list('generator_list'))
            
    def runGenerators(self, skin_dict, generator_list):
        """Runs a list of generators.
        skin_dict: The skin dictionary the list is to be run against.
        
        generator_list: A list of generators to be run. Each generator should
        be a class with a method "start()". The initializer of the class should
        take arguments (config_dict, skin_dict, gen_ts).
        """
        
        for generator in generator_list:
            try:
                # Instantiate an instance of the class.
                obj = weeutil.weeutil._get_object(generator, self.config_dict, skin_dict, self.gen_ts)
            except ValueError, e:
                syslog.syslog(syslog.LOG_CRIT, "reportengine: Unable to instantiate generator %s." % generator)
                syslog.syslog(syslog.LOG_CRIT, "        ****  %s" % e)
                syslog.syslog(syslog.LOG_CRIT, "        ****  Generator ignored...")
                continue

            try:
                # Call its start() method
                obj.start()
            except Exception, e:
                # Caught unrecoverable error. Log it, exit
                syslog.syslog(syslog.LOG_CRIT, "reportengine: Caught unrecoverable exception in generator %s" % generator)
                syslog.syslog(syslog.LOG_CRIT, "        ****  %s" % e)
                syslog.syslog(syslog.LOG_CRIT, "        ****  Thread exiting.")
                # Reraise the exception (this will eventually cause the thread to terminate)
                raise


class ReportGenerator(object):
    """Base class for all report generators."""
    def __init__(self, config_dict, skin_dict, gen_ts):
        self.config_dict = config_dict
        self.skin_dict   = skin_dict
        self.gen_ts      = gen_ts
        
    def start(self):
        self.run()
    
    def run(self):
        pass

class FileGenerator(ReportGenerator):
    """Class for managing the template based generators"""
    
    def run(self):
        # Open up the main database archive
        archiveFilename = os.path.join(self.config_dict['Station']['WEEWX_ROOT'], 
                                       self.config_dict['Archive']['archive_file'])
        archive = weewx.archive.Archive(archiveFilename)
    
        stop_ts    = archive.lastGoodStamp() if self.gen_ts is None else self.gen_ts
        start_ts   = archive.firstGoodStamp()
        currentRec = archive.getRecord(stop_ts, weewx.units.getUnitTypeDict(self.skin_dict))

        genFiles = weewx.genfiles.GenFiles(self.config_dict, self.skin_dict)
        genFiles.generateBy('SummaryByMonth', start_ts, stop_ts)
        genFiles.generateBy('SummaryByYear',  start_ts, stop_ts)
        genFiles.generateToDate(currentRec, stop_ts)
    

class ImageGenerator(ReportGenerator):
    """Class for managing the image generator."""

    def run(self):
        # Open up the main database archive
        archiveFilename = os.path.join(self.config_dict['Station']['WEEWX_ROOT'], 
                                       self.config_dict['Archive']['archive_file'])
        archive = weewx.archive.Archive(archiveFilename)
    
        stop_ts = archive.lastGoodStamp() if self.gen_ts is None else self.gen_ts

        # Generate any images
        genImages = weewx.genimages.GenImages(self.config_dict, self.skin_dict)
        genImages.genImages(archive, stop_ts)
        
class Ftp(ReportGenerator):
    """Class for managing the "FTP generator".
    
    This will ftp everything in the public_html subdirectory to a webserver."""

    def run(self):
        f = open("/home/weewx/ftp.dict", "w")
        self.skin_dict.write(f)
        f.close()

        # Check to see that all necessary options are present. 
        # If so, FTP the data up to a server.
        if (self.skin_dict.has_key('server')   and 
            self.skin_dict.has_key('password') and 
            self.skin_dict.has_key('user')     and
            self.skin_dict.has_key('path')):
            ftpData = weewx.ftpdata.FtpData(source_dir = os.path.join(self.config_dict['Station']['WEEWX_ROOT'],
                                                                      self.config_dict['Reports']['HTML_ROOT']), 
                                            server     = self.skin_dict['server'],
                                            user       = self.skin_dict['user'],
                                            password   = self.skin_dict['password'],
                                            path       = self.skin_dict['path'])
            ftpData.ftpData()
                
class Copy(ReportGenerator):
    """Class for managing the 'copy generator.'
    
    This will copy files from the skin subdirectory to the public_html
    subdirectory."""
    
    def run(self):
        
        # Get the list of files to be copied. Wrap in a try block in case
        # the list does not exist.
        try:
            copy_once_list = self.skin_dict['Files']['Copy']['copy_once']
        except KeyError:
            return

        # Change directory to the skin subdirectory:
        os.chdir(os.path.join(self.config_dict['Station']['WEEWX_ROOT'],
                              self.skin_dict['SKIN_ROOT'],
                              self.skin_dict['skin']))
        # Figure out the destination of the files
        html_dest_dir = os.path.join(self.config_dict['Station']['WEEWX_ROOT'],
                                     self.skin_dict['HTML_ROOT'])
        
        # The copy list can contain wildcard characters. Go through the
        # list globbing any character expansions
        ncopy = 0
        for pattern in copy_once_list:
            # Glob this pattern; then go through each resultant filename:
            for file in glob.glob(pattern):
                # Final destination is the join of the html destination directory
                # and any relative subdirectory on the filename:
                dest_dir = os.path.join(html_dest_dir, os.path.dirname(file))
                # Make the destination directory, wrapping it in a try block in
                # case it already exists:
                try:
                    os.makedirs(dest_dir)
                except OSError:
                    pass
                # This version of copy does not copy over modification time,
                # so it will look like a new file, causing it to be (for example)
                # ftp'd to the server:
                shutil.copy(file, dest_dir)
                ncopy += 1
        
        syslog.syslog(syslog.LOG_DEBUG, "reportengine: copied %d files to %s" % (ncopy, html_dest_dir))
        
if __name__ == '__main__':
    
    # ===============================================================================
    # This module can be called as a main program to generate reports, etc.,
    # that are current as of the last archive record in the archive database.
    # ===============================================================================
    import sys
    import socket

    def gen_all(config_path, gen_ts = None):
        
        weewx.debug = 1
        syslog.openlog('reportengine', syslog.LOG_PID|syslog.LOG_CONS)
        syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))

        try :
            config_dict = configobj.ConfigObj(config_path, file_error=True)
        except IOError:
            print "Unable to open configuration file ", config_path
            raise
            
        socket.setdefaulttimeout(10)
        
        t = StdReportEngine(config_dict, gen_ts)
        t.start()
        t.join()

        
    if len(sys.argv) < 2 :
        print "Usage: reportengine.py path-to-configuration-file [timestamp-to-be-generated]"
        exit()
    gen_ts = int(sys.argv[2]) if len(sys.argv)>=3 else None
        
    gen_all(sys.argv[1], gen_ts)
