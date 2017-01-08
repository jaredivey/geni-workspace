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

def createCtrlLink(ctrl, ovs, index):
    ovs_to_ctrl_intf = ovs.addInterface()
    ovs_to_ctrl_intf.addAddress(PG.IPv4Address("11.1.1.%d" % (4 * index + 1), CTRLMASK))

    # Create interface for controller to switch
    ctrl_to_ovs_intf = ctrl.addInterface()
    ctrl_to_ovs_intf.addAddress(PG.IPv4Address("11.1.1.%d" % (4 * index + 2), CTRLMASK))
    ctrl_link = PG.LAN()
    ctrl_link.addInterface(ctrl_to_ovs_intf)
    ctrl_link.addInterface(ovs_to_ctrl_intf)
    ctrl_link.vlan_tagging = False
    return ctrl_link

def createHost (name, cmid):
    vzc = IGX.XenVM(name)
    vzc.component_manager_id = cmid
    vzc.addService(PG.Execute(shell="sh",
                              command ="sudo git clone https://github.com/jaredivey/geni-install-files /local/geni-install-files"))
    return vzc

def createOvs2HostLink(ovs, host, index, i):
    ovs_intf = ovs.addInterface()
    ovs_intf.addAddress(PG.IPv4Address("12.10.%d.%d" % (index,i), NETMASK))

    host.addService(PG.Execute(shell="sh",
                              command="sudo bash /local/geni-install-files/install-iperf.sh %d %d" % (index, i)))
    host_intf = host.addInterface()
    host_intf.addAddress(PG.IPv4Address("10.10.%d.%d" % (index, i), NETMASK))

    link = PG.LAN()
    link.addInterface(ovs_intf)
    link.addInterface(host_intf)
    link.vlan_tagging = False
    return link

def createOvs2OvsLink(ovs1, ovs2, subnet, index):
    intf1 = ovs1.addInterface()
    intf1.addAddress(PG.IPv4Address("12.10.%d.%d" % (subnet, 2*index+1), NETMASK))
    intf2 = ovs2.addInterface()
    intf2.addAddress(PG.IPv4Address("12.10.%d.%d" % (subnet, 2*index+2), NETMASK))
    link = PG.LAN()
    link.addInterface(intf1)
    link.addInterface(intf2)
    link.vlan_tagging = False
    return link

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
    ctrl = createRyuController("ctrl", cmid)
    r.addResource(ctrl)

    num_hosts = 2
    num_links = 1
    num_switches = 4
    all_ovs = []
    for i in xrange(0, num_switches):
        # Create the OVS switch
        ovs = createOvsSwitch("ovs%d" % (i + 1), cmid, i)
        r.addResource(ovs)

        # Create interface for controller to switch
        r.addResource(createCtrlLink(ctrl,ovs,i))

        # Create hosts and connect them to switch
        for ct in xrange(0,num_hosts):
            vzc = createHost("host%d%d" % (i+1,ct+1), cmid)
            for j in xrange(0,num_links):
                r.addResource(createOvs2HostLink(ovs,vzc,i,ct*num_links+j+1))
            r.addResource(vzc)
        all_ovs.append(ovs)

    # Connect the switches in a single line
    for i in xrange(1,num_switches):
        r.addResource(createOvs2OvsLink(all_ovs[i-1], all_ovs[i], num_switches, i))
    r.addResource(createOvs2OvsLink(all_ovs[num_switches-1], all_ovs[0], num_switches, num_switches))

    r.writeXML("ovs-%s-ring.rspec" % (site.name))
    #m = site.createsliver(context, SLICE, r)
    #geni.util.printlogininfo(manifest=m)