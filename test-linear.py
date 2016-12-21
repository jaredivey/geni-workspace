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
CTRLMASK = "255.255.255.252"
NETMASK = "255.255.0.0"
WHITELIST = set([IG.GATech])

for site in IG.aggregates():
    if site not in WHITELIST:
        continue

    print site.name
    #geni.util.deleteSliverExists(site, context, SLICE)

    if argnum > 1 and args[1] == 'c':
        break

    try:
        ad = site.listresources(context)
    except Exception:
        # Continue past aggregates that are down
        continue

    cmid = ad.nodes[0].component_manager_id

    r = PG.Request()

    # Create the controller
    ctrl = IGX.XenVM("ctrl")
    ctrl.addService(PG.Execute(shell="sh",
                              command ="sudo git clone https://github.com/jaredivey/geni-install-files /local/geni-install-files ; sudo sh /local/geni-install-files/prep-and-run-ryu.sh"))
    ctrl.component_manager_id = cmid
    r.addResource(ctrl)

    num_hosts = 1
    num_links = 4
    num_switches = 4
    all_ovs = []
    for i in xrange(0, num_switches):
        ovs_intfs = []

        # Create the OVS switch
        ovs = IGX.XenVM("ovs%d" % (i+1))
        ovs.disk_image = "urn:publicid:IDN+emulab.net+image+emulab-ops:UBUNTU14-OVS2.31"
        ovs.addService(PG.Execute(shell="sh",
                                  command ="sudo git clone https://github.com/jaredivey/geni-install-files /local/geni-install-files ; sudo bash /local/geni-install-files/create-ovs-br0.sh %d" % (4*i+2)))
        ovs.component_manager_id = cmid
        for idx in xrange(0,num_hosts*num_links):
            intf = ovs.addInterface()
            intf.addAddress(PG.IPv4Address("12.10.%d.%d" % (i,idx+1), NETMASK))
            ovs_intfs.append(intf)
        ovs_to_ctrl_intf = ovs.addInterface()
        ovs_to_ctrl_intf.addAddress(PG.IPv4Address("11.1.1.%d" % (4*i+1), CTRLMASK))
        r.addResource(ovs)

        # Create interface for controller to switch
        ctrl_to_ovs_intf = ctrl.addInterface()
        ctrl_to_ovs_intf.addAddress(PG.IPv4Address("11.1.1.%d" % (4*i+2), CTRLMASK))
        ctrl_link = PG.LAN()
        ctrl_link.addInterface(ctrl_to_ovs_intf)
        ctrl_link.addInterface(ovs_to_ctrl_intf)
        ctrl_link.vlan_tagging = True
        r.addResource(ctrl_link)

        # Create hosts and connect them to switch
        for ct in xrange(0,num_hosts):
            vzc = IGX.XenVM("host%d%d" % (i+1,ct+1))
            vzc.component_manager_id = cmid
            vzc.addService(PG.Execute(shell="sh",
                                      command ="sudo git clone https://github.com/jaredivey/geni-install-files /local/geni-install-files"))
            intfs = []
            for j in xrange(0,num_links):
                hostaddr = "10.10.%d.%d" % (i,ct*num_links+j+1)
                vzc.addService(PG.Execute(shell="sh",
                                          command ="sudo bash /local/geni-install-files/install-iperf.sh %d %d" % (i,ct*num_links+j+1)))
                intf = vzc.addInterface()
                intf.addAddress(PG.IPv4Address(hostaddr, NETMASK))
                intfs.append(intf)

            r.addResource(vzc)

            for j in xrange(0,num_links):
                link = PG.LAN()
                link.addInterface(intfs[j])
                link.addInterface(ovs_intfs[ct*num_links+j])
                link.vlan_tagging = True
                r.addResource(link)
        all_ovs.append(ovs)

    # Connect the switches in a single line
    for i in xrange(1,num_switches):
        intf1 = all_ovs[i-1].addInterface()
        intf1.addAddress(PG.IPv4Address("12.10.%d.%d" % (num_switches, 2*i+1), NETMASK))
        intf2 = all_ovs[i].addInterface()
        intf2.addAddress(PG.IPv4Address("12.10.%d.%d" % (num_switches, 2*i+2), NETMASK))
        link = PG.LAN()
        link.addInterface(intf1)
        link.addInterface(intf2)
        link.vlan_tagging = True
        r.addResource(link)

    r.writeXML("ovs-%s.rspec" % (site.name))
    #m = site.createsliver(context, SLICE, r)
    #geni.util.printlogininfo(manifest=m)
