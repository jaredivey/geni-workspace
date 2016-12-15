# Copyright (c) 2014  Barnstormer Softworks, Ltd.

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
args = sys.argv
argnum = len(sys.argv)

import geni.rspec.pg as PG
import geni.rspec.igext as IGX
import geni.aggregate.instageni as IG

import geni.util
import localcontext
context = localcontext.buildContext()

SLICE = "python-geni-lib"
NETMASK = "255.255.255.0"
HOST_IPS = ["10.10.1.1", "10.10.1.2", "10.10.1.3"]
OVS_IPS = ["10.10.1.11", "10.10.1.12", "10.10.1.13"]
WHITELIST = set([IG.UKYPKS2])

for site in IG.aggregates():
    if site not in WHITELIST:
        continue

    print site.name
    geni.util.deleteSliverExists(site, context, SLICE)

    if argnum > 1 and args[1] == 'c':
        break

    try:
        ad = site.listresources(context)
    except Exception:
        # Continue past aggregates that are down
        continue

    cmid = ad.nodes[0].component_manager_id

    r = PG.Request()
    ovs_intfs = []

    ovs = IGX.XenVM("ovs")
    ovs.disk_image = "urn:publicid:IDN+emulab.net+image+emulab-ops:UBUNTU14-OVS2.31"
    ovs.addService(PG.Execute(shell="sh", command ="sudo git clone https://github.com/jaredivey/geni-install-files /local/geni-install-files ; sudo sh /local/geni-install-files/create-ovs-br0.sh"))
    ovs.addService(PG.Execute(shell="sh", command ="sudo /local/install-script-wireshark.sh"))
    ovs.addService(PG.Install(path="/local", url = "http://www.gpolab.bbn.com/experiment-support/OpenFlowOVS/wireshark.tar.gz"))
    ovs.component_manager_id = cmid
    for idx in xrange(0,3):
        intf = ovs.addInterface("if%d" % (idx))
        intf.addAddress(PG.IPv4Address(OVS_IPS[idx], NETMASK))
        ovs_intfs.append(intf)
    r.addResource(ovs)

    for ct in xrange(0,3):
        vzc = IGX.XenVM("host%d" % (ct+1))
        vzc.component_manager_id = cmid
        intf = vzc.addInterface("if0")
        intf.addAddress(PG.IPv4Address(HOST_IPS[ct], NETMASK))
        r.addResource(vzc)
        link = PG.LAN()
        link.addInterface(intf)
        link.addInterface(ovs_intfs[ct])
        link.vlan_tagging = True
        r.addResource(link)

    r.writeXML("ovs-%s.rspec" % (site.name))
    m = site.createsliver(context, SLICE, r)

    geni.util.printlogininfo(manifest=m)