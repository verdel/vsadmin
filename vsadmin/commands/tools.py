# -*- coding: utf-8 -*-
from pyVmomi import vim
from pyVim import connect
from datetime import timedelta
import atexit
import requests
import ssl
import re
import sys


class vCenterException(RuntimeError):
    message = None

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

    def __unicode__(self):
        return self.message


class NetworkCheck(object):

    @staticmethod
    def checkIP(ip):
        a = ip.split('.')
        if len(a) != 4:
            return False
        for x in a:
            if not x.isdigit():
                return False
            i = int(x)
            if i < 0 or i > 255:
                return False
        return True

    @staticmethod
    def checkMAC(mac):
        if re.match('[0-9a-f]{2}([:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$',
                    mac.lower()):
            return True
        else:
            return False


class vCenter(object):
    def __init__(self, server, username, password):
        self.server = server
        self.username = username
        self.password = password
        self.SI = None
        requests.packages.urllib3.disable_warnings()
        self.context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        self.context.verify_mode = ssl.CERT_NONE
        try:
            self.SI = connect.SmartConnect(host=self.server,
                                           user=self.username,
                                           pwd=self.password,
                                           sslContext=self.context)
        except Exception:
            pass

        if not self.SI:
            print("Could not connect to the specified host using "
                  "specified username and password")
            sys.exit(1)
        atexit.register(connect.Disconnect, self.SI)

        self.lastnetworkinfokey = self.get_customfield_key('LastNetworkInfo')

        self.vchtime = self.SI.CurrentTime()

        # Get all the performance counters
        self.perf_dict = {}
        perfList = self.SI.content.perfManager.perfCounter
        for counter in perfList:
            counter_full = "{}.{}.{}".format(counter.groupInfo.key,
                                             counter.nameInfo.key,
                                             counter.rollupType)
            self.perf_dict[counter_full] = counter.key

    def build_perf_query(self, content, vchtime, counterId, instance, vm, interval):
        perfManager = content.perfManager
        metricId = vim.PerformanceManager.MetricId(counterId=counterId,
                                                   instance=instance)
        startTime = vchtime - timedelta(minutes=(interval + 1))
        endTime = vchtime - timedelta(minutes=1)
        query = vim.PerformanceManager.QuerySpec(intervalId=20,
                                                 entity=vm,
                                                 metricId=[metricId],
                                                 startTime=startTime,
                                                 endTime=endTime)
        perfResults = perfManager.QueryPerf(querySpec=[query])
        if perfResults:
            return perfResults
        else:
            print("ERROR: Performance results empty."
                  "TIP: Check time drift on source and vCenter server")
            print("Troubleshooting info:")
            print("vCenter/host date and time: {}".format(vchtime))
            print("Start perf counter time   :  {}".format(startTime))
            print("End perf counter time     :  {}".format(endTime))
            print(query)
            sys.exit(1)

    def stat_check(self, perf_dict, counter_name):
        counter_key = perf_dict[counter_name]
        return counter_key

    def print_folder_tree(self, vm):
        entity = vm
        folder_tree = []
        while entity.parent.name != 'vm':
            if isinstance(entity.parent, vim.Folder):
                folder_tree = [entity.parent.name] + folder_tree
            entity = entity.parent
        folder_tree = "/" + "/".join(folder_tree)
        return folder_tree

    def get_customfield_key(self, name):
        customFieldsManager = self.SI.RetrieveContent().customFieldsManager
        customfield = next((item for item in customFieldsManager.field if item.name == name), None)
        if customfield is not None:
            return customfield.key
        else:
            return None

    def print_vm_info(self, vm, interval=20, verbose=False):
        statInt = interval * 3  # There are 3 20s samples in each minute
        summary = vm.summary
        disk_list = []
        vm_hardware = vm.config.hardware
        for each_vm_hardware in vm_hardware.device:
            if (each_vm_hardware.key >= 2000) and (each_vm_hardware.key < 3000):
                disk_list.append('{} | {:.1f}GB | Thin: {} | {}'.format(each_vm_hardware.deviceInfo.label,
                                                                        each_vm_hardware.capacityInKB / 1024 / 1024,
                                                                        each_vm_hardware.backing.thinProvisioned,
                                                                        each_vm_hardware.backing.fileName))

        guestToolsRunningStatus = "Running" if vm.guest.toolsRunningStatus == "guestToolsRunning" else "Not running"
        guestToolsStatus = "OK" if vm.guest.toolsStatus == "toolsOk" else "Need Attention"
        guestToolsVersionStatus = "Current" if vm.guest.toolsVersionStatus == "guestToolsCurrent" else "Need upgrade"
        guestToolsVersion = vm.guest.toolsVersion

        print("UUID               : {}".format(summary.config.instanceUuid))
        print("Name               : {}".format(summary.config.name))
        print("Guest              : {}".format(summary.config.guestFullName))
        print("State              : {}".format(summary.runtime.powerState))
        print("Guest Tools Status : Status: {} | Version Status: {} | Version: {} | Health: {}".format(guestToolsRunningStatus, guestToolsVersionStatus, guestToolsVersion, guestToolsStatus))
        print("Cluster            : {}".format(summary.runtime.host.parent.name))
        print("Host               : {}".format(summary.runtime.host.name))
        print("Folder             : {}".format(self.print_folder_tree(vm)))
        print("Number of vCPUs    : {}".format(summary.config.numCpu))
        print("Memory             : {} MB ({:.1f} GB)".format(summary.config.memorySizeMB, (float(summary.config.memorySizeMB) / 1024)))
        print("VM .vmx Path       : {}".format(summary.config.vmPathName))

        print("Virtual Disks      : {}".format(disk_list[0]))
        if len(disk_list) > 1:
            disk_list.pop(0)
            for each_disk in disk_list:
                print("                     {}".format(each_disk))

        if vm.guest.net != []:
            print("Network            : ")
            for card in vm.guest.net:
                print("                     Name: {}".format(card.network))
                print("                     Connected: {}".format(card.connected))
                print("                     Mac: {}".format(card.macAddress))
                if card.ipConfig is not None:
                    for ips in card.ipConfig.ipAddress:
                        print("                     IP: {}".format(ips.ipAddress))
                print("")
        if vm.guest.ipStack != []:
            for gateway in vm.guest.ipStack[0].ipRouteConfig.ipRoute:
                if gateway.network == '0.0.0.0':
                    print("                     Default GW: {}".format(gateway.gateway.ipAddress))
            print("")
            print("Guest Hostname     : {}".format(vm.guest.ipStack[0].dnsConfig.hostName))
            print("DNS                :")
            for dns in vm.guest.ipStack[0].dnsConfig.ipAddress:
                print("                     Address: {}".format(dns))
            print("                     Search Domain: {}".format(vm.guest.ipStack[0].dnsConfig.domainName))

        customfields = next((item for item in summary.customValue if item.key == self.lastnetworkinfokey), None)
        if customfields is not None and customfields.value != "":
            print("Last Network Info  : {}".format(customfields.value))

        if summary.runtime.question is not None:
            print("Question  : ", summary.runtime.question.text)

        annotation = summary.config.annotation
        if annotation is not None and annotation != "":
            print("Notes              : %s" % annotation.encode('utf-8'))

        if verbose:
            # Convert limit and reservation values from -1 to None
            if vm.resourceConfig.cpuAllocation.limit == -1:
                vmcpulimit = "None"
            else:
                vmcpulimit = "{} Mhz".format(vm.resourceConfig.cpuAllocation.limit)
            if vm.resourceConfig.memoryAllocation.limit == -1:
                vmmemlimit = "None"
            else:
                vmmemlimit = "{} MB".format(vm.resourceConfig.cpuAllocation.limit)

            if vm.resourceConfig.cpuAllocation.reservation == 0:
                vmcpures = "None"
            else:
                vmcpures = "{} Mhz".format(vm.resourceConfig.cpuAllocation.reservation)
            if vm.resourceConfig.memoryAllocation.reservation == 0:
                vmmemres = "None"
            else:
                vmmemres = "{} MB".format(vm.resourceConfig.memoryAllocation.reservation)

            #CPU Ready Average
            statCpuReady = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'cpu.ready.summation')), "", vm, interval)
            cpuReady = (float(sum(statCpuReady[0].value[0].value)) / statInt)
            #CPU Usage Average % - NOTE: values are type LONG so needs divided by 100 for percentage
            statCpuUsage = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'cpu.usage.average')), "", vm, interval)
            cpuUsage = ((float(sum(statCpuUsage[0].value[0].value)) / statInt) / 100)
            #Memory Active Average MB
            statMemoryActive = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'mem.active.average')), "", vm, interval)
            memoryActive = (float(sum(statMemoryActive[0].value[0].value) / 1024) / statInt)
            #Memory Shared
            statMemoryShared = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'mem.shared.average')), "", vm, interval)
            memoryShared = (float(sum(statMemoryShared[0].value[0].value) / 1024) / statInt)
            #Memory Balloon
            statMemoryBalloon = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'mem.vmmemctl.average')), "", vm, interval)
            memoryBalloon = (float(sum(statMemoryBalloon[0].value[0].value) / 1024) / statInt)
            #Memory Swapped
            statMemorySwapped = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'mem.swapped.average')), "", vm, interval)
            memorySwapped = (float(sum(statMemorySwapped[0].value[0].value) / 1024) / statInt)
            #Datastore Average IO
            statDatastoreIoRead = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'datastore.numberReadAveraged.average')), "*", vm, interval)
            DatastoreIoRead = (float(sum(statDatastoreIoRead[0].value[0].value)) / statInt)
            statDatastoreIoWrite = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'datastore.numberWriteAveraged.average')), "*", vm, interval)
            DatastoreIoWrite = (float(sum(statDatastoreIoWrite[0].value[0].value)) / statInt)
            #Datastore Average Latency
            statDatastoreLatRead = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'datastore.totalReadLatency.average')), "*", vm, interval)
            DatastoreLatRead = (float(sum(statDatastoreLatRead[0].value[0].value)) / statInt)
            statDatastoreLatWrite = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'datastore.totalWriteLatency.average')), "*", vm, interval)
            DatastoreLatWrite = (float(sum(statDatastoreLatWrite[0].value[0].value)) / statInt)

            #Network usage (Tx/Rx)
            statNetworkTx = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'net.transmitted.average')), "", vm, interval)
            networkTx = (float(sum(statNetworkTx[0].value[0].value) * 8 / 1024) / statInt)
            statNetworkRx = self.build_perf_query(self.SI.content, self.vchtime, (self.stat_check(self.perf_dict, 'net.received.average')), "", vm, interval)
            networkRx = (float(sum(statNetworkRx[0].value[0].value) * 8 / 1024) / statInt)

            print("")
            print("NOTE: Any VM statistics are averages of the last {} minutes".format(statInt / 3))
            print("[VM Advanced] Limits                    : CPU: {}, Memory: {}".format(vmcpulimit, vmmemlimit))
            print("[VM Advanced] Reservations              : CPU: {}, Memory: {}".format(vmcpures, vmmemres))
            print("[VM Advanced] CPU Ready                 : Average {:.1f} %, Maximum {:.1f} %".format((cpuReady / 20000 * 100),
                                                                                                        ((float(max(statCpuReady[0].value[0].value)) / 20000 * 100))))
            print("[VM Advanced] CPU (%)                   : {:.0f} %".format(cpuUsage))
            print("[VM Advanced] Memory Shared             : {:.0f} %, {:.0f} MB".format(
                ((memoryShared / summary.config.memorySizeMB) * 100), memoryShared))
            print("[VM Advanced] Memory Balloon            : {:.0f} %, {:.0f} MB".format(
                ((memoryBalloon / summary.config.memorySizeMB) * 100), memoryBalloon))
            print("[VM Advanced] Memory Swapped            : {:.0f} %, {:.0f} MB".format(
                ((memorySwapped / summary.config.memorySizeMB) * 100), memorySwapped))
            print("[VM Advanced] Memory Active             : {:.0f} %, {:.0f} MB".format(
                ((memoryActive / summary.config.memorySizeMB) * 100), memoryActive))
            print("[VM Advanced] Datastore Average IO      : Read: {:.0f} IOPS, Write: {:.0f} IOPS".format(DatastoreIoRead, DatastoreIoWrite))
            print("[VM Advanced] Datastore Average Latency : Read: {:.0f} ms, Write: {:.0f} ms".format(DatastoreLatRead, DatastoreLatWrite))
            print("[VM Advanced] Overall Network Usage     : Transmitted {:.3f} Mbps, Received {:.3f} Mbps".format(networkTx, networkRx))

            print("")
            print("[Host] CPU Detail                       : Processor Sockets: {}, Cores per Socket {}".format(summary.runtime.host.summary.hardware.numCpuPkgs, (summary.runtime.host.summary.hardware.numCpuCores / summary.runtime.host.summary.hardware.numCpuPkgs)))
            print("[Host] CPU Type                         : {}".format(summary.runtime.host.summary.hardware.cpuModel))
            print("[Host] CPU Usage                        : Used: {} Mhz, Total: {} Mhz".format(summary.runtime.host.summary.quickStats.overallCpuUsage, (summary.runtime.host.summary.hardware.cpuMhz * summary.runtime.host.summary.hardware.numCpuCores)))
            print("[Host] Memory Usage                     : Used: {:.0f} GB, Total: {:.0f} GB".format((float(summary.runtime.host.summary.quickStats.overallMemoryUsage) / 1024), (float(summary.runtime.host.summary.hardware.memorySize) / 1024 / 1024 / 1024)))
            print("[Host] License                          : {}".format(self.SI.content.licenseManager.licenseAssignmentManager.QueryAssignedLicenses(summary.runtime.host._moId)[0].assignedLicense.name))
            print("")

    def search_vm_by_name(self, name, method='exact'):
        content = self.SI.content
        root_folder = content.rootFolder
        # entity_stack = root_folder.childEntity
        objView = content.viewManager.CreateContainerView(root_folder,
                                                          [vim.VirtualMachine],
                                                          True)
        vmList = objView.view
        objView.Destroy()
        obj = []
        for vm in vmList:
            if method == 'exact':
                if (vm.name == name):
                    obj.append(vm)
                    return obj
            else:
                if re.match(".*%s.*" % name, vm.name):
                    obj.append(vm)
        return obj

    def search_vm_by_ip(self, ip):
        obj = []
        content = self.SI.content
        root_folder = content.rootFolder

        if not NetworkCheck.checkIP(ip):
            print("IP address {} is invalid.".format(ip))
            return obj
        search_obj = content.searchIndex.FindByIp(None,
                                                  ip,
                                                  True)
        if search_obj:
            obj.append(search_obj)

        objView = content.viewManager.CreateContainerView(root_folder,
                                                          [vim.VirtualMachine],
                                                          True)
        vmList = objView.view
        for vm in vmList:
            summary = vm.summary
            customfields = next((item for item in summary.customValue if item.key == self.lastnetworkinfokey), None)
            if customfields is not None and customfields.value != "":
                if ip in customfields.value:
                    if vm not in obj:
                        obj.append(vm)
        return obj

    def search_vm_by_mac(self, mac):
        obj = []
        if not NetworkCheck.checkMAC(mac):
            print("MAC address {} is invalid.".format(mac))
            return obj

        content = self.SI.content
        root_folder = content.rootFolder
        objView = content.viewManager.CreateContainerView(root_folder,
                                                          [vim.VirtualMachine],
                                                          True)
        vmList = objView.view
        objView.Destroy()
        for vm in vmList:
            vm_hardware = vm.config.hardware
            for each_vm_hardware in vm_hardware.device:
                if (each_vm_hardware.key >= 4000) and (each_vm_hardware.key < 5000):
                    if re.search('.*{}.*'.format(mac), each_vm_hardware.macAddress):
                        obj.append(vm)
                        break
        return obj

    def search_vm_by_hostname(self, hostname):
        obj = []
        search_obj = self.SI.content.searchIndex.FindByDnsName(None,
                                                               hostname,
                                                               True)
        if search_obj:
            obj.append(search_obj)
        return obj

    def search_vm_by_task(self, task):
        content = self.SI.content
        root_folder = content.rootFolder
        objView = content.viewManager.CreateContainerView(root_folder,
                                                          [vim.VirtualMachine],
                                                          True)
        vmList = objView.view
        objView.Destroy()
        obj = []
        for vm in vmList:
            if vm.summary.config.annotation and vm.summary.config.annotation != "":
                if re.search('.*{}.*'.format(task), vm.summary.config.annotation):
                    obj.append(vm)
        return obj
