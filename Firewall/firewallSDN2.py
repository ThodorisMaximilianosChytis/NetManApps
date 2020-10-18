#!/usr/bin/python2

import os


from pox.core import core
from pox.openflow.libopenflow_01 import ofp_flow_mod, ofp_match
from pox.lib.revent import *
from pox.lib.addresses import IPAddr
import pox.lib.packet as pkt

import csv

log = core.getLogger()
# For flow rule entries in the OpenFlow table
policyFile = "pox/misc/FirewallRestrictions.csv"

class Firewall (EventMixin):

    def __init__ (self):
        self.listenTo(core.openflow)
        log.info("Enabling Firewall Module")
        # Our firewall table
        self.firewall = {}

    def sendRule (self, src, dst):
        """
        Drops this packet and optionally installs a flow to continue
        dropping similar ones for a while
        """
        msg = ofp_flow_mod()
        match = ofp_match(dl_type = 0x800, nw_proto = pkt.ipv4.ICMP_PROTOCOL)
        match.nw_src = IPAddr(src)
        match.nw_dst = IPAddr(dst)
        msg.match = match
        msg.priority = 10
        self.connection.send(msg)

    # function that allows adding firewall rules into the firewall table
    def AddRule (self, src=0, dst=0):
        if (src, dst) in self.firewall:
            log.info("Rule already present drop: src %s - dst %s", src, dst)
        else:
            log.info("Adding firewall rule drop: src %s - dst %s", src, dst)
            self.firewall[(src, dst)]=True
            print("---------")
            print(src)
            print(dst)
            print("---------")
            self.sendRule(src, dst)

    def _handle_ConnectionUp (self, event):
        ''' Add your logic here ... '''
        self.connection = event.connection

       
        
        try:
            ifile  = open(policyFile, "rb")
        except Exception as e:
            log.info(e)
            return

        reader = csv.reader(ifile)
        for row in reader:
            self.AddRule(row[1], row[2])
        
        ifile.close()


def launch ():
    '''
    Starting the Firewall module
    '''
    core.registerNew(Firewall)
