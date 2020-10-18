#!/usr/bin/python

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.cli  import CLI





def topology():

    net = Mininet(controller=RemoteController, link=TCLink)
    

    h1  = net.addHost('h1', ip='10.0.0.1')
    h2  = net.addHost('h2', ip='10.0.0.2')
    h3  = net.addHost('h3', ip='10.0.0.3')
    h4  = net.addHost('h4', ip='10.0.0.4')


    s1 = net.addSwitch('s1', dpid='1')
    s2 = net.addSwitch('s2', dpid='2')


    c0 = net.addController('c0',controller=RemoteController, ip='127.0.0.1', port=6633)
    c1 = net.addController('c1',controller=RemoteController, ip='127.0.0.1', port=6653)

    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(s1, s2)
    net.addLink(h3, s2)
    net.addLink(h4, s2)

    net.start()

    print "Dumping host connections"
    dumpNodeConnections(net.hosts)
    
    print "Testing network connectivity"
    net.pingAll()
    # net.ping([net.hosts[0], net.hosts[1]])
    CLI(net)
    
    net.stop()

    

if __name__ == '__main__':
    setLogLevel('info')
    
    topology()