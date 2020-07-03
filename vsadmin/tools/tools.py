# -*- coding: utf-8 -*-
import atexit
import re
import sys
import ssl
import requests
import vsadmin.tools.vsanapiutils
import vsadmin.tools.vsanmgmtObjects
import vsadmin.tools.vsanStoragePolicy
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from pyVmomi import pbm, vim
from pyVim.connect import SmartConnect, SmartConnectNoSSL, Disconnect
from datetime import timedelta


class bcolors(object):
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


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
    def __init__(self, server, username, password, disable_ssl_verification):
        self.server = server
        self.username = username
        self.password = password
        self.disable_ssl_verification = disable_ssl_verification
        self.serviceInstance = None
        try:
            if disable_ssl_verification:
                self.serviceInstance = SmartConnectNoSSL(host=self.server,
                                                         user=self.username,
                                                         pwd=self.password)
            else:
                self.serviceInstance = SmartConnect(host=self.server,
                                                    user=self.username,
                                                    pwd=self.password)
            atexit.register(Disconnect, self.serviceInstance)
        except IOError as e:
            print(e)
            pass
        if not self.serviceInstance:
            raise SystemExit("Unable to connect to host with supplied info.")

        self.pbm_content = vsadmin.tools.vsanStoragePolicy.PbmConnect(self.serviceInstance._stub,
                                                                 self.disable_ssl_verification)
        self.pm = self.pbm_content.profileManager

        self.lastnetworkinfokey = self.get_customfield_key('LastNetworkInfo')

        self.vchtime = self.serviceInstance.CurrentTime()

        apiVersion = vsadmin.tools.vsanapiutils.GetLatestVmodlVersion(self.server)
        vcMos = vsadmin.tools.vsanapiutils.GetVsanVcMos(self.serviceInstance._stub, version=apiVersion)

        self.vsanPerfSystem = vcMos['vsan-performance-manager']

        # Get all the performance counters
        self.perf_dict = {}
        perfList = self.serviceInstance.content.perfManager.perfCounter
        for counter in perfList:
            counter_full = "{}.{}.{}".format(counter.groupInfo.key,
                                             counter.nameInfo.key,
                                             counter.rollupType)
            self.perf_dict[counter_full] = counter.key

    def get_metric_with_instance(self, content, vm, vchtime, interval):
        perfManager = content.perfManager
        startTime = vchtime - timedelta(minutes=(interval + 1))
        endTime = vchtime - timedelta(minutes=1)
        metricId = perfManager.QueryAvailablePerfMetric(vm, startTime, endTime, interval)
        return metricId

    def get_virtualdisk_scsi(self, vm, virtualdisk):
        controllerID = virtualdisk.controllerKey
        unitNumber = virtualdisk.unitNumber
        vm_hardware = vm.config.hardware
        for vm_hardware_device in vm_hardware.device:
            if vm_hardware_device.key == controllerID:
                busNumber = vm_hardware_device.busNumber
        return "scsi{}:{}".format(busNumber, unitNumber)

    def build_vsan_perf_query(self, content, vchtime, counterId, instance, vm, interval):
        perfManager = content.perfManager
        metricId = vim.PerformanceManager.MetricId(counterId=counterId,
                                                   instance=instance)
        startTime = vchtime - timedelta(minutes=(interval + 1))
        endTime = vchtime - timedelta(minutes=1)
        spec = vim.cluster.VsanPerfQuerySpec(
                interval=20,
                endTime=endTime,
                entityRefId=entity,
                labels=labels,
                startTime=startTime
            )
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

    @staticmethod
    def get_moref(obj):
        return str(obj).split(":")[1].strip("'")

    def get_customfield_key(self, name):
        customFieldsManager = self.serviceInstance.RetrieveContent().customFieldsManager
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
                if summary.runtime.powerState == "poweredOn" and verbose:
                    # VirtualDisk Average IO
                    statVirtualdiskIORead = self.build_perf_query(self.serviceInstance.content,
                                                                  self.vchtime,
                                                                  self.stat_check(self.perf_dict, 'virtualDisk.numberReadAveraged.average'),
                                                                  self.get_virtualdisk_scsi(vm, each_vm_hardware),
                                                                  vm,
                                                                  statInt)
                    VirtualdiskIORead = (float(sum(statVirtualdiskIORead[0].value[0].value)) / statInt)

                    statVirtualdiskIOWrite = self.build_perf_query(self.serviceInstance.content,
                                                                   self.vchtime,
                                                                   self.stat_check(self.perf_dict, 'virtualDisk.numberWriteAveraged.average'),
                                                                   self.get_virtualdisk_scsi(vm, each_vm_hardware),
                                                                   vm,
                                                                   statInt)
                    VirtualdiskIOWrite = (float(sum(statVirtualdiskIOWrite[0].value[0].value)) / statInt)

                    # VirtualDisk Average Latency
                    statVirtualdiskLatRead = self.build_perf_query(self.serviceInstance.content,
                                                                   self.vchtime,
                                                                   self.stat_check(self.perf_dict, 'virtualDisk.totalReadLatency.average'),
                                                                   self.get_virtualdisk_scsi(vm, each_vm_hardware),
                                                                   vm,
                                                                   statInt)
                    VirtualdiskLatRead = (float(sum(statVirtualdiskLatRead[0].value[0].value)) / statInt)
                    VirtualdiskLatRead = "{:.0f}".format(VirtualdiskLatRead) if VirtualdiskLatRead < 25 else "{}{:.0f}{}".format(bcolors.FAIL, VirtualdiskLatRead, bcolors.ENDC)

                    statVirtualdiskLatWrite = self.build_perf_query(self.serviceInstance.content,
                                                                    self.vchtime,
                                                                    self.stat_check(self.perf_dict, 'virtualDisk.totalWriteLatency.average'),
                                                                    self.get_virtualdisk_scsi(vm, each_vm_hardware),
                                                                    vm,
                                                                    statInt)
                    VirtualdiskLatWrite = (float(sum(statVirtualdiskLatWrite[0].value[0].value)) / statInt)
                    VirtualdiskLatWrite = "{:.0f}".format(VirtualdiskLatWrite) if VirtualdiskLatWrite < 25 else "{}{:.0f}{}".format(bcolors.FAIL, VirtualdiskLatWrite, bcolors.ENDC)

                    if each_vm_hardware.backing.datastore.summary.type != 'vsan':
                        # Datastore Average IO
                        statDatastoreIORead = self.build_perf_query(self.serviceInstance.content,
                                                                    self.vchtime,
                                                                    self.stat_check(self.perf_dict, 'datastore.numberReadAveraged.average'),
                                                                    each_vm_hardware.backing.datastore.info.vmfs.uuid,
                                                                    vm,
                                                                    statInt)
                        DatastoreIORead = (float(sum(statDatastoreIORead[0].value[0].value)) / statInt)

                        statDatastoreIOWrite = self.build_perf_query(self.serviceInstance.content,
                                                                    self.vchtime,
                                                                    self.stat_check(self.perf_dict, 'datastore.numberWriteAveraged.average'),
                                                                    each_vm_hardware.backing.datastore.info.vmfs.uuid,
                                                                    vm,
                                                                    statInt)
                        DatastoreIOWrite = (float(sum(statDatastoreIOWrite[0].value[0].value)) / statInt)

                        # Datastore Average Latency
                        statDatastoreLatRead = self.build_perf_query(self.serviceInstance.content,
                                                                    self.vchtime,
                                                                    self.stat_check(self.perf_dict, 'datastore.totalReadLatency.average'),
                                                                    each_vm_hardware.backing.datastore.info.vmfs.uuid,
                                                                    vm,
                                                                    statInt)
                        DatastoreLatRead = (float(sum(statDatastoreLatRead[0].value[0].value)) / statInt)
                        DatastoreLatRead = "{:.0f}".format(DatastoreLatRead) if DatastoreLatRead < 25 else "{}{:.0f}{}".format(bcolors.FAIL, DatastoreLatRead, bcolors.ENDC)

                        statDatastoreLatWrite = self.build_perf_query(self.serviceInstance.content,
                                                                    self.vchtime,
                                                                    self.stat_check(self.perf_dict, 'datastore.totalWriteLatency.average'),
                                                                    each_vm_hardware.backing.datastore.info.vmfs.uuid,
                                                                    vm,
                                                                    statInt)
                        DatastoreLatWrite = (float(sum(statDatastoreLatWrite[0].value[0].value)) / statInt)
                        DatastoreLatWrite = "{:.0f}".format(DatastoreLatWrite) if DatastoreLatWrite < 25 else "{}{:.0f}{}".format(bcolors.FAIL, DatastoreLatWrite, bcolors.ENDC)

                        disk_list.append('Name: {} \r\n'
                                        '                     Size: {:.1f} GB \r\n'
                                        '                     Thin: {} \r\n'
                                        '                     File: {}\r\n'
                                        '                     VirtualDisk: IORead-{:.0f}, IOWrite-{:.0f}, Latency Read-{} ms, Latency Write-{} ms \r\n'
                                        '                     Datastore: IORead-{:.0f}, IOWrite-{:.0f}, Latency Read-{} ms, Latency Write-{} ms'.format(each_vm_hardware.deviceInfo.label,
                                                                                                                                                        each_vm_hardware.capacityInKB / 1024 / 1024,
                                                                                                                                                        each_vm_hardware.backing.thinProvisioned,
                                                                                                                                                        each_vm_hardware.backing.fileName,
                                                                                                                                                        VirtualdiskIORead,
                                                                                                                                                        VirtualdiskIOWrite,
                                                                                                                                                        VirtualdiskLatRead,
                                                                                                                                                        VirtualdiskLatWrite,
                                                                                                                                                        DatastoreIORead,
                                                                                                                                                        DatastoreIOWrite,
                                                                                                                                                        DatastoreLatRead,
                                                                                                                                                        DatastoreLatWrite))
                            
                    else:
                        pmObjectType = pbm.ServerObjectRef.ObjectType("virtualDiskId")
                        pmRef = pbm.ServerObjectRef(key="{}:{}".format(vm._moId,
                                                                       each_vm_hardware.key),
                                                                       objectType=pmObjectType)
                        profiles = vsadmin.tools.vsanStoragePolicy.GetStorageProfiles(self.pm, pmRef)
                        storagePolicy = vsadmin.tools.vsanStoragePolicy.ShowStorageProfile(profiles=profiles, verbose=True)
                        disk_list.append('Name: {} \r\n'
                                     '                     Size: {:.1f} GB \r\n'
                                     '                     Thin: {} \r\n'
                                     '                     File: {} \r\n'
                                     '                     Storage Policy: {}'
                                     '                     VirtualDisk: IORead-{:.0f}, IOWrite-{:.0f}, Latency Read-{} ms, Latency Write-{} ms \r\n'.format(each_vm_hardware.deviceInfo.label,
                                                                                                                                                            each_vm_hardware.capacityInKB / 1024 / 1024,
                                                                                                                                                            each_vm_hardware.backing.thinProvisioned,
                                                                                                                                                            each_vm_hardware.backing.fileName,
                                                                                                                                                            storagePolicy,
                                                                                                                                                            VirtualdiskIORead,
                                                                                                                                                            VirtualdiskIOWrite,
                                                                                                                                                            VirtualdiskLatRead,
                                                                                                                                                            VirtualdiskLatWrite))
                    # Memory Balloon
                    statMemoryBalloon = self.build_perf_query(self.serviceInstance.content, self.vchtime, (self.stat_check(self.perf_dict, 'mem.vmmemctl.average')), "", vm, statInt)
                    memoryBalloon = (float(sum(statMemoryBalloon[0].value[0].value) / 1024) / statInt)
                    memoryBalloon = "{:.1f}".format(memoryBalloon) if memoryBalloon <= 0 else "{}{:.1f}{}".format(bcolors.WARNING, memoryBalloon, bcolors.ENDC)

                    # Memory Swapped
                    statMemorySwapped = self.build_perf_query(self.serviceInstance.content, self.vchtime, (self.stat_check(self.perf_dict, 'mem.swapped.average')), "", vm, statInt)
                    memorySwapped = (float(sum(statMemorySwapped[0].value[0].value) / 1024) / statInt)
                    memorySwapped = "{:.1f}".format(memorySwapped) if memorySwapped <= 0 else "{}{:.1f}{}".format(bcolors.FAIL, memorySwapped, bcolors.ENDC)
                    memory = "{} MB ({:.1f} GB) [Ballooned: {} MB, Swapped: {} MB]".format(summary.config.memorySizeMB, (float(summary.config.memorySizeMB) / 1024), memoryBalloon, memorySwapped)

                else:
                    if each_vm_hardware.backing.datastore.summary.type != 'vsan':
                        disk_list.append('Name: {} \r\n'
                                        '                     Size: {:.1f} GB \r\n'
                                        '                     Thin: {} \r\n'
                                        '                     File: {}'.format(each_vm_hardware.deviceInfo.label,
                                                                               each_vm_hardware.capacityInKB / 1024 / 1024,
                                                                               each_vm_hardware.backing.thinProvisioned,
                                                                               each_vm_hardware.backing.fileName))
                    else:
                        pmObjectType = pbm.ServerObjectRef.ObjectType("virtualDiskId")
                        pmRef = pbm.ServerObjectRef(key="{}:{}".format(vm._moId,
                                                                       each_vm_hardware.key),
                                                                       objectType=pmObjectType)
                        profiles = vsadmin.tools.vsanStoragePolicy.GetStorageProfiles(self.pm, pmRef)
                        storagePolicy = vsadmin.tools.vsanStoragePolicy.ShowStorageProfile(profiles=profiles, verbose=False)
                        disk_list.append('Name: {} \r\n'
                                     '                     Size: {:.1f} GB \r\n'
                                     '                     Thin: {} \r\n'
                                     '                     File: {} \r\n'
                                     '                     Storage Policy: {}'.format(each_vm_hardware.deviceInfo.label,
                                                                                      each_vm_hardware.capacityInKB / 1024 / 1024,
                                                                                      each_vm_hardware.backing.thinProvisioned,
                                                                                      each_vm_hardware.backing.fileName,
                                                                                      storagePolicy))

                    memory = "{} MB ({:.1f} GB)".format(summary.config.memorySizeMB, (float(summary.config.memorySizeMB) / 1024))

        guestToolsRunningStatus = "{}{}{}".format(bcolors.OKGREEN, "Running", bcolors.ENDC) if vm.guest.toolsRunningStatus == "guestToolsRunning" else "{}{}{}".format(bcolors.FAIL, "Not running", bcolors.ENDC)
        guestToolsStatus = "{}{}{}".format(bcolors.OKGREEN, "OK", bcolors.ENDC) if vm.guest.toolsStatus == "toolsOk" else "{}{}{}".format(bcolors.FAIL, "Need Attention", bcolors.ENDC)
        guestToolsVersionStatus = "{}{}{}".format(bcolors.OKGREEN, "Current", bcolors.ENDC) if vm.guest.toolsVersionStatus == "guestToolsCurrent" else "{}{}{}".format(bcolors.WARNING, "Need upgrade", bcolors.ENDC)
        guestToolsVersion = vm.guest.toolsVersion

        powerStatus = "{}{}{}".format(bcolors.OKGREEN, summary.runtime.powerState, bcolors.ENDC) if summary.runtime.powerState == "poweredOn" else "{}{}{}".format(bcolors.FAIL, summary.runtime.powerState, bcolors.ENDC)

        print("UUID               : {}".format(summary.config.instanceUuid))
        print("Name               : {}".format(summary.config.name))
        print("VMRC               : vmrc://{}:443/?moid={}".format(self.server, self.get_moref(vm)))
        print("Guest              : {}".format(summary.config.guestFullName))
        print("State              : {}".format(powerStatus))
        print("Guest Tools Status : Status: {} | Version Status: {} | Version: {} | Health: {}".format(guestToolsRunningStatus, guestToolsVersionStatus, guestToolsVersion, guestToolsStatus))
        print("Cluster            : {}".format(summary.runtime.host.parent.name))
        print("Host               : {}".format(summary.runtime.host.name))
        print("Folder             : {}".format(self.print_folder_tree(vm)))
        print("Number of vCPUs    : {}".format(summary.config.numCpu))
        print("Memory             : {}".format(memory))
        print("VM .vmx Path       : {}".format(summary.config.vmPathName))

        vmxDatastoreName = re.match(r'\[(.*)\]',summary.config.vmPathName).group(1)
        vmxDatastore = self.find_datastore_by_name(vmxDatastoreName)
        if vmxDatastore.summary.type == 'vsan':
            pmObjectType = pbm.ServerObjectRef.ObjectType("virtualMachine")
            pmRef = pbm.ServerObjectRef(key=vm._moId,
                                        objectType=pmObjectType)
            profiles = vsadmin.tools.vsanStoragePolicy.GetStorageProfiles(self.pm, pmRef)
            storagePolicy = vsadmin.tools.vsanStoragePolicy.ShowStorageProfile(profiles=profiles, verbose=verbose)
            print("                     Storage Policy: {}".format(storagePolicy))

        print("Virtual Disks      :")
        if len(disk_list) > 0:
            first = True
            for each_disk in disk_list:
                if first:
                    first = False
                else:
                    print("")
                print("                     {}".format(each_disk))

        if vm.guest.net != []:
            print("Network            : ")
            for card in vm.guest.net:
                print("                     Name: {}".format(card.network))
                if card.deviceConfigId != -1:
                    hwdevice = next((item for item in vm.config.hardware.device if item.key == card.deviceConfigId), None)
                    print("                     Connected: {}".format(hwdevice.connectable.connected))
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
            print("Question  : {}".format(summary.runtime.question.text))

        annotation = summary.config.annotation
        if annotation is not None and annotation != "":
            print("Notes              : {}".format(annotation))
        # print(self.vsanPerfSystem.VsanPerfGetSupportedEntityTypes())
        # metrics = self.get_metric_with_instance(self.serviceInstance.content, vm, self.vchtime, interval)
        # for metric in metrics:
        #     print("ID: {}, Instance: {}".format(self.perf_dict.keys()[self.perf_dict.values().index(metric.counterId)], metric.instance))

    def get_all_objs(self, vimtype, folder=None, recurse=True):
        if not folder:
            folder = self.serviceInstance.content.rootFolder
        obj = {}
        container = self.serviceInstance.content.viewManager.CreateContainerView(folder, vimtype, recurse)
        for managed_object_ref in container.view:
            obj.update({managed_object_ref: managed_object_ref.name})
        return obj

    def find_object_by_name(self, name, obj_type, folder=None, recurse=True):
        if not isinstance(obj_type, list):
            obj_type = [obj_type]
        objects = self.get_all_objs(obj_type, folder=folder, recurse=recurse)
        for obj in objects:
            if obj.name == name:
                return obj
        return None

    def find_datastore_by_name(self, datastore_name):
        return self.find_object_by_name(datastore_name, [vim.Datastore])

    def search_vm_by_name(self, name, name_contain=False):
        content = self.serviceInstance.content
        root_folder = content.rootFolder
        # entity_stack = root_folder.childEntity
        objView = content.viewManager.CreateContainerView(root_folder,
                                                          [vim.VirtualMachine],
                                                          True)
        vmList = objView.view
        objView.Destroy()
        obj = []
        for vm in vmList:
            if not name_contain:
                if (vm.name == name):
                    obj.append(vm)
                    return obj
            else:
                if re.match(".*%s.*" % name, vm.name):
                    obj.append(vm)
        return obj

    def search_vm_by_ip(self, ip, custom_fields=False):
        obj = []
        content = self.serviceInstance.content
        root_folder = content.rootFolder

        if not NetworkCheck.checkIP(ip):
            print("IP address {} is invalid.".format(ip))
            return obj
        search_obj = content.searchIndex.FindByIp(None,
                                                  ip,
                                                  True)
        if search_obj:
            obj.append(search_obj)
            return obj
        elif custom_fields:
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

        content = self.serviceInstance.content
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
        search_obj = self.serviceInstance.content.searchIndex.FindByDnsName(None,
                                                               hostname,
                                                               True)
        if search_obj:
            obj.append(search_obj)
        return obj

    def search_vm_by_task(self, task):
        content = self.serviceInstance.content
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
