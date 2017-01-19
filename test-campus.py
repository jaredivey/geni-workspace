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

SLICE = "geni-desktop-slice"
CTRLMASK = "255.255.255.252"
NETMASK = "255.255.0.0"
UKYPKS2 = set([IG.UKYPKS2])
CLEMSON = set([IG.Clemson])

ovs_interfaces = 0
ctrl_interfaces = 0
host_interfaces = 0

def createRyuController(name, cmid):
    ctrl = IGX.XenVM(name)
    ctrl.addService(PG.Execute(shell="sh",
                              command ="sudo git clone https://github.com/jaredivey/geni-install-files /local/geni-install-files ; sudo sh /local/geni-install-files/prep-and-run-ryu.sh"))
    ctrl.component_manager_id = cmid
    return ctrl


def createOvsSwitch(name, cmid, index):
    ovs = IGX.XenVM(name)
    #ovs.disk_image = "urn:publicid:IDN+emulab.net+image+emulab-ops:UBUNTU14-OVS2.31"
    ovs.addService(PG.Execute(shell="sh",
                              command="sudo git clone https://github.com/jaredivey/geni-install-files /local/geni-install-files ; sudo bash /local/geni-install-files/install-ovs-deps.sh %d" % (4*index+2)))
    ovs.component_manager_id = cmid
    return ovs

def createCtrlLink(ctrl, ovs, index, new_link=PG.LAN()):
    global ovs_interfaces
    ovs_to_ctrl_intf = ovs.addInterface("if%d" % (ovs_interfaces))
    ovs_interfaces += 1
    ovs_to_ctrl_intf.addAddress(PG.IPv4Address("11.1.1.%d" % (4 * index + 1), CTRLMASK))

    # Create interface for controller to switch
    global ctrl_interfaces
    ctrl_to_ovs_intf = ctrl.addInterface("if%d" % (ctrl_interfaces))
    ctrl_interfaces += 1
    ctrl_to_ovs_intf.addAddress(PG.IPv4Address("11.1.1.%d" % (4 * index + 2), CTRLMASK))
    ctrl_link = new_link
    ctrl_link.addInterface(ctrl_to_ovs_intf)
    ctrl_link.addInterface(ovs_to_ctrl_intf)
    ctrl_link.vlan_tagging = True
    return ctrl_link

def createHost (name, cmid):
    vzc = IGX.XenVM(name)
    vzc.component_manager_id = cmid
    vzc.addService(PG.Execute(shell="sh",
                              command ="sudo git clone https://github.com/jaredivey/geni-install-files /local/geni-install-files"))
    return vzc

def createOvs2HostLink(ovs, host, index, i, new_link=PG.LAN()):
    global ovs_interfaces
    ovs_intf = ovs.addInterface("if%d" % (ovs_interfaces))
    ovs_interfaces += 1
    ovs_intf.addAddress(PG.IPv4Address("12.10.%d.%d" % (index+6,i), NETMASK))

    host.addService(PG.Execute(shell="sh",
                              command="sudo bash /local/geni-install-files/install-iperf.sh %d %d" % (index, i)))
    global host_interfaces
    host_intf = host.addInterface("if%d" % (host_interfaces))
    host_interfaces += 1
    host_intf.addAddress(PG.IPv4Address("10.10.%d.%d" % (index,i), NETMASK))

    link = new_link
    link.addInterface(ovs_intf)
    link.addInterface(host_intf)
    link.vlan_tagging = True
    return link

def createOvs2OvsLink(ovs1, ovs2, subnet, index, new_link=PG.LAN()):
    global ovs_interfaces
    intf1 = ovs1.addInterface("if%d" % (ovs_interfaces))
    ovs_interfaces += 1
    intf1.addAddress(PG.IPv4Address("12.10.%d.%d" % (subnet, 2*index+1), NETMASK))
    intf2 = ovs2.addInterface("if%d" % (ovs_interfaces))
    ovs_interfaces += 1
    intf2.addAddress(PG.IPv4Address("12.10.%d.%d" % (subnet, 2*index+2), NETMASK))
    link = new_link
    link.addInterface(intf1)
    link.addInterface(intf2)
    link.vlan_tagging = True
    return link

r = PG.Request()
for site in IG.aggregates():
    if site not in UKYPKS2:
        continue

    print site.name
    #geni.util.deleteSliverExists(site, context, SLICE)

    try:
        ad = site.listresources(context)
    except Exception:
        # Continue past aggregates that are down
        print "%s might be down" % site.name
        continue

    cmid = ad.nodes[0].component_manager_id

    # Create the controller
    ctrl = createRyuController("ctrl", cmid)
    r.addResource(ctrl)

    # Create subnet 0
    print "Creating subnet 0"
    subnet = 0
    ovs0 = []
    sn0_switches = 3
    for i in xrange(0,sn0_switches):
        ovs0.append(createOvsSwitch("ovs%d-%d" % (subnet, i), cmid, i))
        r.addResource(ovs0[i])
        r.addResource(createCtrlLink(ctrl,ovs0[i],i))

        # Connect subnet 0 switches together
        if len(ovs0) > 1:
            r.addResource(createOvs2OvsLink(ovs0[i-1], ovs0[i], subnet, i))
        # Connect last switch to first switch
        if len(ovs0) == sn0_switches:
            r.addResource(createOvs2OvsLink(ovs0[i], ovs0[0], subnet, i+1))

    # Create subnet 1
    print "Creating subnet 1"
    subnet = 1
    ovs1 = []
    sn1_switches = 2
    sn1_links = 2
    for i in xrange(0,sn1_switches):
        ovs1.append(createOvsSwitch("ovs%d-%d" % (subnet, i), cmid, i))
        r.addResource(ovs1[i])
        r.addResource(createCtrlLink(ctrl,ovs1[i],i+sn0_switches))

        if len(ovs1) > 1:
            r.addResource(createOvs2OvsLink(ovs1[i-1], ovs1[i], subnet, i))

        # Create 1 host with 2 links per switch in subnet 1
        vzc = createHost("host%d-%d" % (subnet, i + 1), cmid)
        r.addResource(vzc)
        for j in xrange(0, sn1_links):
            r.addResource(createOvs2HostLink(ovs1[i], vzc, subnet, sn1_links*i + j + 1))

    # Create a link between subnets 0 and 1
    r.addResource(createOvs2OvsLink(ovs0[2], ovs1[0], subnet, 3))

for site in IG.aggregates():
    if site not in CLEMSON:
        continue

    print site.name
    # geni.util.deleteSliverExists(site, context, SLICE)

    try:
        ad = site.listresources(context)
    except Exception:
        # Continue past aggregates that are down
        print "%s might be down" % site.name
        continue

    cmid = ad.nodes[0].component_manager_id

    # Create subnet 2
    print "Creating subnet 2"
    subnet = 2
    ovs2 = []
    sn2_switches = 7
    sn2_links = 1
    for i in xrange(0,sn2_switches):
        ovs2.append(createOvsSwitch("ovs%d-%d" % (subnet, i), cmid, i))
        r.addResource(ovs2[i])
        r.addResource(createCtrlLink(ctrl,ovs2[i],i+sn0_switches+sn1_switches, new_link=PG.StitchedLink()))

        if i > 1:
            vzc = createHost("host%d-%d" % (subnet, i + 1), cmid)
            r.addResource(vzc)
            for j in xrange(0, sn2_links):
                r.addResource(createOvs2HostLink(ovs2[i], vzc, subnet, sn2_links*(i-2) + j + 1))

        # Add 2 more hosts for switch 6
        if i == 6:
            for b in xrange(0,2):
                vzc = createHost("host%d-%d" % (subnet, i + b + 2), cmid)
                r.addResource(vzc)
                for j in xrange(0, sn2_links):
                    r.addResource(createOvs2HostLink(ovs2[i], vzc, subnet, sn2_links*(i-1+b) + j + 1))

    r.addResource(createOvs2OvsLink(ovs2[0], ovs2[1], subnet, 1))
    r.addResource(createOvs2OvsLink(ovs2[0], ovs2[2], subnet, 2))
    r.addResource(createOvs2OvsLink(ovs2[1], ovs2[3], subnet, 3))
    r.addResource(createOvs2OvsLink(ovs2[2], ovs2[3], subnet, 4))
    r.addResource(createOvs2OvsLink(ovs2[2], ovs2[4], subnet, 5))
    r.addResource(createOvs2OvsLink(ovs2[3], ovs2[5], subnet, 6))
    r.addResource(createOvs2OvsLink(ovs2[5], ovs2[6], subnet, 7))

for site in IG.aggregates():
    if site not in UKYPKS2:
        continue

    print site.name
    # geni.util.deleteSliverExists(site, context, SLICE)

    try:
        ad = site.listresources(context)
    except Exception:
        # Continue past aggregates that are down
        print "%s might be down" % site.name
        continue

    cmid = ad.nodes[0].component_manager_id

    # Create subnet 3
    print "Creating subnet 3"
    subnet = 3
    ovs3 = []
    sn3_switches = 4
    sn3_links = 1
    for i in xrange(0,sn3_switches):
        ovs3.append(createOvsSwitch("ovs%d-%d" % (subnet, i), cmid, i))
        r.addResource(ovs3[i])
        r.addResource(createCtrlLink(ctrl,ovs3[i],i+sn0_switches+sn1_switches+sn2_switches))

        if i != 1:
            vzc = createHost("host%d-%d" % (subnet, i + 1), cmid)
            r.addResource(vzc)
            for j in xrange(0, sn3_links):
                r.addResource(createOvs2HostLink(ovs3[i], vzc, subnet, (sn3_links*i + j + 1)))

    # Add a second host to switch 0 using the address space that 1 would have used
    vzc = createHost("host%d-%d" % (subnet, 1 + 1), cmid)
    r.addResource(vzc)
    for j in xrange(0, sn3_links):
        r.addResource(createOvs2HostLink(ovs3[0], vzc, subnet, (sn3_links*1 + j + 1)))

    # Add a second host to switch 3
    vzc = createHost("host%d-%d" % (subnet, (3+1) + 1), cmid)
    r.addResource(vzc)
    for j in xrange(0, sn3_links):
        r.addResource(createOvs2HostLink(ovs3[3], vzc, subnet, (sn3_links*(3+1) + j + 1)))

    r.addResource(createOvs2OvsLink(ovs3[0], ovs3[1], subnet, 1))
    r.addResource(createOvs2OvsLink(ovs3[1], ovs3[2], subnet, 2))
    r.addResource(createOvs2OvsLink(ovs3[1], ovs3[3], subnet, 3))
    r.addResource(createOvs2OvsLink(ovs3[2], ovs3[3], subnet, 4))

for site in IG.aggregates():
    if site not in CLEMSON:
        continue

    print site.name
    # geni.util.deleteSliverExists(site, context, SLICE)

    try:
        ad = site.listresources(context)
    except Exception:
        # Continue past aggregates that are down
        print "%s might be down" % site.name
        continue

    cmid = ad.nodes[0].component_manager_id

    # Create subnet "4" (really just one switch connecting subnets 0 and 2
    print "Creating switch 4"
    subnet = 4
    sn4_switches = 1
    ovs4 = createOvsSwitch("ovs%d-%d" % (subnet, 0), cmid, 0)
    r.addResource(ovs4)
    r.addResource(createCtrlLink(ctrl,ovs4,sn0_switches+sn1_switches+sn2_switches+sn3_switches, new_link=PG.StitchedLink()))

    r.addResource(createOvs2OvsLink(ovs4, ovs0[0], subnet, 1, new_link=PG.StitchedLink()))
    r.addResource(createOvs2OvsLink(ovs4, ovs2[0], subnet, 2))
    r.addResource(createOvs2OvsLink(ovs4, ovs2[1], subnet, 3))

for site in IG.aggregates():
    if site not in UKYPKS2:
        continue

    print site.name
    # geni.util.deleteSliverExists(site, context, SLICE)

    try:
        ad = site.listresources(context)
    except Exception:
        # Continue past aggregates that are down
        print "%s might be down" % site.name
        continue

    cmid = ad.nodes[0].component_manager_id

    # Create subnet "5" (really just one switch connecting subnets 0 and 3 and switch 4
    print "Creating switch 5"
    subnet = 5
    sn5_switches = 1
    ovs5 = createOvsSwitch("ovs%d-%d" % (subnet, 0), cmid, 0)
    r.addResource(ovs5)
    r.addResource(createCtrlLink(ctrl,ovs5,sn0_switches+sn1_switches+sn2_switches+sn3_switches+sn4_switches))

    r.addResource(createOvs2OvsLink(ovs5, ovs0[1], subnet, 1))
    r.addResource(createOvs2OvsLink(ovs5, ovs3[0], subnet, 2))
    r.addResource(createOvs2OvsLink(ovs5, ovs3[1], subnet, 3))
    r.addResource(createOvs2OvsLink(ovs5, ovs4, subnet, 4, new_link=PG.StitchedLink()))

r.writeXML("ovs-ukypks2-clemson-stitched-campus.rspec")
#m = site.createsliver(context, SLICE, r)
#geni.util.printlogininfo(manifest=m)