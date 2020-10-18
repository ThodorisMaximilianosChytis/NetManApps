#!/usr/bin/python
from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from pox.lib.recoco import Timer
from collections import defaultdict
from pox.openflow.discovery import Discovery
from pox.lib.util import dpid_to_str
import pox.lib.packet as pkt
from pox.lib.addresses import EthAddr
import time, struct

_src = "00-00-00-00-00-01"
_dst = "00-00-00-00-00-04"

log = core.getLogger()
adjacency = defaultdict(lambda: defaultdict(lambda: None))
accesspoints = {}
mac_map = {}


def _get_path(src, dst, first, final):
    if src == dst:
        path = [src]
    else:
        distance = {}
        previous = {}
        for i in accesspoints.values():
            distance[i] = 9999
            previous[i] = None
        distance[src] = 0
        for m in range(len(accesspoints.values()) - 1):
            for p in accesspoints.values():
                for q in accesspoints.values():
                    w=1
                    if adjacency[p][q] != None:
                        if distance[p]  < distance[q] - w:
                            distance[q] = distance[p] + w
                            previous[q] = p
        path = []
        p = dst
        path.append(p)
        q = previous[p]
        while q is not None:
            if q == src:
                path.append(q)
                break
            p = q
            path.append(p)
            q = previous[p]
        path.reverse()
        if path is None:
            return None
        if str(src) == _src and str(dst) == _dst and len(path)!=1:
            print("---------------------------------")
            print("Using Dynamic Programming and Bellman Ford Algorithm")
            print("The shortest path from " + _src[-2:] + " to " + _dst[-2:] + " is: " )
            print(path)
            print("---------------------------------")

    R = []
    in_port = first
    for ap1, ap2 in zip(path[:-1], path[1:]):
        out_port = adjacency[ap1][ap2]
        R.append((ap1, in_port, out_port))
        in_port = adjacency[ap2][ap1]
    R.append((dst, in_port, final))
    return R

class PathInstalled(Event):
    def __init__(self, path):
        Event.__init__(self)
        self.path = path

class AccessPoint(EventMixin):
    def __init__(self):
        self.connection = None
        self.ports = None
        self.dpid = None
        self._listeners = None
        self._connected_at = None

    def __repr__(self):
        return dpid_to_str(self.dpid)


    def install_path_helper(self, p, match, packet_in=None):
        for ap, in_port, out_port in p:
            msg = of.ofp_flow_mod()
            msg.match = match
            msg.match.in_port = in_port
            msg.actions.append(of.ofp_action_output(port=out_port))
            msg.buffer_id = None
            ap.connection.send(msg)
            msg = of.ofp_barrier_request()
            ap.connection.send(msg)

    def install_path(self, dst_ap, last_port, match, event):
        p = _get_path(self, dst_ap, event.port, last_port)
        if p is None:
            if (match.dl_type == pkt.ethernet.IP_TYPE and event.parsed.find('ipv4')):
                e = pkt.ethernet()
                e.src = EthAddr(dpid_to_str(self.dpid))
                e.dst = match.dl_src
                e.type = e.IP_TYPE
                ipp = pkt.ipv4()
                ipp.protocol = ipp.ICMP_PROTOCOL
                ipp.srcip = match.nw_dst
                ipp.dstip = match.nw_src
                icmp = pkt.icmp()
                icmp.type = pkt.ICMP.TYPE_DEST_UNREACH
                icmp.code = pkt.ICMP.CODE_UNREACH_HOST
                orig_ip = event.parsed.find('ipv4')
                d = orig_ip.pack()
                d = d[:orig_ip.hl * 4 + 8]
                d = struct.pack("!HH", 0, 0) + d
                icmp.payload = d
                ipp.payload = icmp
                e.payload = ipp
                msg = of.ofp_packet_out()
                msg.actions.append(of.ofp_action_output(port=event.port))
                msg.data = e.pack()
                self.connection.send(msg)
            return
        self.install_path_helper(p, match, event.ofp)
        p = [(ap, out_port, in_port) for ap, in_port, out_port in p]
        self.install_path_helper(p, match.flip())


    def con(self, connection):
        if self.dpid is None:
            self.dpid = connection.dpid
        assert self.dpid == connection.dpid
        if self.ports is None:
            self.ports = connection.features.ports

        if self.connection is not None:
            self.connection.removeListeners(self._listeners)
            self.connection = None
            self._listeners = None
        self.connection = connection
        self._listeners = self.listenTo(connection)
        self._connected_at = time.time()


    def _handle_PacketIn(self, event):
        packet = event.parsed
        loc = (self, event.port)
        oldloc = mac_map.get(packet.src)
        if packet.effective_ethertype == packet.LLDP_TYPE:
            return
        if oldloc is None:
            if packet.src.is_multicast == False:
                mac_map[packet.src] = loc
        elif oldloc != loc:
            if core.openflow_discovery.is_edge_port(loc[0].dpid, loc[1]):
                if packet.src.is_multicast == False:
                    mac_map[packet.src] = loc
        if not packet.dst.is_multicast:
            if packet.dst in mac_map:
                dest = mac_map[packet.dst]
                match = of.ofp_match.from_packet(packet)
                self.install_path(dest[0], dest[1], match, event)


    def _handle_ConnectionDown(self, event):

        if self.connection is not None:
            self.connection.removeListeners(self._listeners)
            self.connection = None
            self._listeners = None


class l2_multi(EventMixin):

    def __init__(self):
        def startup():
            core.openflow_discovery.addListeners(self)          #listen to events
            core.openflow.addListeners(self, priority=0)

        core.call_when_ready(startup, ('openflow', 'openflow_discovery'))
    
    def _handle_LinkEvent(self, event):             #event handler for 'openflow discovery' event
        l = event.link
        ap1 = accesspoints[l.dpid1]
        ap2 = accesspoints[l.dpid2]
        clear = of.ofp_flow_mod(command=of.OFPFC_DELETE)
        for ap in accesspoints.itervalues():
            if ap.connection is None: continue
            ap.connection.send(clear)
        if event.removed:
            if ap2 in adjacency[ap1]: del adjacency[ap1][ap2]
            if ap1 in adjacency[ap2]: del adjacency[ap2][ap1]
            for ll in core.openflow_discovery.adjacency:
                if ll.dpid1 == l.dpid1 and ll.dpid2 == l.dpid2:
                    if Discovery.Link(ll[2], ll[3], ll[0], ll[1]) in core.openflow_discovery.adjacency:
                        adjacency[ap1][ap2] = ll.port1
                        adjacency[ap2][ap1] = ll.port2
                        break
        else:
            if adjacency[ap1][ap2] is None:
                if Discovery.Link(l[2], l[3], l[0], l[1]) in core.openflow_discovery.adjacency:
                    adjacency[ap1][ap2] = l.port1
                    adjacency[ap2][ap1] = l.port2
            bad_macs = set()
            for mac, (ap, port) in mac_map.iteritems():
                if (ap is ap1 and port == l.port1) or (ap is ap2 and port == l.port2):
                    bad_macs.add(mac)

    def _handle_ConnectionUp(self, event):      #event handler for 'openflow'
        ap = accesspoints.get(event.dpid)
        if ap is None:
            ap = AccessPoint()
            accesspoints[event.dpid] = ap
        ap.con(event.connection)

def launch():
    core.registerNew(l2_multi)
